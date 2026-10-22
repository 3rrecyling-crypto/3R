"""
Auditoría con IA de las fotos de la bomba (Next: /diesel/cargas, botón "Auditar con IA").

La IA solo lee la foto y deja un estatus en la carga; nunca cambia litros ni ningún otro dato.
- Verificado: el contador de la carga del medidor ("RESET TO ZERO") coincide con los litros
  capturados (±1 L o ±0.5 %).
- Alerta: no coincide, o la foto no se lee. La nota dice por qué.
Unidad: foto de la bomba contra litros de diésel. Thermo: foto de la bomba del thermo contra
litros del thermo. La IA lee la foto sin conocer los litros capturados (para no sesgarla) y la
comparación la hace el sistema. Se guarda también el totalizador ("TOTAL LITRES") que se lea.

Solo se auditan las cargas sin estatus y con foto, desde AUDITAR_DESDE (antes las fotos no se
guardaban en S3 y se perdieron); las que ya tienen estatus no se vuelven a revisar, para ahorrar.
La pantalla pide lotes de LOTE cargas hasta terminar, así ninguna petición tarda demasiado.
"""
import base64
import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ternium import reportes_ia as rIA

from . import archivos
from .models import CargaDiesel
from .views import filtrar_cargas
from .views_tablero import puede_ver

logger = logging.getLogger(__name__)

MODELO = os.environ.get('DIESEL_AUDITORIA_MODELO', 'claude-sonnet-5-5')
ESFUERZO = os.environ.get('DIESEL_AUDITORIA_ESFUERZO', 'medium')
LOTE = 5                      # cargas por petición (en paralelo)
LADO_MAX = 2000               # px: la foto se reduce antes de mandarla
TOLERANCIA_L, TOLERANCIA_PCT = Decimal('1'), Decimal('0.005')
AUDITAR_DESDE = date(2026, 10, 22)  # arreglo de las fotos en S3

PROMPT = (
    'Eres auditor de cargas de diésel de 3R Recycling. Recibes la foto del medidor de la bomba tomada al '
    'terminar una carga. El medidor (por ejemplo Fill-Rite serie 900) tiene dos contadores:\n'
    '1. El contador grande, con la leyenda "RESET TO ZERO": son los LITROS DE ESTA CARGA (se pone en cero '
    'antes de cargar). Si la última rueda está entre dos números, reporta el menor; si se ven decimales, '
    'inclúyelos.\n'
    '2. El contador pequeño "TOTAL LITRES": el acumulado histórico de la bomba (totalizador).\n'
    'Lee los dos tal como se ven, sin ceros a la izquierda. No adivines: si el contador de la carga no se lee '
    'con claridad (borroso, reflejo, tapado, cortado o la foto no es de un medidor), pon legible=false y '
    'explica en "observacion" en pocas palabras. Pon 0 en lo que no se lea.'
)
ESQUEMA = {
    'type': 'object',
    'properties': {
        'legible': {'type': 'boolean', 'description': 'Se lee con claridad el contador de esta carga'},
        'litros_carga': {'type': 'number', 'description': 'Contador RESET TO ZERO (0 si no se lee)'},
        'totalizador': {'type': 'number', 'description': 'Contador TOTAL LITRES (0 si no se lee)'},
        'observacion': {'type': 'string', 'description': 'Breve; por qué no se lee, si aplica'},
    },
    'required': ['legible', 'litros_carga', 'totalizador', 'observacion'],
    'additionalProperties': False,
}


class SinIA(Exception):
    """La IA no está disponible; el mensaje se muestra tal cual."""


def pendientes(user, params):
    """Cargas que faltan por auditar con los filtros del listado (sin el de auditoría)."""
    filtros = {k: v for k, v in params.items() if k != 'auditoria'}
    inicio = timezone.make_aware(datetime.combine(AUDITAR_DESDE, datetime.min.time()))
    # Con su foto: unidad → bomba; thermo → bomba del thermo
    con_foto = (Q(tipo_carga='thermo') & ~Q(foto_thermo='') & Q(foto_thermo__isnull=False)) | \
        (~Q(tipo_carga='thermo') & ~Q(foto_bomba='') & Q(foto_bomba__isnull=False))
    return filtrar_cargas(user, filtros).filter(con_foto, auditoria_estado='', fecha_carga__gte=inicio)


