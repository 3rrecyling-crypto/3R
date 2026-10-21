"""
Asistente con IA del tablero de diésel (Next: /diesel/tablero, botón "Pregúntale a la IA").

El usuario escribe o dicta una pregunta; Claude recibe el tablero con los
filtros que tiene en pantalla y, si la pregunta es de otro periodo o patio, usa
la herramienta `consultar_tablero` (la misma función del tablero, solo con los
patios del usuario). Si pide un reporte, arma uno en Excel a su medida con
`generar_reporte_excel` (reporte_excel.py) y la pantalla muestra el botón para
descargarlo. Claude no toca la base de datos.

Reusa la configuración de Reportes con IA: la llave de Anthropic (Configuración
IA), el modelo, el límite de peticiones y la bitácora del panel Consumo de IA.
"""
import json
import logging
import re
import time

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponse
from ternium import reportes_ia as rIA

from . import reporte_excel
from .views_tablero import datos_tablero, puede_ver, rango

logger = logging.getLogger(__name__)

MAX_PASOS = 4         # llamadas al modelo por pregunta
MAX_CONSULTAS = 4     # periodos o patios extra que puede pedir
CARGAS_PARA_IA = 25   # últimas cargas de cada grupo que ve el modelo

HERRAMIENTA = {
    'name': 'consultar_tablero',
    'description': (
        'Devuelve el tablero de cargas de diésel (mismo formato que el que ya tienes) para otro periodo '
        'y/o patio. Úsala cuando la pregunta sea de otras fechas u otro patio, o para comparar periodos.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'desde': {'type': 'string', 'description': 'Fecha inicial AAAA-MM-DD.'},
            'hasta': {'type': 'string', 'description': 'Fecha final AAAA-MM-DD (máximo un año de rango).'},
            'patio_id': {'type': 'integer', 'description': 'id del patio (de patios_disponibles); 0 = todos.'},
        },
        'required': ['desde', 'hasta'],
    },
}

HERRAMIENTA_REPORTE = {
    'name': 'generar_reporte_excel',
    'description': (
        'Arma un reporte en Excel del diésel a la medida de lo que pidió el usuario; la pantalla le muestra '
        'el botón para descargarlo. Siempre lleva una hoja de Resumen (indicadores y tu análisis) y además '
        'las secciones que elijas. Puedes filtrar por un permisionario o por un equipo (unidad o thermo). '
        'Devuelve cuántas cargas, litros y costo trae el reporte para que se lo describas al usuario.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'titulo': {'type': 'string', 'description': 'Título corto del reporte, en español.'},
            'desde': {'type': 'string', 'description': 'Fecha inicial AAAA-MM-DD.'},
            'hasta': {'type': 'string', 'description': 'Fecha final AAAA-MM-DD (máximo un año de rango).'},
            'patio_id': {'type': 'integer', 'description': 'id del patio (de patios_disponibles); 0 = todos.'},
            'secciones': {
                'type': 'array',
                'items': {'type': 'string', 'enum': list(reporte_excel.SECCIONES)},
                'description': ('Hojas a incluir: por_dia (litros por día con gráfica), equipos_3r (unidades y thermos de 3R '
                                'con rendimiento), cargas_3r (cada carga de 3R), permisionarios (resumen por permisionario), '
                                'cargas_permisionarios (cada carga de permisionarios), compras, ajustes, totems.'),
            },
            'permisionario': {'type': 'string', 'description': 'Opcional: nombre (o parte) del permisionario para filtrar las cargas.'},
            'equipo': {'type': 'string', 'description': 'Opcional: número de unidad o identificador del thermo para filtrar.'},
        },
        'required': ['titulo', 'desde', 'hasta', 'secciones'],
    },
}
MAX_REPORTES = 3