def _pares(c):
    """(campo de la foto, litros capturados, nombre) que se comparan; nunca se cruzan unidad y thermo."""
    if c.tipo_carga == 'thermo':
        return [('foto_thermo', c.litros_thermo, 'bomba del thermo')]
    pares = [('foto_bomba', c.litros_diesel, 'bomba')]
    if c.litros_thermo:  # cargas del sistema anterior con motor y thermo en una sola
        pares.append(('foto_thermo', c.litros_thermo, 'bomba del thermo'))
    return pares


def _imagen(contenido):
    """La foto como JPEG en base64, derecha y de máximo LADO_MAX px."""
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(contenido))).convert('RGB')
    img.thumbnail((LADO_MAX, LADO_MAX))
    salida = io.BytesIO()
    img.save(salida, 'JPEG', quality=85)
    return base64.standard_b64encode(salida.getvalue()).decode('ascii')


def leer_foto(client, archivo):
    """Lo que la IA lee en la foto: (dict, usage) o (None, None) si no hay archivo legible."""
    import anthropic
    try:
        datos = _imagen(archivos.leer(archivo))
    except Exception:
        logger.warning('Auditoría diésel: no se pudo abrir la foto %s', archivo.name, exc_info=True)
        return {'legible': False, 'observacion': 'No se pudo abrir la foto'}, None
    try:
        r = client.messages.create(
            model=MODELO, max_tokens=4000, system=PROMPT,
            output_config={'effort': ESFUERZO, 'format': {'type': 'json_schema', 'schema': ESQUEMA}},
            messages=[{'role': 'user', 'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': datos}},
                {'type': 'text', 'text': 'Lee el medidor de esta foto.'},
            ]}],
        )
    except anthropic.AuthenticationError:
        raise SinIA('La llave de Anthropic de Configuración IA no es válida.')
    except anthropic.PermissionDeniedError:
        raise SinIA('La llave de Anthropic no tiene acceso al modelo.')
    except anthropic.RateLimitError:
        raise SinIA('La IA está saturada en este momento. Intenta en un minuto.')
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        logger.warning('Auditoría diésel: Claude no respondió (%s)', e)
        raise SinIA('La IA no respondió en este momento. Intenta de nuevo.')
    if r.stop_reason == 'refusal':
        return {'legible': False, 'observacion': 'La IA no pudo revisar la foto'}, r.usage
    try:
        lectura = json.loads(next(b.text for b in r.content if b.type == 'text'))
    except (StopIteration, ValueError):
        return {'legible': False, 'observacion': 'La IA no dio una lectura'}, r.usage
    return lectura, r.usage


def _decimal(v):
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return d if d > 0 else None


def comparar(lectura, capturados, nombre):
    """(coincide, litros leídos, totalizador, nota)."""
    leidos = _decimal(lectura.get('litros_carga')) if lectura.get('legible') else None
    total = _decimal(lectura.get('totalizador'))
    if leidos is None:
        obs = ' '.join(str(lectura.get('observacion') or '').split())[:120]
        return False, None, total, f'No se lee la foto de la {nombre}' + (f': {obs}' if obs else '')
    tolerancia = max(TOLERANCIA_L, capturados * TOLERANCIA_PCT)
    if abs(leidos - capturados) <= tolerancia:
        return True, leidos, total, ''
    return False, leidos, total, f'La foto de la {nombre} marca {leidos:,.2f} L y se capturaron {capturados:,.2f} L'