def _para_ia(d):
    """El tablero en JSON compacto para el modelo (sin días en cero ni todas las cargas)."""
    flota, perms = d['flota_3r'], d['permisionarios']
    patio = next((p['nombre'] for p in d['patios'] if p['id'] == d['patio']), 'Todos los patios')
    return json.dumps({
        'periodo': {'desde': d['periodo']['desde'], 'hasta': d['periodo']['hasta']},
        'patio': patio,
        'patios_disponibles': d['patios'],
        'total': d['total'],
        '3r_recycling': {
            'kpis': flota['kpis'],
            'litros_por_dia_unidades_thermos': [[x['fecha'], x['unidades'], x['thermos']]
                                                for x in flota['por_dia'] if x['unidades'] or x['thermos']],
            'equipos': flota['equipos'],
            'ultimas_cargas': flota['cargas'][:CARGAS_PARA_IA],
        },
        'permisionarios': {
            'kpis': perms['kpis'],
            'litros_por_dia': [[x['fecha'], x['litros']] for x in perms['por_dia'] if x['litros']],
            'lista': [{
                **{k: v for k, v in p.items() if k not in ('por_dia', 'cargas_detalle')},
                'ultimas_cargas': p['cargas_detalle'][:CARGAS_PARA_IA],
            } for p in perms['lista']],
        },
    }, ensure_ascii=False, separators=(',', ':'))


def _prompt(hoy):
    fecha = f'{rIA.DIAS[hoy.weekday()]} {hoy.day} de {rIA.MESES[hoy.month - 1]} de {hoy.year} ({hoy.isoformat()})'
    return f"""Eres el asistente del Tablero de cargas de diésel del ERP de 3R Recycling. Contestas preguntas sobre las cargas de diésel: litros, cargas, unidades, thermos, rendimiento, costos y permisionarios. La pregunta puede venir escrita o dictada por voz (con errores de dictado).

LOS DATOS
- Recibes en JSON el tablero con los filtros que el usuario tiene en pantalla (periodo y patio).
- "3r_recycling" es la flota propia de 3R RECYCLING: sus unidades (kilometraje, litros y rendimiento en km/L) y sus thermos (horas y litros).
- "permisionarios" son transportistas externos con unidades ajenas a 3R: de ellos hay litros, cargas, equipos y costo, pero NO manejan rendimiento ni kilometraje; nunca lo calcules ni lo menciones para ellos. "Sin permisionario" son cargas sin permisionario asignado.
- precio_litro es el precio por litro del tótem del que salió la carga (la última compra de diésel que entró a ese tótem antes de la carga) y costo = litros × precio_litro, en pesos mexicanos. precio_promedio es el precio por litro ponderado por litros. Una carga con precio_litro null no tenía compra registrada en su tótem y se cuenta en cargas_sin_precio.
- "ultimas_cargas" trae solo las cargas más recientes de cada grupo; los totales y kpis sí incluyen todas.

CÓMO TRABAJAS
- Si la pregunta es de otro periodo o patio ("¿y el mes pasado?", "compárame con septiembre", "solo el Patio Principal"), usa consultar_tablero con esas fechas; puedes llamarla varias veces para comparar. Si se contesta con los datos que ya tienes, no la uses.
- Si el usuario pide un reporte, un Excel, un archivo o algo para descargar o imprimir, usa generar_reporte_excel con el periodo, el patio, las secciones que respondan a lo que pidió y, si aplica, el filtro de permisionario o de equipo (por ejemplo "reporte de las cargas de Fletes del Norte de septiembre" → permisionario "Fletes del Norte", secciones cargas_permisionarios y por_dia). Después dile en pocas frases qué trae el reporte (con las cifras que te devuelve la herramienta) y que lo descarga con el botón "Descargar Excel". Nunca digas que no puedes generar reportes.
- Nunca inventes cifras ni nombres: todo lo que afirmes debe salir de los datos. Puedes calcular diferencias, porcentajes y promedios con cuidado.
- No hagas preguntas de aclaración: si algo es ambiguo, elige la interpretación más razonable y dila en pocas palabras.
- Si la pregunta no es del diésel, explica amablemente que este asistente consulta las cargas de diésel.

CÓMO RESPONDES
- En español de México, claro y directo; empieza por la respuesta. Breve: unas pocas frases o viñetas (la respuesta también se puede escuchar en voz alta).
- Usa **negritas** para las cifras clave y viñetas con "• " cuando enumeres. No uses tablas markdown ni encabezados (#).
- Litros con "L" (1,234 L), dinero en pesos ($12,345.67) y rendimiento en km/L.

Hoy es {fecha}."""


class _SinIA(Exception):
    def __init__(self, aviso):
        super().__init__(aviso)
        self.aviso = aviso


def responder(pregunta, user, api_key, datos, historial, uso, consultas, reportes=None):
    """Ciclo de herramientas con Claude; devuelve el texto. Suma tokens y costo en `uso`,
    anota en `consultas` cada periodo que se consultó y en `reportes` cada reporte de
    Excel que se armó. Lanza _SinIA si la API falla."""
    reportes = reportes if reportes is not None else []
    import anthropic

    client = rIA._cliente_anthropic(api_key)
    system = [{'type': 'text', 'text': _prompt(rIA._hoy()), 'cache_control': {'type': 'ephemeral'}}]
    messages = []
    for h in historial:
        messages.append({'role': 'user', 'content': h['pregunta']})
        messages.append({'role': 'assistant', 'content': h['respuesta']})
    messages.append({'role': 'user', 'content': [
        # El tablero va en su propio bloque en caché: se reusa en cada paso del ciclo.
        {'type': 'text', 'text': f'Tablero en pantalla:\n{_para_ia(datos)}', 'cache_control': {'type': 'ephemeral'}},
        {'type': 'text', 'text': pregunta},
    ]})

    def llamar(**extra):
        try:
            return client.messages.create(
                model=rIA.MODELO_AGENTE, max_tokens=16000, system=system, tools=[HERRAMIENTA, HERRAMIENTA_REPORTE],
                output_config={'effort': rIA.ESFUERZO_AGENTE}, messages=messages, **extra)
        except anthropic.AuthenticationError:
            raise _SinIA('La llave de Anthropic de Configuración IA no es válida.')
        except anthropic.PermissionDeniedError:
            raise _SinIA('La llave de Anthropic no tiene acceso al modelo.')
        except anthropic.RateLimitError:
            raise _SinIA('La IA está saturada en este momento. Intenta en un minuto.')
        except anthropic.APIStatusError as e:
            logger.warning('Tablero diésel IA: Claude respondió %s: %s', e.status_code, e.message)
            raise _SinIA('La IA no respondió en este momento. Intenta de nuevo.')
        except anthropic.APIConnectionError as e:
            logger.warning('Tablero diésel IA: sin conexión con Claude (%s)', e)
            raise _SinIA('No hubo conexión con la IA. Revisa el internet e intenta de nuevo.')

    respuesta = None
    usadas = 0
    for paso in range(MAX_PASOS):
        # En el último paso ya no se permiten herramientas: que conteste con lo que tiene
        respuesta = llamar(**({'tool_choice': {'type': 'none'}} if paso == MAX_PASOS - 1 else {}))
        rIA._sumar_uso(uso, respuesta)
        if respuesta.stop_reason == 'refusal':
            return 'No puedo ayudar con esa solicitud. Intenta preguntarlo de otra forma.'
        if respuesta.stop_reason != 'tool_use':
            break
        messages.append({'role': 'assistant', 'content': respuesta.content})
        resultados = []
        for bloque in respuesta.content:
            if bloque.type != 'tool_use':
                continue
            if bloque.name == HERRAMIENTA_REPORTE['name']:
                if len(reportes) >= MAX_REPORTES:
                    resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                       'content': 'Ya se armaron varios reportes en esta respuesta; no hagas más.'})
                    continue
                try:
                    spec = reporte_excel.normalizar(bloque.input)
                    info = reporte_excel.resumen(user, spec)
                    reportes.append(spec)
                    resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id,
                                       'content': json.dumps(info, ensure_ascii=False, default=str)})
                except Exception:
                    logger.exception('Tablero diésel IA: falló el reporte %s', bloque.input)
                    resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                       'content': 'No se pudo armar el reporte. Intenta con otros filtros.'})
                continue
            if bloque.name != HERRAMIENTA['name']:
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                   'content': 'Herramienta desconocida.'})
                continue
            usadas += 1
            if usadas > MAX_CONSULTAS:
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                   'content': 'Límite de consultas alcanzado: responde con los datos que ya tienes.'})
                continue
            entrada = bloque.input if isinstance(bloque.input, dict) else {}
            try:
                desde, hasta = rango(str(entrada.get('desde') or ''), str(entrada.get('hasta') or ''))
                patio = entrada.get('patio_id') or None
                consultas.append({'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'patio': patio})
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id,
                                   'content': _para_ia(datos_tablero(user, desde, hasta, patio))})
            except Exception:
                logger.exception('Tablero diésel IA: falló la consulta %s', entrada)
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                   'content': 'La consulta falló. Intenta con otras fechas.'})
        messages.append({'role': 'user', 'content': resultados})

    texto = ''.join(b.text for b in (respuesta.content if respuesta else []) if b.type == 'text').strip()
    return texto or 'No pude armar una respuesta. Intenta decirlo de otra forma.'