def auditar(user, cargas, api_key, uso):
    """Audita las cargas (en paralelo) y guarda el estatus. Devuelve los resultados."""
    client = rIA._cliente_anthropic(api_key)
    trabajos = [(c, campo, litros, nombre) for c in cargas for campo, litros, nombre in _pares(c)]

    def leer(trabajo):
        c, campo, _, _ = trabajo
        archivo = getattr(c, campo)
        if not archivo:
            return {'legible': False, 'observacion': 'Sin foto'}, None
        return leer_foto(client, archivo)

    with ThreadPoolExecutor(max_workers=LOTE) as ex:
        lecturas = list(ex.map(leer, trabajos))

    por_carga = {}
    for (c, _, litros, nombre), (lectura, usage) in zip(trabajos, lecturas):
        if usage is not None:
            uso['llamadas'] += 1
            uso['entrada'] += getattr(usage, 'input_tokens', 0) or 0
            uso['salida'] += getattr(usage, 'output_tokens', 0) or 0
            uso['costo_usd'] += rIA.costo_llamada(MODELO, usage)
        por_carga.setdefault(c.pk, []).append(comparar(lectura, litros, nombre))

    ahora, resultados = timezone.now(), []
    for c in cargas:
        partes = por_carga.get(c.pk, [])
        ok = bool(partes) and all(p[0] for p in partes)
        estado = 'verificado' if ok else 'alerta'
        nota = '; '.join(p[3] for p in partes if p[3])[:255]
        # Solo los campos de la auditoría, y solo si sigue sin estatus (otra auditoría al mismo tiempo)
        CargaDiesel.objects.filter(pk=c.pk, auditoria_estado='').update(
            auditoria_estado=estado, auditoria_litros_foto=partes[0][1] if partes else None,
            auditoria_totalizador=partes[0][2] if partes else None, auditoria_nota=nota,
            auditoria_fecha=ahora, auditoria_por=user)
        resultados.append({'id': c.pk, 'equipo': c.equipo, 'estado': estado, 'nota': nota,
                           'litros_foto': float(partes[0][1]) if partes and partes[0][1] is not None else None})
    return resultados


def _ultima():
    c = CargaDiesel.objects.exclude(auditoria_fecha=None).select_related('auditoria_por').order_by('-auditoria_fecha').first()
    if not c:
        return None
    u = c.auditoria_por
    return {'fecha': timezone.localtime(c.auditoria_fecha).strftime('%d/%m/%Y %H:%M'),
            'usuario': (u.get_full_name() or u.username) if u else ''}


class AuditoriaCargasAPIView(APIView):
    """GET (con los filtros del listado): cuántas faltan por auditar y la última auditoría.
    POST (mismos filtros): audita el siguiente lote de cargas sin estatus."""

    def get(self, request):
        if not puede_ver(request.user):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            'pendientes': pendientes(request.user, request.query_params).count(),
            'ultima': _ultima(), 'ia_disponible': bool(rIA._config_agente()),
            'desde': AUDITAR_DESDE.strftime('%d/%m/%Y'),
        })

    def post(self, request):
        user = request.user
        if not puede_ver(user):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        api_key = rIA._config_agente()
        if not api_key:
            return Response({'detail': 'La IA no está conectada. Un administrador puede configurarla en Configuración IA.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        lote = list(pendientes(user, request.query_params).select_related('unidad', 'thermo')
                    .order_by('fecha_carga', 'pk')[:LOTE])
        inicio = time.monotonic()
        uso = {**rIA.uso_vacio(), 'modelo': MODELO}
        aviso, resultados = None, []
        if lote:
            try:
                resultados = auditar(user, lote, api_key, uso)
            except SinIA as e:
                aviso = str(e)
            resumen = ', '.join(f"{r['equipo']}: {r['estado']}" for r in resultados) or aviso or ''
            rIA._registrar(user, f'[Diésel] Auditoría de fotos ({len(lote)} cargas)', '',
                           {'respuesta': resumen, 'motor': 'ia', 'proveedor': 'anthropic', 'resultados': [],
                            'avisos': [aviso] if aviso else [], 'duracion_ms': int((time.monotonic() - inicio) * 1000)}, uso)
        if aviso:
            return Response({'detail': aviso}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        logger.info('Auditoría diésel [%s]: %d cargas · US$%.5f', user.username, len(resultados), uso['costo_usd'])
        return Response({'resultados': resultados, 'pendientes': pendientes(user, request.query_params).count()})