class TableroIAAPIView(APIView):
    """GET: si la IA está conectada.
    POST {pregunta, desde, hasta, patio?, historial?: [{pregunta, respuesta}], conversacion?}: {respuesta}."""

    def get(self, request):
        if not puede_ver(request.user):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'ia_disponible': bool(rIA._config_agente())})

    def post(self, request):
        user = request.user
        if not puede_ver(user):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        body = request.data if isinstance(request.data, dict) else {}
        pregunta = ' '.join(str(body.get('pregunta') or '').split())[:rIA.MAX_PREGUNTA]
        if not pregunta:
            return Response({'detail': 'Escribe o dicta tu pregunta.'}, status=status.HTTP_400_BAD_REQUEST)
        api_key = rIA._config_agente()
        if not api_key:
            return Response({'detail': 'La IA no está conectada. Un administrador puede configurarla en Configuración IA.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not rIA._dentro_del_limite(user):
            return Response({'detail': 'Hiciste muchas preguntas seguidas. Espera unos minutos e intenta de nuevo.'},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)

        historial = [
            {'pregunta': ' '.join(str(h.get('pregunta') or '').split())[:rIA.MAX_PREGUNTA],
             'respuesta': str(h.get('respuesta') or '')[:3000]}
            for h in (body.get('historial') or []) if isinstance(h, dict)
        ]
        historial = [h for h in historial if h['pregunta'] and h['respuesta']][-3:]
        conversacion = re.sub(r'[^A-Za-z0-9\-]', '', str(body.get('conversacion') or ''))[:40]
        desde, hasta = rango(str(body.get('desde') or ''), str(body.get('hasta') or ''))
        patio = body.get('patio') or None
        datos = datos_tablero(user, desde, hasta, patio)

        inicio = time.monotonic()
        uso = rIA.uso_vacio()
        consultas = [{'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'patio': datos['patio']}]
        reportes = []
        try:
            texto, aviso = responder(pregunta, user, api_key, datos, historial, uso, consultas, reportes), None
        except _SinIA as e:
            texto, aviso = '', e.aviso
        registro = {
            'respuesta': texto, 'motor': 'ia', 'proveedor': 'anthropic', 'avisos': [aviso] if aviso else [],
            'resultados': [{'consulta': c} for c in consultas] + [{'consulta': {'reporte_excel': r}} for r in reportes],
            'duracion_ms': int((time.monotonic() - inicio) * 1000),
        }
        # En la bitácora del panel Consumo de IA, marcada como del tablero de diésel.
        rIA._registrar(user, f'[Diésel] {pregunta}', conversacion, registro, uso)
        if aviso:
            return Response({'detail': aviso}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        logger.info('Tablero diésel IA [%s] %s → %d consultas · US$%.5f',
                    user.username, pregunta, len(consultas), uso['costo_usd'])
        return Response({'respuesta': texto, 'reportes': reportes, 'duracion_ms': registro['duracion_ms']})


class TableroIAExcelAPIView(APIView):
    """POST {reporte, pregunta?, respuesta?}: el Excel del reporte que armó la IA. La especificación
    se vuelve a validar y los datos salen solo de los patios del usuario."""

    def post(self, request):
        if not puede_ver(request.user):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        body = request.data if isinstance(request.data, dict) else {}
        spec = reporte_excel.normalizar(body.get('reporte'))
        try:
            contenido = reporte_excel.construir(
                request.user, spec, ' '.join(str(body.get('pregunta') or '').split())[:rIA.MAX_PREGUNTA],
                str(body.get('respuesta') or '')[:6000])
        except Exception:
            logger.exception('Tablero diésel IA: falló el Excel %s', spec)
            return Response({'detail': 'No se pudo generar el Excel.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        respuesta = HttpResponse(contenido, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        respuesta['Content-Disposition'] = f'attachment; filename="{reporte_excel.nombre_archivo(spec)}"'
        return respuesta
