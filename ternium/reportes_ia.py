"""
Reportes con IA: el usuario pide datos de sus remisiones con texto o con voz.

Cómo funciona:
  1. `interpretar()` traduce la pregunta a una CONSULTA (un dict) con la IA de
     Configuración IA (Anthropic o DeepSeek; Gemini de respaldo). Si no hay IA
     disponible, `interpretar_reglas()` cubre las preguntas más comunes.
  2. `normalizar()` valida la consulta contra listas cerradas de filtros,
     agrupaciones, métricas y columnas: la IA nunca escribe SQL ni elige campos
     fuera de esas listas.
  3. `ejecutar()` la corre con el ORM, limitada a las empresas autorizadas del
     usuario. Las cifras salen SIEMPRE de la base de datos, nunca de la IA.

Fechas: como todos los reportes, se filtra por la fecha de INICIO DE DESCARGA
(o la de captura si la remisión no la tiene). Pesos: kilos, igual que los
tableros (suma de los detalles de cada remisión).
"""
from __future__ import annotations

import calendar
import copy
import datetime as dt
import difflib
import importlib.util
import json
import logging
import os
import re
import time
import unicodedata

from django.core.cache import cache
from django.contrib.auth.models import User
from django.db.models import (
    Avg, Case, Count, DateField, DurationField, ExpressionWrapper, F, FloatField, Prefetch, Q,
    Sum, Value, When,
)
from django.db.models.functions import (
    Cast, Coalesce, ExtractIsoWeekDay, TruncDate, TruncMonth, TruncWeek, TruncYear,
)
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    Cliente, ConfiguracionManifiesto, Contenedor, DetalleRemision, Empresa, EvidenciaRemision,
    HistorialRemision, LineaTransporte, Lugar, Material, Operador, Remision, Unidad,
    es_proboca, es_sealed_air,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# VOCABULARIO PERMITIDO
# ════════════════════════════════════════════════════════════════════════════

TIPOS = ('lista', 'agrupado', 'total', 'conversacion')
# Fecha con la que se filtra el periodo: clave → texto para el usuario
CAMPOS_FECHA = {
    'descarga': 'inicio de descarga', 'captura': 'fecha de captura', 'carga': 'inicio de carga',
    'auditoria': 'fecha de auditoría', 'registro': 'fecha de registro en el sistema',
    'destruccion': 'fecha de destrucción',
}
STATUS = dict(Remision.STATUS_CHOICES)

# Filtros por nombre: clave → (etiqueta, modelo, campo con el nombre, ruta desde
# Remision, campo de texto libre que también se captura en la remisión).
CATALOGOS = {
    'empresa': ('Unidad de negocio', Empresa, 'nombre', 'empresa', None),
    'origen': ('Origen', Lugar, 'nombre', 'origen', None),
    'destino': ('Destino', Lugar, 'nombre', 'destino', None),
    'cliente': ('Cliente', Cliente, 'nombre', 'cliente', None),
    'material': ('Material', Material, 'nombre', 'detalles__material', None),
    'operador': ('Operador', Operador, 'nombre', 'operador', 'operador_manual'),
    'linea_transporte': ('Línea de transporte', LineaTransporte, 'nombre', 'linea_transporte', None),
    'unidad': ('Unidad', Unidad, 'internal_id', 'unidad', 'unidad_manual'),
    'contenedor': ('Contenedor', Contenedor, 'nombre', 'contenedor', 'contenedor_manual'),
    'patio_rechazo': ('Patio de rechazo', Lugar, 'nombre', 'detalles__patio_rechazo', None),
}

# Búsqueda de texto (contiene; si hay varios campos basta con que uno coincida):
# clave → (etiqueta, campos de Remision)
TEXTOS = {
    'remision': ('Remisión', ['remision']),
    'folio_carga': ('Folio de carga', ['folio_ld']),
    'folio_descarga': ('Folio de descarga', ['folio_dlv']),
    'folio_salida': ('Folio de salida', ['folio_salida']),
    'folio_medline': ('Folio Medline', ['folio_medline']),
    'factura': ('Factura', ['factura_nombre', 'facturas__folio', 'facturas__folio_fiscal']),
    'placas': ('Placas', ['placas_unidad_manual', 'placas_contenedor_manual',
                          'unidad__license_plate', 'contenedor__placas']),
    'auditado_por': ('Auditado por', ['auditado_por__username', 'auditado_por__first_name',
                                      'auditado_por__last_name']),
    'texto': ('Texto', ['comentario', 'descripcion', 'trazabilidad_notas', 'comentarios_destruccion']),
}

# Filtros de sí / no: clave → (texto si es sí, texto si es no)
SI_NO = {
    'con_rechazo': ('Con rechazo', 'Sin rechazo'),
    'con_factura': ('Con factura', 'Sin factura'),
    'con_evidencia': ('Con evidencias', 'Sin evidencias'),
    'con_manifiesto': ('Con manifiesto', 'Sin manifiesto'),
    'con_descarga': ('Con descarga registrada', 'Sin descarga registrada'),
    'con_folio_salida': ('Con folio de salida', 'Sin folio de salida'),
    'destruccion_completa': ('Destrucción fiscal completa', 'Destrucción fiscal pendiente'),
}

# Rangos numéricos (<clave>_min / <clave>_max): clave → (etiqueta, unidad)
RANGOS = {
    'merma': ('Merma', '%'),
    'carga': ('Carga', 'kg'),
    'descarga': ('Descarga', 'kg'),
    'antiguedad': ('Antigüedad', 'días'),
}

# Dimensiones que viven en las líneas de material (DetalleRemision)
DIM_DETALLE = {'material': 'material__nombre', 'patio_rechazo': 'patio_rechazo__nombre'}

DIMENSIONES = {
    'empresa': 'Unidad de negocio', 'origen': 'Origen', 'destino': 'Destino',
    'cliente': 'Cliente', 'material': 'Material', 'operador': 'Operador',
    'linea_transporte': 'Línea de transporte', 'unidad': 'Unidad',
    'contenedor': 'Contenedor', 'status': 'Estatus', 'patio_rechazo': 'Patio de rechazo',
    'auditado_por': 'Auditado por',
    'dia': 'Día', 'semana': 'Semana', 'mes': 'Mes', 'anio': 'Año', 'dia_semana': 'Día de la semana',
}
DIMENSIONES_TIEMPO = ('dia', 'semana', 'mes', 'anio', 'dia_semana')

# clave → (título, tipo de dato para formatear)
METRICAS = {
    'remisiones': ('Remisiones', 'entero'),
    'carga_kg': ('Carga (kg)', 'kg'),
    'descarga_kg': ('Descarga (kg)', 'kg'),
    'rechazo_kg': ('Rechazo (kg)', 'kg'),
    'diferencia_kg': ('Diferencia (kg)', 'kg'),
    'merma_pct': ('Merma %', 'pct'),
    'carga_ton': ('Carga (t)', 'ton'),
    'descarga_ton': ('Descarga (t)', 'ton'),
    'rechazo_ton': ('Rechazo (t)', 'ton'),
    'bultos': ('Bultos', 'entero'),
    'promedio_carga_kg': ('Carga promedio por remisión (kg)', 'kg'),
    'promedio_descarga_kg': ('Descarga promedio por remisión (kg)', 'kg'),
    'importe': ('Importe', 'dinero'),
    'peso_bascula_kg': ('Peso báscula (kg)', 'kg'),
    'tiempo_carga_h': ('Tiempo promedio de carga (h)', 'horas'),
    'tiempo_descarga_h': ('Tiempo promedio de descarga (h)', 'horas'),
    'tiempo_transito_h': ('Tránsito promedio (h)', 'horas'),
}
METRICAS_DEFECTO = ['remisiones', 'carga_kg', 'descarga_kg', 'merma_pct']
_SOLO_AGRUPADO = ('remisiones', 'promedio_carga_kg', 'promedio_descarga_kg', 'peso_bascula_kg')

COLUMNAS = {
    'remision': ('Remisión', 'texto'),
    'fecha_descarga': ('Inicio de descarga', 'fecha'),
    'fecha': ('Fecha de captura', 'fecha'),
    'empresa': ('Unidad de negocio', 'texto'),
    'origen': ('Origen', 'texto'),
    'destino': ('Destino', 'texto'),
    'cliente': ('Cliente', 'texto'),
    'materiales': ('Material', 'texto'),
    'operador': ('Operador', 'texto'),
    'linea_transporte': ('Línea de transporte', 'texto'),
    'unidad': ('Unidad', 'texto'),
    'contenedor': ('Contenedor', 'texto'),
    'placas_unidad': ('Placas unidad', 'texto'),
    'placas_contenedor': ('Placas contenedor', 'texto'),
    'status': ('Estatus', 'estatus'),
    'folio_carga': ('Folio de carga', 'texto'),
    'folio_descarga': ('Folio de descarga', 'texto'),
    'folio_salida': ('Folio de salida', 'texto'),
    'folio_medline': ('Folio Medline', 'texto'),
    'inicia_carga': ('Inicia carga', 'fechahora'),
    'termina_carga': ('Termina carga', 'fechahora'),
    'inicia_descarga': ('Inicia descarga', 'fechahora'),
    'termina_descarga': ('Termina descarga', 'fechahora'),
    'hora_entrada': ('Hora de entrada', 'hora'),
    'hora_salida': ('Hora de salida', 'hora'),
    **{k: v for k, v in METRICAS.items() if k not in _SOLO_AGRUPADO},
    'tiempo_carga_h': ('Tiempo de carga (h)', 'horas'),
    'tiempo_descarga_h': ('Tiempo de descarga (h)', 'horas'),
    'tiempo_transito_h': ('Tránsito (h)', 'horas'),
    'dias_antiguedad': ('Días transcurridos', 'entero'),
    'peso_bascula': ('Peso báscula', 'kg'),
    'unidad_medida': ('Unidad de medida', 'texto'),
    'patio_rechazo': ('Patio de rechazo', 'texto'),
    'cliente_detalle': ('Cliente por material', 'texto'),
    'precio_kg': ('Precio por kg', 'dinero'),
    'factura': ('Factura', 'texto'),
    'facturas_cfdi': ('Facturas CFDI', 'texto'),
    'evidencias': ('Evidencias', 'entero'),
    'manifiesto': ('Manifiesto', 'sino'),
    'boleta_medline': ('Boleta de salida Medline', 'sino'),
    'fecha_destruccion': ('Fecha de destrucción', 'fecha'),
    'destruccion': ('Material destruido', 'texto'),
    'destruccion_completa': ('Destrucción fiscal completa', 'sino'),
    'comentarios_destruccion': ('Comentarios de destrucción', 'texto'),
    'descripcion': ('Descripción', 'texto'),
    'trazabilidad': ('Notas de trazabilidad', 'texto'),
    'comentario': ('Comentario', 'texto'),
    'auditado_por': ('Auditado por', 'texto'),
    'auditado_en': ('Fecha de auditoría', 'fechahora'),
    'creado_en': ('Registrada en el sistema', 'fechahora'),
    'actualizado_en': ('Última modificación', 'fechahora'),
    'ultimo_cambio': ('Último cambio (historial)', 'texto'),
}
COLUMNAS_DEFECTO = [
    'remision', 'fecha_descarga', 'empresa', 'origen', 'destino', 'materiales',
    'operador', 'carga_kg', 'descarga_kg', 'merma_pct', 'status',
]

# Orden de la lista: columna → expresión del ORM (las métricas son anotaciones).
ORDEN_LISTA = {
    'remision': 'remision', 'fecha_descarga': 'fecha_ref', 'fecha': 'fecha',
    'empresa': 'empresa__nombre', 'origen': 'origen__nombre', 'destino': 'destino__nombre',
    'cliente': 'cliente__nombre', 'operador': 'operador__nombre',
    'linea_transporte': 'linea_transporte__nombre', 'unidad': 'unidad__internal_id',
    'contenedor': 'contenedor__nombre', 'placas_unidad': 'placas_unidad_manual',
    'placas_contenedor': 'placas_contenedor_manual', 'status': 'status',
    'folio_carga': 'folio_ld', 'folio_descarga': 'folio_dlv', 'folio_salida': 'folio_salida',
    'folio_medline': 'folio_medline', 'inicia_carga': 'inicia_ld', 'termina_carga': 'termina_ld',
    'inicia_descarga': 'inicia_dlv', 'termina_descarga': 'termina_dlv',
    'hora_entrada': 'hora_entrada', 'hora_salida': 'hora_salida',
    'carga_kg': 'carga_kg', 'carga_ton': 'carga_kg', 'descarga_kg': 'descarga_kg',
    'descarga_ton': 'descarga_kg', 'rechazo_kg': 'rechazo_kg', 'rechazo_ton': 'rechazo_kg',
    'diferencia_kg': 'diferencia', 'merma_pct': 'merma', 'bultos': 'bultos_sum',
    'importe': 'importe', 'peso_bascula': 'peso_bascula',
    'tiempo_carga_h': 'dur_carga', 'tiempo_descarga_h': 'dur_descarga', 'tiempo_transito_h': 'dur_transito',
    'dias_antiguedad': 'antiguedad', 'factura': 'factura_nombre', 'fecha_destruccion': 'fecha_destruccion',
    'auditado_por': 'auditado_por__username', 'auditado_en': 'auditado_en',
    'creado_en': 'creado_en', 'actualizado_en': 'actualizado_en',
}

# Reportes de Excel con formato oficial que ya existen en Remisiones.
REPORTES_FORMALES = {
    'proboca': 'PROBOCA', 'sealed-air': 'SEALED AIR', 'huaxing': 'HUAXING',
    'bachoco': 'BACHOCO', 'trane': 'TRANE',
}

LIMITE_LISTA, LIMITE_LISTA_MAX = 50, 500
LIMITE_GRUPOS, LIMITE_GRUPOS_MAX = 100, 500
LIMITE_EXCEL = 5000
MAX_PREGUNTA = 500
PETICIONES_POR_VENTANA, VENTANA_SEG = 40, 600

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']
DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']


class ErrorReporte(Exception):
    def __init__(self, detalle, status=400):
        super().__init__(detalle)
        self.detalle, self.status = detalle, status


# ════════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ════════════════════════════════════════════════════════════════════════════

def _plano(s) -> str:
    """Minúsculas y sin acentos. Conserva dígitos, / y - (fechas y folios), %
    ("3% de abril" no es una fecha) y el punto decimal ("2.5 toneladas")."""
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'(\d),(\d{3})\b', r'\1\2', s)  # 20,000 → 20000
    s = re.sub(r'\.(?!\d)', ' ', s)            # punto final de frase fuera
    return ' '.join(re.sub(r'[^a-z0-9/%.\-\s]', ' ', s.lower()).split())


def _norm(s) -> str:
    """Para comparar nombres: minúsculas, sin acentos ni signos."""
    return ' '.join(re.sub(r'[^a-z0-9\s]', ' ', _plano(s)).split())


def _hoy() -> dt.date:
    return timezone.localdate()


def _fecha(valor):
    if isinstance(valor, dt.date):
        return valor
    try:
        return dt.date.fromisoformat(str(valor).strip()[:10])
    except (TypeError, ValueError):
        return None


def _fmt_fecha(d) -> str:
    return d.strftime('%d/%m/%Y') if d else ''


def _num(x, dec=2) -> str:
    return f'{x:,.{dec}f}'


def _peso(kg, en_ton=False) -> str:
    if en_ton:
        return f'{_num(kg / 1000, 2)} t'
    return f'{_num(kg, 2)} kg ({_num(kg / 1000, 2)} t)'


def _lista_str(valor, maximo=10, largo=80):
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, (list, tuple)):
        return []
    out = []
    for v in valor:
        v = str(v or '').strip()[:largo]
        if v and v not in out:
            out.append(v)
    return out[:maximo]


def _merma(carga, descarga, rechazo):
    return round((carga - (descarga + rechazo)) / carga * 100, 2) if carga > 0 else 0.0


def _empresas_permitidas(user):
    if user.is_superuser:
        return Empresa.objects.all()
    perfil = getattr(user, 'ternium_profile', None)
    return perfil.empresas_autorizadas.all() if perfil else Empresa.objects.none()


def puede_usar(user) -> bool:
    return user.is_superuser or user.has_perm('ternium.acceso_remisiones')


def _rango_mes(anio, mes):
    return dt.date(anio, mes, 1), dt.date(anio, mes, calendar.monthrange(anio, mes)[1])


def texto_periodo(desde, hasta) -> str:
    if not desde and not hasta:
        return 'todas las fechas'
    if desde and hasta:
        if desde == hasta:
            return f'el {_fmt_fecha(desde)}'
        if (desde.day == 1 and hasta == _rango_mes(hasta.year, hasta.month)[1]):
            if (desde.year, desde.month) == (hasta.year, hasta.month):
                return f'{MESES[desde.month - 1]} {desde.year}'
            if desde.month == 1 and hasta.month == 12 and desde.year == hasta.year:
                return f'el año {desde.year}'
        return f'del {_fmt_fecha(desde)} al {_fmt_fecha(hasta)}'
    return f'desde el {_fmt_fecha(desde)}' if desde else f'hasta el {_fmt_fecha(hasta)}'


# ════════════════════════════════════════════════════════════════════════════
# NORMALIZACIÓN (lo único que se ejecuta es lo que pasa por aquí)
# ════════════════════════════════════════════════════════════════════════════

def normalizar(cruda) -> dict:
    c = cruda if isinstance(cruda, dict) else {}
    f = c.get('filtros') if isinstance(c.get('filtros'), dict) else {}

    tipo = c.get('tipo') if c.get('tipo') in TIPOS else 'lista'
    filtros = {}

    desde, hasta = _fecha(f.get('fecha_desde')), _fecha(f.get('fecha_hasta'))
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde
    filtros['fecha_desde'] = desde.isoformat() if desde else None
    filtros['fecha_hasta'] = hasta.isoformat() if hasta else None
    filtros['campo_fecha'] = f.get('campo_fecha') if f.get('campo_fecha') in CAMPOS_FECHA else 'descarga'

    for clave in CATALOGOS:
        valores = _lista_str(f.get(clave))
        if valores:
            filtros[clave] = valores

    status = [s for s in (str(x).upper() for x in _lista_str(f.get('status'))) if s in STATUS]
    if status:
        filtros['status'] = status

    for clave in TEXTOS:
        valor = ' '.join(str(f.get(clave) or '').split())[:80]
        if valor:
            filtros[clave] = valor

    for clave in RANGOS:
        for limite_clave in (f'{clave}_min', f'{clave}_max'):
            try:
                if f.get(limite_clave) not in (None, ''):
                    filtros[limite_clave] = max(-1e9, min(1e9, float(f.get(limite_clave))))
            except (TypeError, ValueError):
                pass

    for clave in SI_NO:
        valor = f.get(clave)
        if isinstance(valor, str):
            valor = {'si': True, 'sí': True, 'true': True, 'no': False, 'false': False}.get(valor.strip().lower())
        if isinstance(valor, bool):
            filtros[clave] = valor

    agrupar = [d for d in _lista_str(c.get('agrupar_por'), maximo=4) if d in DIMENSIONES][:2]
    if tipo == 'lista' and agrupar:
        tipo = 'agrupado'
    if tipo == 'agrupado' and not agrupar:
        tipo = 'total'

    metricas = [m for m in _lista_str(c.get('metricas'), maximo=17) if m in METRICAS]
    if tipo == 'agrupado' and 'remisiones' not in metricas:
        metricas.insert(0, 'remisiones')
    if not metricas or metricas == ['remisiones']:
        metricas = list(METRICAS_DEFECTO)

    columnas = [k for k in _lista_str(c.get('columnas'), maximo=len(COLUMNAS)) if k in COLUMNAS]
    if not columnas:
        columnas = list(COLUMNAS_DEFECTO)
        if any(m.endswith('_ton') for m in metricas):
            columnas = [k.replace('_kg', '_ton') for k in columnas]
        if filtros.get('folio_salida'):
            columnas.insert(1, 'folio_salida')
    if 'remision' not in columnas:
        columnas.insert(0, 'remision')

    orden = None
    o = c.get('orden') if isinstance(c.get('orden'), dict) else {}
    campo = str(o.get('campo') or '').strip()
    validos = (ORDEN_LISTA if tipo == 'lista' else {**METRICAS, **DIMENSIONES})
    if campo in validos:
        orden = {'campo': campo, 'dir': 'asc' if o.get('dir') == 'asc' else 'desc'}

    maximo = LIMITE_LISTA_MAX if tipo == 'lista' else LIMITE_GRUPOS_MAX
    defecto = LIMITE_LISTA if tipo == 'lista' else LIMITE_GRUPOS
    try:
        limite = int(c.get('limite') or defecto)
    except (TypeError, ValueError):
        limite = defecto
    limite = max(1, min(limite, maximo))

    formal = c.get('reporte_formal')
    formal = formal.get('tipo') if isinstance(formal, dict) else formal
    formal = formal if formal in REPORTES_FORMALES else None

    return {
        'tipo': tipo,
        'titulo': str(c.get('titulo') or '').strip()[:120],
        'mensaje': str(c.get('mensaje') or '').strip()[:1200],
        'filtros': filtros,
        'agrupar_por': agrupar if tipo == 'agrupado' else [],
        'metricas': metricas,
        'columnas': columnas,
        'orden': orden,
        'limite': limite,
        'reporte_formal': formal,
    }


# ════════════════════════════════════════════════════════════════════════════
# RESOLUCIÓN DE NOMBRES (tolerante a acentos, mayúsculas y errores de dictado)
# ════════════════════════════════════════════════════════════════════════════

def _indice(clave, user):
    _, modelo, campo, _, _ = CATALOGOS[clave]
    qs = _empresas_permitidas(user) if clave == 'empresa' else modelo.objects.all()
    return [(pk, nombre, _norm(nombre)) for pk, nombre in qs.values_list('pk', campo) if nombre]


def _buscar(termino, indice):
    """IDs del catálogo que corresponden a `termino`."""
    t = _norm(termino)
    if not t:
        return set()
    hits = {pk for pk, _, n in indice if t in n or (len(n) >= 4 and n in t)}
    if hits:
        return hits
    nombres = [n for _, _, n in indice]
    cercanos = set(difflib.get_close_matches(t, nombres, n=3, cutoff=0.82))
    if cercanos:
        return {pk for pk, _, n in indice if n in cercanos}
    if ' ' not in t and len(t) >= 4:
        # Una sola palabra mal dictada: "huaxin" → "HUAXING ..."
        return {pk for pk, _, n in indice
                if any(difflib.SequenceMatcher(None, t, w).ratio() >= 0.85 for w in n.split())}
    return set()


def _resolver(filtros, user):
    """Convierte los nombres de los filtros a IDs. Devuelve (ids por clave,
    nombres encontrados por clave, avisos, filtros efectivos). Los filtros
    efectivos difieren de los pedidos cuando un nombre dado como empresa
    resultó ser un lugar y se movió a origen."""
    efectivos = copy.deepcopy(filtros)
    ids, nombres, avisos = {}, {}, []
    if efectivos.get('empresa'):
        # Muchos clientes (HUAXING, BACHOCO, TRANE…) son orígenes, no unidades
        # de negocio: si el nombre no es empresa pero sí lugar, va a origen.
        empresas, lugares = _indice('empresa', user), _indice('origen', user)
        for t in list(efectivos['empresa']):
            if not _buscar(t, empresas) and _buscar(t, lugares):
                efectivos['empresa'].remove(t)
                efectivos.setdefault('origen', []).append(t)
                avisos.append(f'"{t}" no es una unidad de negocio; lo tomé como origen.')
        if not efectivos['empresa']:
            del efectivos['empresa']

    for clave, (etiqueta, _, _, _, manual) in CATALOGOS.items():
        terminos = efectivos.get(clave)
        if not terminos:
            continue
        indice = _indice(clave, user)
        encontrados = set()
        for t in terminos:
            hits = _buscar(t, indice)
            encontrados |= hits
            if hits or manual:
                continue  # con texto libre también se busca lo capturado a mano
            if clave == 'empresa':
                avisos.append(f'No encontré la unidad de negocio "{t}" entre las que tienes autorizadas.')
            else:
                avisos.append(f'No encontré {etiqueta.lower()} "{t}" en el catálogo.')
        ids[clave] = encontrados
        nombres[clave] = [n for pk, n, _ in indice if pk in encontrados]
    return ids, nombres, avisos, efectivos


# ════════════════════════════════════════════════════════════════════════════
# EJECUCIÓN
# ════════════════════════════════════════════════════════════════════════════

def _expr_fecha(campo_fecha, p=''):
    """Fecha del periodo. `p` es el prefijo hacia Remision ('' o 'remision__')."""
    if campo_fecha == 'captura':
        return F(p + 'fecha')
    if campo_fecha == 'auditoria':
        return TruncDate(p + 'auditado_en')
    if campo_fecha == 'registro':
        return TruncDate(p + 'creado_en')
    if campo_fecha == 'destruccion':
        return F(p + 'fecha_destruccion')
    base = 'inicia_ld' if campo_fecha == 'carga' else 'inicia_dlv'
    return Coalesce(TruncDate(p + base), F(p + 'fecha'), output_field=DateField())


def _expr_dimension(dim, p_rem='', p_det='detalles__'):
    """Expresión para agrupar. `p_rem` lleva a Remision y `p_det` a sus líneas
    de material: ('', 'detalles__') desde Remision y ('remision__', '') desde
    DetalleRemision. Las dimensiones de tiempo usan la anotación `fecha_ref`."""
    if dim in DIM_DETALLE:
        return Coalesce(F(p_det + DIM_DETALLE[dim]), Value(''))
    if dim == 'status':
        return F(p_rem + 'status')
    if dim == 'auditado_por':
        return Coalesce(F(p_rem + 'auditado_por__username'), Value(''))
    if dim == 'dia':
        return F('fecha_ref')
    if dim == 'semana':
        return TruncWeek('fecha_ref', output_field=DateField())
    if dim == 'mes':
        return TruncMonth('fecha_ref', output_field=DateField())
    if dim == 'anio':
        return TruncYear('fecha_ref', output_field=DateField())
    if dim == 'dia_semana':
        return ExtractIsoWeekDay('fecha_ref')
    _, _, campo, ruta, manual = CATALOGOS[dim]
    partes = [F(f'{p_rem}{ruta}__{campo}')]
    if manual:
        partes.append(F(p_rem + manual))
    return Coalesce(*partes, Value(''))


def _suma(campo, filtro=None):
    return Coalesce(Cast(Sum(campo, filter=filtro), FloatField()), Value(0.0))


def _duracion(fin, inicio, p=''):
    return ExpressionWrapper(F(p + fin) - F(p + inicio), output_field=DurationField())


def _prom_duracion(fin, inicio, p=''):
    """Promedio de (fin - inicio), ignorando registros sin datos o al revés."""
    return Avg(_duracion(fin, inicio, p), filter=Q(**{f'{p}{fin}__gt': F(p + inicio)}))


def _horas(valor):
    """timedelta (o microsegundos) → horas con 2 decimales."""
    if valor in (None, ''):
        return None
    segundos = valor.total_seconds() if isinstance(valor, dt.timedelta) else float(valor) / 1e6
    return round(segundos / 3600, 2) if segundos > 0 else None


def _etiqueta_dimension(dim, valor, usuarios=None):
    if dim == 'dia_semana':
        return DIAS[valor - 1].capitalize() if valor else '(sin fecha)'
    if dim in DIMENSIONES_TIEMPO:
        if not valor:
            return '(sin fecha)'
        if dim == 'dia':
            return _fmt_fecha(valor)
        if dim == 'semana':
            return f'Semana del {_fmt_fecha(valor)}'
        if dim == 'mes':
            return f'{MESES[valor.month - 1].capitalize()} {valor.year}'
        return str(valor.year)
    if dim == 'status':
        return STATUS.get(valor, valor or '')
    if dim == 'auditado_por':
        return (usuarios or {}).get(valor) or valor or '(sin auditar)'
    return valor or f'(sin {DIMENSIONES[dim].lower()})'


def _metricas_fila(n, carga, descarga, rechazo, bultos, importe=0.0, bascula=0.0,
                   t_carga=None, t_descarga=None, t_transito=None):
    return {
        'remisiones': n,
        'carga_kg': round(carga, 3), 'descarga_kg': round(descarga, 3),
        'rechazo_kg': round(rechazo, 3),
        'diferencia_kg': round(descarga + rechazo - carga, 3),
        'merma_pct': _merma(carga, descarga, rechazo),
        'carga_ton': round(carga / 1000, 3), 'descarga_ton': round(descarga / 1000, 3),
        'rechazo_ton': round(rechazo / 1000, 3),
        'bultos': int(bultos or 0),
        'promedio_carga_kg': round(carga / n, 3) if n else 0.0,
        'promedio_descarga_kg': round(descarga / n, 3) if n else 0.0,
        'importe': round(float(importe or 0), 2),
        'peso_bascula_kg': round(float(bascula or 0), 3),
        'tiempo_carga_h': _horas(t_carga),
        'tiempo_descarga_h': _horas(t_descarga),
        'tiempo_transito_h': _horas(t_transito),
    }


def _texto_filtros(f, nombres):
    desde, hasta = _fecha(f.get('fecha_desde')), _fecha(f.get('fecha_hasta'))
    chips = [f'Periodo: {texto_periodo(desde, hasta)} · {CAMPOS_FECHA[f["campo_fecha"]]}']
    for clave, (etiqueta, *_resto) in CATALOGOS.items():
        if clave in nombres and nombres[clave]:
            vals = sorted(set(nombres[clave]))
            txt = ', '.join(vals[:3]) + (f' y {len(vals) - 3} más' if len(vals) > 3 else '')
            chips.append(f'{etiqueta}: {txt}')
        elif f.get(clave):
            chips.append(f'{etiqueta}: {", ".join(f[clave])}')
    if f.get('status'):
        chips.append('Estatus: ' + ', '.join(STATUS[s] for s in f['status']))
    else:
        chips.append('Sin canceladas')
    for clave, (etiqueta, _) in TEXTOS.items():
        if f.get(clave):
            chips.append(f'{etiqueta} contiene "{f[clave]}"')
    for clave, (etiqueta, unidad) in RANGOS.items():
        for sufijo, signo in (('_min', '≥'), ('_max', '≤')):
            if f.get(clave + sufijo) is not None:
                chips.append(f'{etiqueta} {signo} {_num(f[clave + sufijo], 2 if unidad != "días" else 0)} {unidad}')
    for clave, (si, no) in SI_NO.items():
        if clave in f:
            chips.append(si if f[clave] else no)
    return chips


def _reporte_formal(c, nombres):
    """Si la consulta coincide con un reporte oficial de Remisiones, devuelve
    cómo descargarlo (mismos parámetros que el centro de reportes)."""
    tipo = c.get('reporte_formal')
    if not tipo:
        empresas = nombres.get('empresa') or []
        origenes = [_norm(n) for n in nombres.get('origen') or []]
        if empresas and all(es_proboca(n) for n in empresas):
            tipo = 'proboca'
        elif empresas and all(es_sealed_air(n) for n in empresas):
            tipo = 'sealed-air'
        else:
            for clave in ('huaxing', 'bachoco', 'trane'):
                if origenes and all(clave in n for n in origenes):
                    tipo = clave
    if not tipo:
        return None
    f = c['filtros']
    desde, hasta = _fecha(f.get('fecha_desde')), _fecha(f.get('fecha_hasta'))
    params = {'tipo_reporte': tipo}
    if desde and hasta and desde.day == 1 and (desde.year, desde.month) == (hasta.year, hasta.month) \
            and hasta == _rango_mes(hasta.year, hasta.month)[1]:
        params.update(tipo_filtro='mes', mes=f'{desde.year}-{desde.month:02d}')
    else:
        params.update(tipo_filtro='rango', fecha_inicio=f.get('fecha_desde') or '',
                      fecha_fin=f.get('fecha_hasta') or '')
    from urllib.parse import urlencode
    return {
        'tipo': tipo,
        'etiqueta': f'Reporte {REPORTES_FORMALES[tipo]} (formato oficial)',
        'ruta': '/remisiones/exportar-especificos/?' + urlencode(params),
    }


def _facturas_vigentes():
    """Facturas CFDI no canceladas (módulo de facturación), o None si no está."""
    try:
        from facturacion.models import Factura
        return Factura.objects.exclude(estado='cancelada')
    except Exception:
        return None


def _destruccion_completa_q():
    """Mismo criterio que el filtro de destrucción fiscal de Remisiones."""
    return (Q(fecha_destruccion__isnull=False, destruccion_material_1__isnull=False,
              foto_ingreso__isnull=False, foto_vertido__isnull=False, foto_destruccion__isnull=False)
            & ~Q(destruccion_material_1='') & ~Q(foto_ingreso='') & ~Q(foto_vertido='')
            & ~Q(foto_destruccion=''))


def _filtro_si_no(qs, clave, valor):
    if clave == 'destruccion_completa':
        completa = _destruccion_completa_q()
        if valor:
            return qs.filter(completa)
        # Pendiente = la requiere (origen + material configurados) y no está completa
        requiere = Q()
        for conf in ConfiguracionManifiesto.objects.all():
            requiere |= Q(origen_id=conf.origen_id, detalles__material_id=conf.material_id)
        return qs.filter(requiere).exclude(completa) if requiere else qs.none()

    if clave == 'con_rechazo':
        cond = Q(pk__in=DetalleRemision.objects.filter(peso_rechazado__gt=0).values('remision'))
    elif clave == 'con_factura':
        cond = Q(factura_nombre__gt='')
        facturas = _facturas_vigentes()
        if facturas is not None:
            cond |= Q(pk__in=facturas.values('remisiones'))
    elif clave == 'con_evidencia':
        cond = Q(pk__in=EvidenciaRemision.objects.values('remision')) | Q(evidencia_documento__gt='')
    elif clave == 'con_manifiesto':
        cond = Q(manifiesto__gt='')
    elif clave == 'con_descarga':
        cond = Q(inicia_dlv__isnull=False)
    else:  # con_folio_salida
        cond = Q(folio_salida__gt='')
    return qs.filter(cond) if valor else qs.exclude(cond)


def ejecutar(c, user, para_excel=False) -> dict:
    ids, nombres, avisos, f = _resolver(c['filtros'], user)

    qs = Remision.objects.all()
    if not user.is_superuser:
        qs = qs.filter(empresa__in=_empresas_permitidas(user))

    # Fechas (las de reporte: inicio de descarga, salvo que pidan otra)
    qs = qs.annotate(fecha_ref=_expr_fecha(f['campo_fecha']))
    if f.get('fecha_desde'):
        qs = qs.filter(fecha_ref__gte=f['fecha_desde'])
    if f.get('fecha_hasta'):
        qs = qs.filter(fecha_ref__lte=f['fecha_hasta'])

    mat_ids = None
    for clave, (_, _, _, ruta, manual) in CATALOGOS.items():
        if not f.get(clave):
            continue
        encontrados = ids.get(clave) or set()
        if clave == 'material':
            mat_ids = encontrados
            qs = qs.filter(detalles__material_id__in=encontrados)
            continue
        cond = Q(**{f'{ruta}_id__in': encontrados})
        if manual:
            for t in f[clave]:
                cond |= Q(**{f'{manual}__icontains': t})
        qs = qs.filter(cond)

    qs = qs.filter(status__in=f['status']) if f.get('status') else qs.exclude(status='CANCELADO')
    for clave, (_, campos) in TEXTOS.items():
        if not f.get(clave):
            continue
        # "Juan Pérez" en auditado_por: cada palabra en nombre, apellido o usuario
        partes = f[clave].split() if clave == 'auditado_por' else [f[clave]]
        for parte in partes:
            cond = Q()
            for campo in campos:
                cond |= Q(**{f'{campo}__icontains': parte})
            qs = qs.filter(cond)
    for clave in SI_NO:
        if clave in f:
            qs = _filtro_si_no(qs, clave, f[clave])
    hoy = _hoy()
    if f.get('antiguedad_min') is not None:
        qs = qs.filter(fecha_ref__lte=hoy - dt.timedelta(days=int(f['antiguedad_min'])))
    if f.get('antiguedad_max') is not None:
        qs = qs.filter(fecha_ref__gte=hoy - dt.timedelta(days=int(f['antiguedad_max'])))

    # A partir de aquí se trabaja con los IDs (sin joins duplicados).
    filtro_mat_r = Q(detalles__material_id__in=mat_ids) if mat_ids is not None else None
    sumas_r = {
        'carga_kg': _suma('detalles__peso_ld', filtro_mat_r),
        'descarga_kg': _suma('detalles__peso_dlv', filtro_mat_r),
        'rechazo_kg': _suma('detalles__peso_rechazado', filtro_mat_r),
    }
    merma_expr = Case(
        When(carga_kg__gt=0, then=(F('carga_kg') - F('descarga_kg') - F('rechazo_kg')) * Value(100.0) / F('carga_kg')),
        default=Value(0.0), output_field=FloatField(),
    )
    ids_sub = qs.values('pk')
    rangos_peso = {'merma': 'merma', 'carga': 'carga_kg', 'descarga': 'descarga_kg'}
    if any(f.get(f'{k}_{s}') is not None for k in rangos_peso for s in ('min', 'max')):
        con_pesos = Remision.objects.filter(pk__in=ids_sub).annotate(**sumas_r).annotate(merma=merma_expr)
        for clave, anotacion in rangos_peso.items():
            if f.get(f'{clave}_min') is not None:
                con_pesos = con_pesos.filter(**{f'{anotacion}__gte': f[f'{clave}_min']})
            if f.get(f'{clave}_max') is not None:
                con_pesos = con_pesos.filter(**{f'{anotacion}__lte': f[f'{clave}_max']})
        ids_sub = con_pesos.values('pk')

    remisiones = Remision.objects.filter(pk__in=ids_sub)
    detalles = DetalleRemision.objects.filter(remision__in=ids_sub)
    if mat_ids is not None:
        detalles = detalles.filter(material_id__in=mat_ids)

    tot = detalles.aggregate(c=_suma('peso_ld'), d=_suma('peso_dlv'), r=_suma('peso_rechazado'),
                             b=Coalesce(Sum('bultos'), Value(0)), i=_suma(F('peso_dlv') * F('precio')))
    tot_r = remisiones.aggregate(
        n=Count('pk'), bascula=_suma('peso_bascula'),
        tc=_prom_duracion('termina_ld', 'inicia_ld'), td=_prom_duracion('termina_dlv', 'inicia_dlv'),
        tt=_prom_duracion('inicia_dlv', 'termina_ld'),
    )
    n_total = tot_r['n']
    resumen = _metricas_fila(n_total, tot['c'], tot['d'], tot['r'], tot['b'], tot['i'],
                             tot_r['bascula'], tot_r['tc'], tot_r['td'], tot_r['tt'])

    resultado = {
        'tipo': c['tipo'],
        'titulo': c['titulo'] or 'Reporte de remisiones',
        'avisos': avisos,
        'filtros_texto': _texto_filtros(f, nombres),
        'resumen': resumen,
        'tabla': None,
        'reporte_formal': _reporte_formal(c, nombres),
    }

    if c['tipo'] == 'lista':
        resultado['tabla'] = _tabla_lista(c, remisiones, sumas_r, merma_expr, mat_ids, resumen,
                                          LIMITE_EXCEL if para_excel else c['limite'])
    elif c['tipo'] == 'agrupado':
        resultado['tabla'] = _tabla_agrupada(c, remisiones, detalles, resumen,
                                             LIMITE_EXCEL if para_excel else c['limite'])
    return resultado


def _unicos(valores):
    out = []
    for v in valores:
        if v not in (None, '') and v not in out:
            out.append(v)
    return out


def _tabla_lista(c, remisiones, sumas_r, merma_expr, mat_ids, resumen, limite):
    f = c['filtros']
    cols = set(c['columnas'])
    filtro_mat = Q(detalles__material_id__in=mat_ids) if mat_ids is not None else None
    qs = (remisiones
          .select_related('empresa', 'origen', 'destino', 'cliente', 'operador',
                          'linea_transporte', 'unidad', 'contenedor', 'auditado_por')
          .annotate(fecha_ref=_expr_fecha(f['campo_fecha']), **sumas_r,
                    bultos_sum=Coalesce(Sum('detalles__bultos', filter=filtro_mat), Value(0)),
                    importe=_suma(F('detalles__peso_dlv') * F('detalles__precio'), filtro_mat),
                    dur_carga=_duracion('termina_ld', 'inicia_ld'),
                    dur_descarga=_duracion('termina_dlv', 'inicia_dlv'),
                    dur_transito=_duracion('inicia_dlv', 'termina_ld'))
          .annotate(merma=merma_expr,
                    diferencia=F('descarga_kg') + F('rechazo_kg') - F('carga_kg'))
          .prefetch_related(Prefetch('detalles', queryset=DetalleRemision.objects.select_related(
              'material', 'patio_rechazo', 'cliente'))))
    # Relaciones extra solo si se pidieron esas columnas
    if 'evidencias' in cols:
        qs = qs.prefetch_related('evidencias')
    if 'facturas_cfdi' in cols and _facturas_vigentes() is not None:
        qs = qs.prefetch_related('facturas')
    if 'ultimo_cambio' in cols:
        qs = qs.prefetch_related(Prefetch('historial', queryset=HistorialRemision.objects.select_related('usuario')))

    o = c['orden']
    if o:
        campo, desc = ORDEN_LISTA[o['campo']], o['dir'] == 'desc'
        if campo == 'antiguedad':  # más días = fecha más antigua
            campo, desc = 'fecha_ref', not desc
        qs = qs.order_by(F(campo).desc(nulls_last=True) if desc else F(campo).asc(nulls_last=True), '-pk')
    else:
        qs = qs.order_by('-fecha_ref', '-pk')

    def nombre(obj, campo='nombre'):
        return getattr(obj, campo, '') if obj else ''

    def horas(fin, inicio):
        return _horas(fin - inicio) if fin and inicio else None

    hoy = _hoy()
    filas = []
    for r in qs[:limite]:
        dets = [d for d in r.detalles.all() if mat_ids is None or d.material_id in mat_ids]
        con_precio = [d for d in dets if d.precio is not None]
        kg_precio = sum(float(d.peso_dlv or 0) for d in con_precio)
        carga, descarga, rechazo = float(r.carga_kg or 0), float(r.descarga_kg or 0), float(r.rechazo_kg or 0)
        m = _metricas_fila(1, carga, descarga, rechazo, r.bultos_sum, r.importe)
        aud = r.auditado_por
        valores = {
            'remision': r.remision,
            'fecha_descarga': r.fecha_ref,
            'fecha': r.fecha,
            'empresa': nombre(r.empresa),
            'origen': nombre(r.origen),
            'destino': nombre(r.destino),
            'cliente': nombre(r.cliente),
            'materiales': ', '.join(_unicos(d.material.nombre if d.material else '' for d in dets)),
            'operador': nombre(r.operador) or (r.operador_manual or ''),
            'linea_transporte': nombre(r.linea_transporte),
            'unidad': nombre(r.unidad, 'internal_id') or (r.unidad_manual or ''),
            'contenedor': nombre(r.contenedor) or (r.contenedor_manual or ''),
            'placas_unidad': r.placas_unidad_manual or nombre(r.unidad, 'license_plate') or '',
            'placas_contenedor': r.placas_contenedor_manual or nombre(r.contenedor, 'placas') or '',
            'status': r.status,
            'folio_carga': r.folio_ld or '',
            'folio_descarga': r.folio_dlv or '',
            'folio_salida': r.folio_salida or '',
            'folio_medline': r.folio_medline or '',
            'inicia_carga': r.inicia_ld, 'termina_carga': r.termina_ld,
            'inicia_descarga': r.inicia_dlv, 'termina_descarga': r.termina_dlv,
            'hora_entrada': r.hora_entrada, 'hora_salida': r.hora_salida,
            **{k: v for k, v in m.items() if k not in _SOLO_AGRUPADO},
            'tiempo_carga_h': horas(r.termina_ld, r.inicia_ld),
            'tiempo_descarga_h': horas(r.termina_dlv, r.inicia_dlv),
            'tiempo_transito_h': horas(r.inicia_dlv, r.termina_ld),
            'dias_antiguedad': (hoy - r.fecha_ref).days if r.fecha_ref else None,
            'peso_bascula': float(r.peso_bascula) if r.peso_bascula is not None else None,
            'unidad_medida': ', '.join(_unicos(d.get_unidad_medida_display() for d in dets)),
            'patio_rechazo': ', '.join(_unicos(nombre(d.patio_rechazo) for d in dets)),
            'cliente_detalle': ', '.join(_unicos(nombre(d.cliente) for d in dets)),
            # Precio por kg: el de la remisión, o el promedio ponderado si trae varios
            'precio_kg': (round(float(r.importe or 0) / kg_precio, 4) if kg_precio
                          else (float(con_precio[0].precio) if con_precio else None)),
            'factura': r.factura_nombre or '',
            'facturas_cfdi': (', '.join(
                f'{fa.serie or ""}{"-" if fa.serie else ""}{fa.folio or fa.pk}'
                + (' (cancelada)' if fa.estado == 'cancelada' else '')
                for fa in r.facturas.all()) if 'facturas_cfdi' in cols and _facturas_vigentes() is not None else ''),
            'evidencias': (len(r.evidencias.all()) + (1 if r.evidencia_documento else 0)) if 'evidencias' in cols else None,
            'manifiesto': bool(r.manifiesto),
            'boleta_medline': bool(r.boleta_salida_medline),
            'fecha_destruccion': r.fecha_destruccion,
            'destruccion': '; '.join(
                f'{mat} ({_num(float(peso), 2)} kg)' if peso is not None else mat
                for mat, peso in ((r.destruccion_material_1, r.destruccion_peso_1),
                                  (r.destruccion_material_2, r.destruccion_peso_2)) if mat),
            'destruccion_completa': r.destruccion_fiscal_completa,
            'comentarios_destruccion': (r.comentarios_destruccion or '')[:300],
            'descripcion': (r.descripcion or '')[:300],
            'trazabilidad': (r.trazabilidad_notas or '')[:300],
            'comentario': (r.comentario or '')[:300],
            'auditado_por': (aud.get_full_name() or aud.username) if aud else '',
            'auditado_en': r.auditado_en,
            'creado_en': r.creado_en,
            'actualizado_en': r.actualizado_en,
            'ultimo_cambio': next((
                f'{timezone.localtime(h.fecha).strftime("%d/%m/%Y %H:%M")} · '
                f'{(h.usuario.get_full_name() or h.usuario.username) if h.usuario else "Sistema"}: {h.cambio[:150]}'
                for h in r.historial.all()), '') if 'ultimo_cambio' in cols else '',
        }
        fila = {k: valores[k] for k in c['columnas']}
        fila['_id'] = r.pk
        filas.append(fila)

    columnas = [{'clave': k, 'titulo': COLUMNAS[k][0], 'tipo': COLUMNAS[k][1]} for k in c['columnas']]
    totales = {k: resumen[k] for k in c['columnas'] if k in METRICAS}
    return {'columnas': columnas, 'filas': filas, 'total_filas': resumen['remisiones'],
            'mostradas': len(filas), 'totales': totales}


def _tabla_agrupada(c, remisiones, detalles, resumen, limite):
    f = c['filtros']
    dims = c['agrupar_por']
    claves = [f'g_{d}' for d in dims]
    tiempo = any(d in DIMENSIONES_TIEMPO for d in dims)

    # Pesos, bultos e importe: desde las líneas de material.
    d_qs = detalles
    if tiempo:
        d_qs = d_qs.annotate(fecha_ref=_expr_fecha(f['campo_fecha'], 'remision__'))
    # Agrupar por algo de las líneas (material, patio de rechazo): todo sale de
    # las líneas ya filtradas. Si no, el conteo, la báscula y los tiempos salen
    # de las remisiones (así cuentan también las que no tienen líneas).
    por_linea = any(d in DIM_DETALLE for d in dims)
    de_remision = {
        'n': Count('remision', distinct=True), 'bascula': _suma('remision__peso_bascula'),
        'tc': _prom_duracion('termina_ld', 'inicia_ld', 'remision__'),
        'td': _prom_duracion('termina_dlv', 'inicia_dlv', 'remision__'),
        'tt': _prom_duracion('inicia_dlv', 'termina_ld', 'remision__'),
    } if por_linea else {}
    d_qs = (d_qs.annotate(**{k: _expr_dimension(d, 'remision__', '') for k, d in zip(claves, dims)})
            .values(*claves)
            .annotate(carga=_suma('peso_ld'), descarga=_suma('peso_dlv'),
                      rechazo=_suma('peso_rechazado'), bultos=Coalesce(Sum('bultos'), Value(0)),
                      importe=_suma(F('peso_dlv') * F('precio')), **de_remision)
            .order_by())
    vacio = {'n': 0, 'carga': 0.0, 'descarga': 0.0, 'rechazo': 0.0, 'bultos': 0, 'importe': 0.0,
             'bascula': 0.0, 'tc': None, 'td': None, 'tt': None}
    grupos = {}
    for row in d_qs:
        g = grupos.setdefault(tuple(row[k] for k in claves), dict(vacio))
        g.update(carga=float(row['carga']), descarga=float(row['descarga']), rechazo=float(row['rechazo']),
                 bultos=row['bultos'], importe=float(row['importe']))
        if por_linea:
            g.update(n=row['n'], bascula=float(row['bascula']), tc=row['tc'], td=row['td'], tt=row['tt'])

    if not por_linea:
        r_qs = remisiones
        if tiempo:
            r_qs = r_qs.annotate(fecha_ref=_expr_fecha(f['campo_fecha']))
        r_qs = (r_qs.annotate(**{k: _expr_dimension(d) for k, d in zip(claves, dims)})
                .values(*claves)
                .annotate(n=Count('pk', distinct=True), bascula=_suma('peso_bascula'),
                          tc=_prom_duracion('termina_ld', 'inicia_ld'),
                          td=_prom_duracion('termina_dlv', 'inicia_dlv'),
                          tt=_prom_duracion('inicia_dlv', 'termina_ld'))
                .order_by())
        for row in r_qs:
            g = grupos.setdefault(tuple(row[k] for k in claves), dict(vacio))
            g.update(n=row['n'], bascula=float(row['bascula']), tc=row['tc'], td=row['td'], tt=row['tt'])

    usuarios = {}
    if 'auditado_por' in dims:
        i = dims.index('auditado_por')
        usuarios = {u.username: (u.get_full_name() or u.username)
                    for u in User.objects.filter(username__in={k[i] for k in grupos if k[i]})}

    filas = []
    for llave, g in grupos.items():
        fila = {'_orden': llave}
        for k, d, v in zip(claves, dims, llave):
            fila[k] = _etiqueta_dimension(d, v, usuarios)
        fila.update(_metricas_fila(g['n'], g['carga'], g['descarga'], g['rechazo'], g['bultos'],
                                   g['importe'], g['bascula'], g['tc'], g['td'], g['tt']))
        filas.append(fila)

    def clave_dim(v):  # vacíos al final; mismo tipo dentro de cada dimensión
        return (v in (None, ''), v if v not in (None, '') else '')

    o = c['orden']
    if o and o['campo'] in METRICAS:
        desc = o['dir'] == 'desc'
        vacio_al_final = float('-inf') if desc else float('inf')  # métricas sin dato (tiempos) al final
        filas.sort(key=lambda x: vacio_al_final if x[o['campo']] is None else x[o['campo']], reverse=desc)
    elif o and o['campo'] in dims:
        i = dims.index(o['campo'])
        filas.sort(key=lambda x: clave_dim(x['_orden'][i]), reverse=o['dir'] == 'desc')
    elif dims[0] in DIMENSIONES_TIEMPO:
        filas.sort(key=lambda x: tuple(clave_dim(v) for v in x['_orden']))
    else:
        principal = next((m for m in ('descarga_kg', 'descarga_ton', 'carga_kg', 'carga_ton')
                          if m in c['metricas']), 'remisiones')
        filas.sort(key=lambda x: x[principal], reverse=True)

    total_grupos = len(filas)
    if tiempo and not o:
        limite = max(limite, 400)  # una serie de tiempo se muestra completa
    filas = filas[:limite]
    for fila in filas:
        fila.pop('_orden', None)

    columnas = [{'clave': k, 'titulo': DIMENSIONES[d], 'tipo': 'texto'} for k, d in zip(claves, dims)]
    columnas += [{'clave': m, 'titulo': METRICAS[m][0], 'tipo': METRICAS[m][1]} for m in c['metricas']]
    filas = [{k: fila[k] for k in [col['clave'] for col in columnas]} for fila in filas]
    totales = {m: resumen[m] for m in c['metricas']}
    return {'columnas': columnas, 'filas': filas, 'total_filas': total_grupos,
            'mostradas': len(filas), 'totales': totales}


# ════════════════════════════════════════════════════════════════════════════
# RESPUESTA EN LENGUAJE NATURAL (con las cifras de la base de datos)
# ════════════════════════════════════════════════════════════════════════════

def redactar(c, res) -> str:
    r = res['resumen']
    n = r['remisiones']
    f = c['filtros']
    en_ton = any(m.endswith('_ton') for m in c['metricas'] + (c['columnas'] if c['tipo'] == 'lista' else []))
    periodo = texto_periodo(_fecha(f.get('fecha_desde')), _fecha(f.get('fecha_hasta')))

    if n == 0:
        return ('No encontré remisiones con esos filtros '
                f'({periodo}). Prueba con otro periodo o quita algún filtro.')

    plural = 'remisión' if n == 1 else 'remisiones'
    partes = [f'Encontré **{_num(n, 0)} {plural}** ({periodo}).']
    if r['carga_kg'] or r['descarga_kg']:
        txt = f'Carga: **{_peso(r["carga_kg"], en_ton)}** · Descarga: **{_peso(r["descarga_kg"], en_ton)}**'
        if r['rechazo_kg']:
            txt += f' · Rechazo: **{_peso(r["rechazo_kg"], en_ton)}**'
        txt += f' · Merma: **{_num(r["merma_pct"], 2)} %**.'
        partes.append(txt)
    # Otras métricas pedidas (importe, promedios, tiempos, báscula)
    extras = [m for m in c['metricas'] if m in _METRICAS_EXTRA and r.get(m) is not None]
    if r.get('importe') and 'importe' not in extras:
        extras.insert(0, 'importe')
    if extras:
        partes.append(' · '.join(f'{METRICAS[m][0]}: **{_valor_txt(m, r[m])}**' for m in extras) + '.')

    tabla = res.get('tabla')
    if c['tipo'] == 'lista' and tabla and tabla['mostradas'] < tabla['total_filas']:
        partes.append(f'Te muestro {tabla["mostradas"]} de {_num(tabla["total_filas"], 0)}; '
                      'descarga el Excel para verlas todas.')
    elif c['tipo'] == 'agrupado' and tabla and tabla['filas']:
        dims = c['agrupar_por']
        principal = (c['orden']['campo'] if c['orden'] and c['orden']['campo'] in METRICAS
                     else next((m for m in ('descarga_kg', 'descarga_ton', 'carga_kg', 'carga_ton')
                                if m in c['metricas']), None)
                     # sin pesos: la métrica que se pidió (tiempo, importe, merma…)
                     or next((m for m in c['metricas'] if m != 'remisiones'), 'remisiones'))
        con_valor = [x for x in tabla['filas'] if x.get(principal) is not None] or tabla['filas']
        top = max(con_valor, key=lambda x: x[principal] or 0) if dims[0] in DIMENSIONES_TIEMPO \
            else con_valor[0]
        etiqueta = ' / '.join(str(top[f'g_{d}']) for d in dims)
        valor, total = top[principal], r.get(principal) or 0
        valor_txt = _valor_txt(principal, valor)
        dim_txt = ' y '.join(DIMENSIONES[d].lower() for d in dims)
        grupos = tabla['total_filas']
        if grupos == 1:
            partes.append(f'Todo corresponde a **{etiqueta}** ({dim_txt}).')
            return ' '.join(partes)
        frase = f'Agrupé por {dim_txt}: {_num(grupos, 0)} grupos'
        mostradas = tabla['mostradas']
        if mostradas < grupos:
            frase += ' (te muestro ' + ('el principal' if mostradas == 1 else f'los {mostradas} principales') + ')'
        frase += '. '
        if total and valor and principal in _ADITIVAS:
            frase += f'Destaca **{etiqueta}** con {valor_txt} ({_num(valor / total * 100, 1)} % del total).'
        else:
            frase += f'Destaca **{etiqueta}** con {valor_txt}.'
        partes.append(frase)
    return ' '.join(partes)


# Métricas que se suman (tiene sentido "% del total") y las que se reportan aparte
_ADITIVAS = {'remisiones', 'carga_kg', 'descarga_kg', 'rechazo_kg', 'carga_ton', 'descarga_ton',
             'rechazo_ton', 'importe', 'peso_bascula_kg'}
_METRICAS_EXTRA = ('importe', 'promedio_carga_kg', 'promedio_descarga_kg', 'peso_bascula_kg',
                   'tiempo_carga_h', 'tiempo_descarga_h', 'tiempo_transito_h', 'bultos')


def _valor_txt(metrica, valor):
    if valor is None:
        return 'sin dato'
    tipo = METRICAS[metrica][1]
    if metrica == 'remisiones':
        return f'{_num(valor, 0)} remisiones'
    return {
        'pct': f'{_num(valor, 2)} %', 'ton': f'{_num(valor, 2)} t', 'kg': f'{_num(valor, 2)} kg',
        'dinero': f'${_num(valor, 2)}', 'horas': f'{_num(valor, 2)} h', 'entero': _num(valor, 0),
    }.get(tipo, str(valor))


# ════════════════════════════════════════════════════════════════════════════
# INTÉRPRETE CON IA
# ════════════════════════════════════════════════════════════════════════════

def _instalado(modulo):
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def _proveedores_ia(incluir_anthropic=True):
    """[(nombre, función(system, user) → texto)] en orden de preferencia. Solo
    los que tienen llave Y librería instalada (DeepSeek va por HTTP)."""
    lista = []
    try:
        from ia_studio.ia_client import chat_ia, resolver_config_ia
        cfg = resolver_config_ia(None)
        if cfg.get('api_key') and (cfg['proveedor'] == 'deepseek'
                                   or (incluir_anthropic and _instalado('anthropic'))):
            def _principal(system, user, cfg=cfg):
                return chat_ia(cfg['proveedor'], cfg['api_key'], system, user,
                               base_url=cfg['base_url'], modelo=cfg['modelo'],
                               max_tokens=1500, temperature=0, json_mode=True)
            lista.append((cfg['proveedor'], _principal))
    except Exception:
        logger.exception('Reportes IA: no se pudo leer la configuración de IA')
    try:
        from .chat_ia import _gemini_api_key, _gemini_chat
        clave = _gemini_api_key()
        if clave and _instalado('google.genai'):
            lista.append(('gemini', lambda system, user: _gemini_chat(clave, system, [], user)))
    except Exception:
        logger.exception('Reportes IA: no se pudo preparar Gemini')
    return lista


NOMBRE_PROVEEDOR = {'anthropic': 'Claude (Anthropic)', 'deepseek': 'DeepSeek', 'gemini': 'Gemini (Google)'}


def _catalogo_prompt(user):
    def nombres(qs, campo='nombre', tope=300):
        vals = [n for n in qs.values_list(campo, flat=True)[:tope] if n]
        return ', '.join(vals) or '(vacío)'
    return (
        f'Unidades de negocio que este usuario puede consultar: {nombres(_empresas_permitidas(user).order_by("nombre"))}\n'
        f'Lugares (orígenes y destinos): {nombres(Lugar.objects.order_by("nombre"))}\n'
        f'Materiales: {nombres(Material.objects.order_by("nombre"))}'
    )


def _conocimiento(user, hoy):
    """Lo que la IA necesita saber de las remisiones y de cómo consultarlas.
    Lo comparten el agente (Claude) y el modo JSON (otros proveedores)."""
    return f"""Hoy es {DIAS[hoy.weekday()]} {hoy.isoformat()} (zona horaria America/Monterrey).

QUÉ ES UNA REMISIÓN: el registro de un viaje de material de un origen a un destino. Tiene unidad de negocio (empresa), folio de remisión, fecha de captura, fechas y horas de carga y de descarga, folio de carga, folio de descarga, folio de salida (solo PROBOCA), folio Medline, operador, línea de transporte, unidad (tracto) y contenedor con sus placas, cliente, estatus (PENDIENTE, TERMINADO, AUDITADO, CANCELADO), horas de entrada y salida, peso de báscula, factura, evidencias, manifiesto, descripción, notas de trazabilidad, comentario, datos de destrucción fiscal, quién y cuándo la auditó, y una o varias líneas de material con peso de carga, de descarga y rechazado (kg), patio de rechazo, cliente, bultos y precio por kg (solo SEALED AIR; importe = kg de descarga × precio). Merma % = (carga − descarga − rechazo) / carga × 100. Un "viaje" es una remisión.

CÓMO SE ARMA UNA CONSULTA
- tipo: "lista" = remisiones una por una; "agrupado" = totales por una o dos dimensiones; "total" = solo totales generales (¿cuántas…?, ¿cuánto se cargó…?).
- Fechas: convierte expresiones relativas a fechas exactas (hoy, ayer, esta semana = lunes a hoy, la semana pasada = lunes a domingo, este mes = día 1 a hoy, el mes pasado, "septiembre", el año pasado, los últimos 15 días). Un mes sin año es el más reciente que ya empezó. Si NO mencionan periodo, no pongas fechas.
- campo_fecha: "descarga" por defecto (fecha de inicio de descarga, la que usan todos los reportes). "captura" si piden la fecha de captura; "carga" la fecha de carga; "auditoria" si preguntan por lo auditado en un periodo; "registro" si preguntan qué se dio de alta en el sistema en un periodo; "destruccion" la fecha de destrucción fiscal.
- Nombres: escríbelos como aparecen en los catálogos de abajo si los reconoces (corrige errores de dictado); si no, tal como los dijo el usuario. PROBOCA y SEALED AIR son unidades de negocio; HUAXING, BACHOCO, TRANE, MEDLINE y HUDSON suelen ser orígenes.
- status: no lo pongas si no lo piden (el sistema excluye las canceladas). "Por auditar" = TERMINADO.
- Texto (contiene): factura (nombre/folio de factura o CFDI), placas (de unidad o contenedor), auditado_por (nombre de quien auditó), texto (busca en comentario, descripción, notas de trazabilidad y comentarios de destrucción: úsalo para "que diga…", "que mencione…").
- Rangos: merma en %, carga y descarga en KILOS (20 toneladas = 20000), antiguedad = días transcurridos desde la fecha del periodo ("pendientes de más de 7 días" → status PENDIENTE y antiguedad_min 7).
- Sí/no: con_X true = que lo tenga, false = que NO lo tenga ("sin factura" → con_factura false; "sin evidencias" → con_evidencia false; "sin descargar" → con_descarga false). destruccion_completa false = destrucción fiscal pendiente.
- agrupar_por (máximo 2): empresa, origen, destino, cliente, material, operador, linea_transporte, unidad, contenedor, status, patio_rechazo, auditado_por, dia, semana, mes, anio, dia_semana.
- metricas: remisiones, carga_kg, descarga_kg, rechazo_kg, diferencia_kg, merma_pct, carga_ton, descarga_ton, rechazo_ton, bultos, promedio_carga_kg, promedio_descarga_kg (por remisión), importe ($, SEALED AIR), peso_bascula_kg, tiempo_carga_h, tiempo_descarga_h, tiempo_transito_h (promedios en horas; tránsito = de fin de carga a inicio de descarga). Usa las *_ton si hablan de toneladas.
- columnas (solo en lista): remision, fecha_descarga, fecha, empresa, origen, destino, cliente, materiales, operador, linea_transporte, unidad, contenedor, placas_unidad, placas_contenedor, status, folio_carga, folio_descarga, folio_salida, folio_medline, inicia_carga, termina_carga, inicia_descarga, termina_descarga, hora_entrada, hora_salida, carga_kg, descarga_kg, rechazo_kg, diferencia_kg, merma_pct, carga_ton, descarga_ton, rechazo_ton, bultos, importe, precio_kg, tiempo_carga_h, tiempo_descarga_h, tiempo_transito_h, dias_antiguedad, peso_bascula, unidad_medida, patio_rechazo, cliente_detalle, factura, facturas_cfdi, evidencias, manifiesto, boleta_medline, fecha_destruccion, destruccion, destruccion_completa, comentarios_destruccion, descripcion, trazabilidad, comentario, auditado_por, auditado_en, creado_en, actualizado_en, ultimo_cambio. Si no piden datos concretos, omite "columnas" (hay unas por defecto). Si piden un dato concreto, incluye las columnas básicas (remision, fecha_descarga, empresa, origen, destino, materiales) más lo pedido. Si piden "todo" o "todos los datos" de una remisión, incluye todas las columnas.
- orden.campo: una métrica, una columna o una dimensión. "Top N" o "los N con más…" → dir "desc" y limite N.
- limite: lista 50 por defecto (máximo 500); agrupado 100.
- reporte_formal: solo si piden explícitamente el reporte oficial/formato de PROBOCA, SEALED AIR, HUAXING, BACHOCO o TRANE.

CATÁLOGOS
{_catalogo_prompt(user)}"""


def _prompt_sistema(user, hoy):
    lunes = hoy - dt.timedelta(days=hoy.weekday())
    mes_ant_ini, mes_ant_fin = _rango_mes(*((hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)))
    ej = {
        'total': {'tipo': 'total', 'titulo': f'Remisiones PROBOCA · {MESES[hoy.month - 1]} {hoy.year}',
                  'filtros': {'empresa': ['PROBOCA'], 'fecha_desde': hoy.replace(day=1).isoformat(),
                              'fecha_hasta': hoy.isoformat()}},
        'agrupado': {'tipo': 'agrupado',
                     'titulo': f'Toneladas por material · {MESES[mes_ant_ini.month - 1]} {mes_ant_ini.year}',
                     'filtros': {'fecha_desde': mes_ant_ini.isoformat(), 'fecha_hasta': mes_ant_fin.isoformat()},
                     'agrupar_por': ['material'], 'metricas': ['remisiones', 'descarga_ton'],
                     'orden': {'campo': 'descarga_ton', 'dir': 'desc'}},
        'lista': {'tipo': 'lista', 'titulo': 'Remisiones pendientes de esta semana',
                  'filtros': {'status': ['PENDIENTE'], 'fecha_desde': lunes.isoformat(),
                              'fecha_hasta': hoy.isoformat()},
                  'columnas': ['remision', 'fecha_descarga', 'empresa', 'origen', 'destino', 'operador',
                               'folio_carga', 'folio_descarga', 'status']},
        'top': {'tipo': 'agrupado', 'titulo': f'Top 5 operadores · {hoy.year}',
                'filtros': {'fecha_desde': f'{hoy.year}-01-01', 'fecha_hasta': hoy.isoformat()},
                'agrupar_por': ['operador'], 'metricas': ['remisiones', 'descarga_kg'],
                'orden': {'campo': 'remisiones', 'dir': 'desc'}, 'limite': 5},
    }
    js = lambda o: json.dumps(o, ensure_ascii=False)  # noqa: E731
    return f"""Eres el motor de consultas de "Reportes con IA" del ERP de 3R Recycling. Conviertes la petición del usuario (escrita o dictada por voz; puede traer errores de dictado) en UNA consulta JSON sobre REMISIONES. Tú no calculas cifras: el sistema ejecuta tu consulta contra la base de datos.

{_conocimiento(user, hoy)}

Responde SOLO con un objeto JSON, sin texto adicional ni ```. Forma (omite las claves que no uses):
{{"tipo": "lista|agrupado|total|conversacion", "titulo": "título corto",
 "filtros": {{"fecha_desde": "AAAA-MM-DD", "fecha_hasta": "AAAA-MM-DD", "campo_fecha": "descarga|captura|carga|auditoria|registro|destruccion",
   "empresa": [], "origen": [], "destino": [], "cliente": [], "material": [], "operador": [], "linea_transporte": [], "unidad": [], "contenedor": [], "patio_rechazo": [],
   "status": [], "remision": "", "folio_carga": "", "folio_descarga": "", "folio_salida": "", "folio_medline": "",
   "factura": "", "placas": "", "auditado_por": "", "texto": "",
   "merma_min": número, "merma_max": número, "carga_min": kg, "carga_max": kg, "descarga_min": kg, "descarga_max": kg,
   "antiguedad_min": días, "antiguedad_max": días,
   "con_rechazo": bool, "con_factura": bool, "con_evidencia": bool, "con_manifiesto": bool, "con_descarga": bool,
   "con_folio_salida": bool, "destruccion_completa": bool}},
 "agrupar_por": [], "metricas": [], "columnas": [], "orden": {{"campo": "", "dir": "asc|desc"}}, "limite": número,
 "reporte_formal": "proboca|sealed-air|huaxing|bachoco|trane", "mensaje": ""}}

REGLAS DE ESTE FORMATO
- tipo "conversacion": saludos, ayuda o temas que NO son remisiones (pon una respuesta breve y amable en "mensaje"; si piden otra cosa, como diésel o nómina, explica que este módulo consulta remisiones).
- Seguimiento: si viene una CONSULTA ANTERIOR y la petición la modifica ("ahora por material", "solo las de septiembre", "¿y de PROBOCA?"), parte de ella y cambia solo lo pedido. Si es un tema nuevo, empieza de cero.
- No hagas preguntas: si algo es ambiguo, elige la interpretación más razonable.

EJEMPLOS
"cuántas remisiones de proboca llevamos este mes" → {js(ej['total'])}
"toneladas descargadas por material el mes pasado" → {js(ej['agrupado'])}
"dame las remisiones pendientes de esta semana con operador y folios" → {js(ej['lista'])}
"top 5 operadores con más viajes este año" → {js(ej['top'])}"""


def _prompt_usuario(pregunta, contexto, previas):
    partes = []
    if contexto:
        partes.append('CONSULTA ANTERIOR: ' + json.dumps(contexto, ensure_ascii=False, default=str)[:2500])
    if previas:
        partes.append('PREGUNTAS ANTERIORES:\n' + '\n'.join(f'- {p}' for p in previas))
    partes.append(f'PETICIÓN: {pregunta}')
    return '\n\n'.join(partes)


def _extraer_json(texto):
    t = re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', str(texto or '').strip())
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def ia_disponible():
    proveedores = _proveedores_ia()
    return proveedores[0][0] if proveedores else None


def interpretar(pregunta, user, contexto=None, previas=None, incluir_anthropic=True):
    """→ (consulta cruda, motor 'ia'|'reglas', proveedor, aviso)."""
    hoy = _hoy()
    proveedores = _proveedores_ia(incluir_anthropic)
    aviso = ''
    if proveedores:
        system = _prompt_sistema(user, hoy)
        mensaje = _prompt_usuario(pregunta, contexto, previas)
        for nombre, llamar in proveedores:
            try:
                consulta = _extraer_json(llamar(system, mensaje))
                if isinstance(consulta, dict):
                    return consulta, 'ia', nombre, ''
            except Exception as e:
                logger.warning('Reportes IA: %s no respondió (%s)', nombre, e)
        aviso = 'La IA no respondió en este momento; usé el intérprete básico.'
    return interpretar_reglas(pregunta, user, contexto, hoy), 'reglas', None, aviso


# ════════════════════════════════════════════════════════════════════════════
# AGENTE CON CLAUDE: responde cualquier pregunta sobre remisiones
# ════════════════════════════════════════════════════════════════════════════
# Claude no toca la base de datos: usa la herramienta `consultar_remisiones`
# (que pasa por normalizar() + ejecutar(), con los permisos del usuario) las
# veces que necesite y redacta la respuesta con esas cifras.

MODELO_AGENTE = os.environ.get('REPORTES_IA_MODELO', 'claude-haiku-5-5')
ESFUERZO_AGENTE = os.environ.get('REPORTES_IA_ESFUERZO', 'medium')
MAX_PASOS_AGENTE = 6       # llamadas al modelo por pregunta
MAX_CONSULTAS_AGENTE = 8   # consultas a la base por pregunta
FILAS_PARA_IA = 80         # renglones de cada tabla que ve el modelo


# USD por millón de tokens (entrada, salida). Haiku 5.5 cobra esta tarifa con
# prompts de hasta 100K tokens; arriba, la de PRECIO_HAIKU_LARGO. La caché se
# cobra como 0.1× (lectura) y 1.25× (escritura de 5 min) del precio de entrada.
PRECIOS_MODELO = {
    'claude-haiku-5-5': (0.10, 0.50),
    'claude-sonnet-5-5': (2.00, 10.00),
    'claude-sonnet-5': (2.00, 10.00),
    'claude-opus-5-5': (4.00, 20.00),
}
PRECIO_HAIKU_LARGO = (0.50, 2.50)


def costo_llamada(modelo, uso):
    """Costo en USD de una llamada a Claude según su `usage`."""
    entrada = getattr(uso, 'input_tokens', 0) or 0
    salida = getattr(uso, 'output_tokens', 0) or 0
    lectura = getattr(uso, 'cache_read_input_tokens', 0) or 0
    escritura = getattr(uso, 'cache_creation_input_tokens', 0) or 0
    precio_in, precio_out = PRECIOS_MODELO.get(modelo, (0.0, 0.0))
    if modelo == 'claude-haiku-5-5' and entrada + lectura + escritura > 100_000:
        precio_in, precio_out = PRECIO_HAIKU_LARGO
    return (entrada * precio_in + lectura * precio_in * 0.1 + escritura * precio_in * 1.25
            + salida * precio_out) / 1_000_000


def uso_vacio():
    return {'modelo': MODELO_AGENTE, 'llamadas': 0, 'entrada': 0, 'salida': 0,
            'cache_lectura': 0, 'cache_escritura': 0, 'costo_usd': 0.0}


def _sumar_uso(acumulado, respuesta):
    u = respuesta.usage
    acumulado['llamadas'] += 1
    acumulado['entrada'] += getattr(u, 'input_tokens', 0) or 0
    acumulado['salida'] += getattr(u, 'output_tokens', 0) or 0
    acumulado['cache_lectura'] += getattr(u, 'cache_read_input_tokens', 0) or 0
    acumulado['cache_escritura'] += getattr(u, 'cache_creation_input_tokens', 0) or 0
    acumulado['costo_usd'] += costo_llamada(MODELO_AGENTE, u)


class AgenteNoDisponible(Exception):
    """El agente falló; `aviso` explica al usuario por qué se usó el respaldo."""
    def __init__(self, aviso):
        super().__init__(aviso)
        self.aviso = aviso


def _config_agente():
    """Llave de Anthropic si el proveedor configurado es Anthropic (Configuración IA)."""
    if not _instalado('anthropic'):
        return None
    try:
        from ia_studio.ia_client import resolver_config_ia
        cfg = resolver_config_ia(None)
    except Exception:
        return None
    if cfg.get('proveedor') == 'anthropic' and cfg.get('api_key'):
        return cfg['api_key']
    return None


def _esquema_consulta():
    texto = {'type': 'string'}
    filtros = {
        'fecha_desde': {'type': 'string', 'description': 'AAAA-MM-DD'},
        'fecha_hasta': {'type': 'string', 'description': 'AAAA-MM-DD'},
        'campo_fecha': {'type': 'string', 'enum': list(CAMPOS_FECHA)},
        **{k: {'type': 'array', 'items': texto, 'description': f'{v[0]} (nombres)'} for k, v in CATALOGOS.items()},
        'status': {'type': 'array', 'items': {'type': 'string', 'enum': list(STATUS)}},
        **{k: {'type': 'string', 'description': f'{v[0]} contiene'} for k, v in TEXTOS.items()},
        **{f'{k}_{s}': {'type': 'number', 'description': f'{v[0]} {"mínima" if s == "min" else "máxima"} ({v[1]})'}
           for k, v in RANGOS.items() for s in ('min', 'max')},
        **{k: {'type': 'boolean', 'description': f'true = {v[0].lower()}; false = {v[1].lower()}'}
           for k, v in SI_NO.items()},
    }
    return {
        'type': 'object',
        'properties': {
            'tipo': {'type': 'string', 'enum': ['lista', 'agrupado', 'total']},
            'titulo': {'type': 'string', 'description': 'Título corto de esta consulta'},
            'filtros': {'type': 'object', 'properties': filtros, 'additionalProperties': False},
            'agrupar_por': {'type': 'array', 'items': {'type': 'string', 'enum': list(DIMENSIONES)}, 'maxItems': 2},
            'metricas': {'type': 'array', 'items': {'type': 'string', 'enum': list(METRICAS)}},
            'columnas': {'type': 'array', 'items': {'type': 'string', 'enum': list(COLUMNAS)}},
            'orden': {'type': 'object', 'properties': {
                'campo': texto, 'dir': {'type': 'string', 'enum': ['asc', 'desc']}}},
            'limite': {'type': 'integer', 'minimum': 1, 'maximum': LIMITE_LISTA_MAX},
            'reporte_formal': {'type': 'string', 'enum': list(REPORTES_FORMALES)},
        },
        'required': ['tipo'],
    }


HERRAMIENTA_CONSULTA = {
    'name': 'consultar_remisiones',
    'description': (
        'Consulta las remisiones del sistema (solo las unidades de negocio que el usuario tiene '
        'autorizadas) y devuelve totales, filtros aplicados, avisos y una tabla. Úsala para '
        'obtener cualquier dato: listas de remisiones, totales, agrupaciones, rankings, '
        'tendencias. Puedes llamarla varias veces, por ejemplo para comparar dos periodos. Los '
        'pesos están en kilos salvo las métricas *_ton. Si un nombre no existe, el resultado lo '
        'indica en "avisos".'
    ),
    'input_schema': _esquema_consulta(),
}


# Catálogos que la IA puede leer: clave → (modelo, campo nombre, campos básicos,
# campos extra solo con permiso de Catálogos). Fuera: VIN, pólizas, documentos,
# fotos, teléfonos y correos.
CATALOGOS_IA = {
    'materiales': (Material, 'nombre', ['nombre', 'clave_sat', 'clave_unidad_sat'], ['creado_en']),
    'unidades_negocio': (Empresa, 'nombre', ['nombre', 'prefijo'], ['creado_en']),
    'lugares': (Lugar, 'nombre', ['nombre', 'tipo', 'es_patio', 'municipio', 'estado'],
                ['razon_social', 'rfc', 'regimen_fiscal', 'uso_cfdi', 'calle', 'numero_exterior',
                 'colonia', 'codigo_postal', 'localidad', 'pais']),
    'operadores': (Operador, 'nombre', ['nombre', 'folio', 'activo'], ['creado_en']),
    'unidades': (Unidad, 'internal_id', ['internal_id', 'license_plate', 'make_model', 'year', 'asset_type',
                                         'ownership', 'operational_status'],
                 ['color', 'acquisition_date', 'insurance_due_date', 'license_due_date', 'permiso_sct',
                  'no_permiso_sct', 'nombre_aseguradora', 'eco_remolque_1', 'placa_remolque_1',
                  'eco_remolque_2', 'placa_remolque_2']),
    'contenedores': (Contenedor, 'nombre', ['nombre', 'placas'], []),
    'lineas_transporte': (LineaTransporte, 'nombre', ['nombre'], []),
    'clientes': (Cliente, 'nombre', ['nombre', 'municipio'], ['calle', 'no_exterior', 'colonia', 'codigo_postal']),
}
LIMITE_CATALOGO = 200


def consultar_catalogo(entrada, user):
    """Lectura de catálogos para la IA (lista cerrada de campos). Devuelve JSON."""
    clave = entrada.get('catalogo') if isinstance(entrada, dict) else None
    if clave not in CATALOGOS_IA:
        return json.dumps({'error': f'Catálogo no válido. Opciones: {", ".join(CATALOGOS_IA)}'}, ensure_ascii=False)
    modelo, campo_nombre, basicos, extra = CATALOGOS_IA[clave]
    con_extra = user.is_superuser or user.has_perm('ternium.acceso_catalogos')
    campos = basicos + (extra if con_extra else [])
    qs = _empresas_permitidas(user) if clave == 'unidades_negocio' else modelo.objects.all()

    buscar = ' '.join(str(entrada.get('buscar') or '').split())[:80]
    if buscar:
        textos = [c for c in campos if modelo._meta.get_field(c).get_internal_type() in ('CharField', 'TextField')]
        cond = Q()
        for c in textos:
            cond |= Q(**{f'{c}__icontains': buscar})
        qs = qs.filter(cond)
    if clave == 'operadores' and isinstance(entrada.get('activo'), bool):
        qs = qs.filter(activo=entrada['activo'])
    if clave == 'lugares' and isinstance(entrada.get('es_patio'), bool):
        qs = qs.filter(es_patio=entrada['es_patio'])
    try:
        limite = max(1, min(int(entrada.get('limite') or 50), LIMITE_CATALOGO))
    except (TypeError, ValueError):
        limite = 50

    salida = {
        'catalogo': clave,
        'total': qs.count(),
        'filas': list(qs.order_by(campo_nombre).values(*campos)[:limite]),
    }
    if extra and not con_extra:
        salida['nota'] = 'Este usuario no tiene permiso de Catálogos: solo se muestran los datos básicos.'
    return json.dumps(salida, ensure_ascii=False, cls=_Encoder)


HERRAMIENTA_CATALOGO = {
    'name': 'consultar_catalogo',
    'description': (
        'Consulta los catálogos del sistema: materiales (con clave SAT), unidades_negocio (empresas), '
        'lugares (orígenes y destinos, si es patio, ubicación), operadores (folio, si está activo), '
        'unidades (tractos: placas, marca, año, estatus, vencimientos), contenedores (placas), '
        'lineas_transporte y clientes. Úsala para preguntas sobre los catálogos en sí ("¿qué '
        'materiales hay?", "¿qué clave SAT tiene el cartón?", "¿qué operadores están activos?"). '
        'Para cantidades movidas, viajes o pesos usa consultar_remisiones.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'catalogo': {'type': 'string', 'enum': list(CATALOGOS_IA)},
            'buscar': {'type': 'string', 'description': 'Texto a buscar en el nombre y demás datos'},
            'activo': {'type': 'boolean', 'description': 'Solo operadores: activos (true) o inactivos (false)'},
            'es_patio': {'type': 'boolean', 'description': 'Solo lugares: patios (true) o no (false)'},
            'limite': {'type': 'integer', 'minimum': 1, 'maximum': LIMITE_CATALOGO},
        },
        'required': ['catalogo'],
    },
}


def _prompt_agente(user, hoy):
    return f"""Eres el asistente de "Reportes con IA" del ERP de 3R Recycling. Respondes con libertad cualquier pregunta sobre las REMISIONES del usuario y lo relacionado con ellas: materiales (cuánto se movió de cada uno), unidades de negocio, orígenes, destinos, clientes, operadores, unidades, tiempos, mermas, folios, facturas… La pregunta puede venir escrita o dictada por voz (con errores de dictado).

CÓMO TRABAJAS
- Para cifras de movimientos (cuánto, cuántas, toneladas, viajes, mermas, tiempos, rankings, comparaciones) usa consultar_remisiones: llámala las veces que haga falta (comparar periodos, empresas o materiales, revisar el detalle de una remisión, buscar la causa de algo). Si la pregunta se puede contestar con una sola consulta, haz una sola. Ejemplo: "¿cuánto cartón se movió este año?" → tipo total, material ["CARTON"], fechas del año, métricas en toneladas.
- Para datos de los catálogos en sí (qué materiales o lugares existen, claves SAT, operadores activos, placas o vencimientos de una unidad) usa consultar_catalogo.
- Nunca inventes cifras ni nombres: todo lo que afirmes debe salir de los resultados de la herramienta. Puedes calcular diferencias, porcentajes y promedios a partir de esos resultados; hazlo con cuidado y, si es útil, menciona de dónde sale el cálculo.
- Si la herramienta devuelve avisos (un nombre que no existe, una empresa no autorizada) o no hay datos, dilo con claridad y sugiere otra forma de preguntar.
- No hagas preguntas de aclaración: si algo es ambiguo, elige la interpretación más razonable y menciona brevemente cuál usaste.
- Si la pregunta no es sobre remisiones (por ejemplo diésel, nómina o bancos), explica amablemente que este módulo consulta remisiones y que esos datos están en su propio módulo. Saludos y dudas de uso se contestan sin consultar.
- Si hay conversación previa, úsala para entender preguntas de seguimiento ("¿y en abril?", "ahora por material").
- Excel y presentaciones: la pantalla genera con los datos de tus consultas un Excel (con fórmulas, totales, hoja de resumen y gráfica) y una presentación de PowerPoint (portada, tu respuesta, indicadores, gráficas y tablas). Si el usuario pide un Excel, un reporte para descargar o una presentación, haz las consultas que necesite ese reporte (puedes hacer varias: cada una será una hoja o una diapositiva) y dile que el archivo se está descargando; nunca digas que no puedes generarlo.

CÓMO RESPONDES
- En español de México, claro y directo; empieza por la respuesta. Breve: unas pocas frases o viñetas.
- Usa **negritas** para las cifras clave y viñetas con "• " cuando enumeres. No uses tablas markdown ni encabezados (#): la pantalla ya muestra la tabla de cada consulta y el usuario puede descargarla en Excel.
- Cantidades en formato mexicano (1,234.56), toneladas con "t" y kilos con "kg".

{_conocimiento(user, hoy)}"""


def _resultado_para_ia(c, res):
    """Lo que el modelo ve de una consulta: resumen, filtros, avisos y la tabla (recortada)."""
    salida = {
        'titulo': res['titulo'],
        'filtros_aplicados': res['filtros_texto'],
        'avisos': res['avisos'],
        'resumen': {k: v for k, v in res['resumen'].items() if v is not None},
    }
    t = res.get('tabla')
    if t:
        claves = [col['clave'] for col in t['columnas']]
        salida['tabla'] = {
            'columnas': [col['titulo'] for col in t['columnas']],
            'filas': [[fila.get(k) for k in claves] for fila in t['filas'][:FILAS_PARA_IA]],
            'total_filas': t['total_filas'],
            'filas_incluidas': min(len(t['filas']), FILAS_PARA_IA),
        }
    if res.get('reporte_formal'):
        salida['reporte_oficial_disponible'] = res['reporte_formal']['etiqueta']
    return json.dumps(salida, ensure_ascii=False, cls=_Encoder)


def _cliente_anthropic(api_key):
    import anthropic
    try:
        # Redes con antivirus/proxy que intercepta TLS: misma CA extra que el resto de la IA
        from ia_studio.ia_client import _ssl_context_ia
        ctx = _ssl_context_ia()
    except Exception:
        ctx = None
    if ctx is not None:
        import httpx
        return anthropic.Anthropic(api_key=api_key, timeout=60, http_client=httpx.Client(verify=ctx, timeout=60))
    return anthropic.Anthropic(api_key=api_key, timeout=60)


def responder_con_agente(pregunta, user, api_key, historial=None, contexto=None, uso=None):
    """Ciclo de herramientas con Claude. Devuelve (texto, [(consulta, resultado), ...]).
    Va sumando tokens y costo en `uso` (también si falla a medio camino).
    Lanza AgenteNoDisponible si la API falla, para usar el respaldo."""
    uso = uso if uso is not None else uso_vacio()
    import anthropic

    hoy = _hoy()
    client = _cliente_anthropic(api_key)
    system = [{'type': 'text', 'text': _prompt_agente(user, hoy), 'cache_control': {'type': 'ephemeral'}}]

    messages = []
    for h in (historial or [])[-3:]:
        if h.get('pregunta') and h.get('respuesta'):
            messages.append({'role': 'user', 'content': h['pregunta']})
            messages.append({'role': 'assistant', 'content': h['respuesta']})
    texto_usuario = pregunta
    if contexto:
        texto_usuario += ('\n\n(Para preguntas de seguimiento, la última consulta que se hizo fue: '
                          + json.dumps(contexto, ensure_ascii=False, default=str)[:2500] + ')')
    messages.append({'role': 'user', 'content': texto_usuario})

    consultas = []
    usadas = 0  # herramientas ejecutadas (remisiones + catálogos)

    def llamar(**extra):
        try:
            return client.messages.create(
                model=MODELO_AGENTE, max_tokens=16000, system=system,
                tools=[HERRAMIENTA_CONSULTA, HERRAMIENTA_CATALOGO], output_config={'effort': ESFUERZO_AGENTE},
                messages=messages, **extra)
        except anthropic.AuthenticationError:
            raise AgenteNoDisponible('La llave de Anthropic de Configuración IA no es válida; usé el respaldo.')
        except anthropic.PermissionDeniedError:
            raise AgenteNoDisponible('La llave de Anthropic no tiene acceso al modelo; usé el respaldo.')
        except anthropic.RateLimitError:
            raise AgenteNoDisponible('Claude está saturado en este momento; usé el respaldo.')
        except anthropic.APIStatusError as e:
            logger.warning('Reportes IA: Claude respondió %s: %s', e.status_code, e.message)
            raise AgenteNoDisponible('Claude no respondió en este momento; usé el respaldo.')
        except anthropic.APIConnectionError as e:
            logger.warning('Reportes IA: sin conexión con Claude (%s)', e)
            raise AgenteNoDisponible('No hubo conexión con Claude; usé el respaldo.')

    respuesta = None
    for paso in range(MAX_PASOS_AGENTE):
        # En el último paso ya no se permiten herramientas: que conteste con lo que tiene
        extra = {'tool_choice': {'type': 'none'}} if paso == MAX_PASOS_AGENTE - 1 else {}
        respuesta = llamar(**extra)
        _sumar_uso(uso, respuesta)
        if respuesta.stop_reason == 'refusal':
            return 'No puedo ayudar con esa solicitud. Intenta preguntarlo de otra forma.', consultas
        if respuesta.stop_reason != 'tool_use':
            break
        # El turno completo (con sus bloques de razonamiento) regresa tal cual
        messages.append({'role': 'assistant', 'content': respuesta.content})
        resultados = []
        for bloque in respuesta.content:
            if bloque.type != 'tool_use':
                continue
            if bloque.name not in (HERRAMIENTA_CONSULTA['name'], HERRAMIENTA_CATALOGO['name']):
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                   'content': 'Herramienta desconocida.'})
                continue
            usadas += 1
            if usadas > MAX_CONSULTAS_AGENTE:
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                   'content': 'Límite de consultas alcanzado: responde con los datos que ya tienes.'})
                continue
            if bloque.name == HERRAMIENTA_CATALOGO['name']:
                try:
                    contenido = consultar_catalogo(bloque.input, user)
                    resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'content': contenido})
                except Exception:
                    logger.exception('Reportes IA: falló el catálogo %s', bloque.input)
                    resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                       'content': 'No se pudo leer el catálogo.'})
                continue
            try:
                consulta = normalizar(bloque.input if isinstance(bloque.input, dict) else {})
                if consulta['tipo'] == 'conversacion':
                    consulta['tipo'] = 'total'
                resultado = ejecutar(consulta, user)
                consultas.append((consulta, resultado))
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id,
                                   'content': _resultado_para_ia(consulta, resultado)})
            except Exception:
                logger.exception('Reportes IA: falló la consulta del agente %s', bloque.input)
                resultados.append({'type': 'tool_result', 'tool_use_id': bloque.id, 'is_error': True,
                                   'content': 'La consulta falló. Intenta con otros filtros más sencillos.'})
        messages.append({'role': 'user', 'content': resultados})

    texto = ''.join(b.text for b in (respuesta.content if respuesta else []) if b.type == 'text').strip()
    if not texto:
        texto = ('Aquí están los datos que encontré.' if consultas
                 else 'No pude armar una respuesta. Intenta decirlo de otra forma.')
    logger.info('Reportes IA agente [%s] %d consultas · %d llamadas · tokens entrada %s (caché %s) '
                'salida %s · US$%.5f', user.username, len(consultas), uso['llamadas'], uso['entrada'],
                uso['cache_lectura'], uso['salida'], uso['costo_usd'])
    return texto, consultas


# ════════════════════════════════════════════════════════════════════════════
# INTÉRPRETE POR REGLAS (sin IA configurada o si la IA falla)
# ════════════════════════════════════════════════════════════════════════════

_MES_RE = '(' + '|'.join(MESES + ['setiembre']) + r')\b'  # \b: "mayor" no es "mayo"


def _num_mes(nombre):
    return 9 if nombre == 'setiembre' else MESES.index(nombre) + 1


def _mes_reciente(mes, hoy):
    return hoy.year if mes <= hoy.month else hoy.year - 1


def _periodo_reglas(t, hoy):
    """(desde, hasta) a partir del texto plano, o (None, None)."""
    iso = [dt.date(int(a), int(m), int(d)) for a, m, d in re.findall(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', t)
           if 1 <= int(m) <= 12 and 1 <= int(d) <= 31]
    iso += [dt.date(int(a), int(m), int(d)) for d, m, a in re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', t)
            if 1 <= int(m) <= 12 and 1 <= int(d) <= 31]
    if len(iso) >= 2:
        return min(iso[:2]), max(iso[:2])
    if len(iso) == 1:
        return (iso[0], None) if re.search(r'\b(desde|a partir)\b', t) else (iso[0], iso[0])

    m = re.search(rf'\bdel? (\d{{1,2}}) al (\d{{1,2}}) de {_MES_RE}(?: (?:de |del )?(\d{{4}}))?', t)
    if m:
        mes = _num_mes(m.group(3))
        anio = int(m.group(4)) if m.group(4) else _mes_reciente(mes, hoy)
        ultimo = calendar.monthrange(anio, mes)[1]
        return (dt.date(anio, mes, min(int(m.group(1)), ultimo)),
                dt.date(anio, mes, min(int(m.group(2)), ultimo)))

    m = re.search(rf'\b(\d{{1,2}}) de {_MES_RE}(?: (?:de |del )?(\d{{4}}))?', t)
    if m and 1 <= int(m.group(1)) <= 31:
        mes = _num_mes(m.group(2))
        anio = int(m.group(3)) if m.group(3) else _mes_reciente(mes, hoy)
        d = dt.date(anio, mes, min(int(m.group(1)), calendar.monthrange(anio, mes)[1]))
        return d, d

    # "marzo del año pasado", "julio de este año"
    m = re.search(rf'\b{_MES_RE}\s+(?:del?\s+)?(?:el\s+)?(ano pasado|ano anterior|este ano|ano actual)\b', t)
    if m:
        anio = hoy.year if m.group(2) in ('este ano', 'ano actual') else hoy.year - 1
        return _rango_mes(anio, _num_mes(m.group(1)))

    # Trimestres y semestres: "primer trimestre de 2025", "segundo semestre"
    m = re.search(r'\b(primer|primero|1er|1|segundo|2do|2|tercer|tercero|3er|3|cuarto|4to|4)\s+'
                  r'(trimestre|semestre)(?:\s+(?:de |del )?(?:ano )?(\d{4}))?', t)
    if m:
        n = {'p': 1, '1': 1, 's': 2, '2': 2, 't': 3, '3': 3, 'c': 4, '4': 4}[m.group(1)[0]]
        meses = 3 if m.group(2) == 'trimestre' else 6
        if n * meses <= 12:
            primero = (n - 1) * meses + 1
            anio = int(m.group(3)) if m.group(3) else _mes_reciente(primero, hoy)
            return dt.date(anio, primero, 1), _rango_mes(anio, primero + meses - 1)[1]

    m = re.search(r'\bultim[oa]s? (\d{1,3}) (dias|semanas|meses)\b', t)
    if m:
        n = int(m.group(1))
        dias = n if m.group(2) == 'dias' else n * 7 if m.group(2) == 'semanas' else n * 30
        return hoy - dt.timedelta(days=dias - 1), hoy
    if re.search(r'\b(anteayer|antier)\b', t):
        d = hoy - dt.timedelta(days=2)
        return d, d
    if re.search(r'\bayer\b', t):
        d = hoy - dt.timedelta(days=1)
        return d, d
    if re.search(r'\bhoy\b', t):
        return hoy, hoy
    lunes = hoy - dt.timedelta(days=hoy.weekday())
    if re.search(r'\bsemana (pasada|anterior)\b', t):
        return lunes - dt.timedelta(days=7), lunes - dt.timedelta(days=1)
    if re.search(r'\b(esta semana|semana actual|en la semana)\b', t):
        return lunes, hoy
    if re.search(r'\bmes (pasado|anterior)\b', t):
        return _rango_mes(*((hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)))
    if re.search(r'\b(este mes|mes actual|en el mes|del mes)\b', t):
        return hoy.replace(day=1), hoy
    if re.search(r'\bano (pasado|anterior)\b', t):
        return dt.date(hoy.year - 1, 1, 1), dt.date(hoy.year - 1, 12, 31)
    if re.search(r'\b(este ano|ano actual|en el ano|del ano)\b', t):
        return dt.date(hoy.year, 1, 1), hoy

    meses = re.findall(rf'\b{_MES_RE}(?: (?:de |del )?(\d{{4}}))?', t)
    if meses:
        rangos = []
        for nombre, anio in meses[:2]:
            mes = _num_mes(nombre)
            rangos.append(_rango_mes(int(anio) if anio else _mes_reciente(mes, hoy), mes))
        return min(r[0] for r in rangos), max(r[1] for r in rangos)

    m = re.search(r'\b(?:en|del|de|durante) (?:el )?(?:ano )?(20\d{2})\b', t)
    if m:
        return dt.date(int(m.group(1)), 1, 1), dt.date(int(m.group(1)), 12, 31)
    return None, None


COLUMNAS_POR_PALABRA = [
    (r'\bfolios? de salida\b', ['folio_salida']),
    (r'\bfolios? de carga\b|\bfolios\b(?! de)', ['folio_carga']),
    (r'\bfolios? de descarga\b|\by de descarga\b|\bfolios\b(?! de)', ['folio_descarga']),
    (r'\bfolios? medline\b', ['folio_medline']),
    (r'\bfacturas?\b', ['factura']),
    (r'\bhoras? de carga\b', ['inicia_carga', 'termina_carga']),
    (r'\bhoras? de descarga\b|\bhorarios?\b', ['inicia_descarga', 'termina_descarga']),
    (r'\blineas? de transporte\b|\btransportistas?\b', ['linea_transporte']),
    (r'\bunidad(?:es)?\b(?! de negocio)|\btractos?\b|\bcamion(?:es)?\b', ['unidad']),
    (r'\bcontenedor(?:es)?\b|\bcajas?\b', ['contenedor']),
    (r'\bclientes?\b', ['cliente']),
    (r'\bbultos\b', ['bultos']),
    (r'\brechazos?\b', ['rechazo_kg']),
    (r'\bcomentarios?\b', ['comentario']),
    (r'\bauditad[oa] por\b|\bquien (?:la |las )?audito\b', ['auditado_por']),
    (r'\bfecha de auditoria\b|\bcuando se audito\b', ['auditado_por', 'auditado_en']),
    (r'\bfecha de captura\b', ['fecha']),
    (r'\bplacas?\b', ['placas_unidad', 'placas_contenedor']),
    (r'\bhoras? de entrada\b', ['hora_entrada']),
    (r'\bhoras? de salida\b', ['hora_salida']),
    (r'\bbascula\b', ['peso_bascula']),
    (r'\bdescripcion(?:es)?\b', ['descripcion']),
    (r'\btrazabilidad\b', ['trazabilidad']),
    (r'\bdestruccion\b', ['fecha_destruccion', 'destruccion', 'destruccion_completa']),
    (r'\bevidencias?\b', ['evidencias']),
    (r'\bmanifiestos?\b', ['manifiesto']),
    (r'\bboletas?\b', ['boleta_medline']),
    (r'\bcfdi\b', ['facturas_cfdi']),
    (r'\bprecios?\b|\bimportes?\b|\bventas?\b', ['precio_kg', 'importe']),
    (r'\btiempos?\b|\bcuanto tarda', ['tiempo_carga_h', 'tiempo_descarga_h', 'tiempo_transito_h']),
    (r'\btransito\b', ['tiempo_transito_h']),
    (r'\bpatio de rechazo\b', ['patio_rechazo']),
    (r'\bunidad de medida\b', ['unidad_medida']),
    (r'\bhistorial\b|\bultimo cambio\b|\bquien (?:la )?modifico\b', ['ultimo_cambio', 'actualizado_en']),
    (r'\bantiguedad\b|\bdias (?:transcurridos|pendientes?|sin)\b', ['dias_antiguedad']),
]

_GENERICAS = {'remision', 'remisiones', 'material', 'materiales', 'origen', 'destino', 'empresa',
              'cliente', 'operador', 'reporte', 'semana', 'total', 'carga', 'descarga'}


def _encontrar_en_texto(t, indice):
    """Nombres del catálogo que aparecen en el texto. Devuelve [(nombre, inicio)]."""
    hallados = []
    palabras = [w for w in re.finditer(r'[a-z0-9]{5,}', t) if w.group(0) not in _GENERICAS]
    for _, nombre, n in indice:
        if len(n) < 3:
            continue
        m = re.search(rf'\b{re.escape(n)}\b', t)
        if not m:
            primera = n.split()[0]
            if len(primera) >= 5 and primera not in _GENERICAS:
                m = re.search(rf'\b{re.escape(primera)}(?:s|es)?\b', t)
                if not m:
                    # Errores de dictado: "medlin" → MEDLINE
                    m = next((w for w in palabras
                              if difflib.SequenceMatcher(None, w.group(0), primera).ratio() >= 0.88), None)
        if m:
            hallados.append((nombre, m.start(), m.group(0)))
    return hallados


def interpretar_reglas(pregunta, user, contexto, hoy):
    t = _norm(pregunta)
    tp = _plano(pregunta)

    seguimiento = bool(contexto) and bool(re.match(
        r'^(y |ahora|solo|pero|tambien|igual|lo mismo|agrupa|ordena|ordenalo|ponlo|cambia|de esas|esas)', t))
    base = copy.deepcopy(contexto) if seguimiento and isinstance(contexto, dict) else {}
    filtros = base.get('filtros') or {}
    c = {
        'tipo': base.get('tipo'), 'titulo': '', 'filtros': filtros,
        'agrupar_por': base.get('agrupar_por') or [], 'metricas': base.get('metricas') or [],
        'columnas': base.get('columnas') or [], 'orden': base.get('orden'), 'limite': base.get('limite'),
    }

    # "hazme una presentación / un excel de ..." → la petición de datos es lo que sigue
    t = re.sub(r'\b(hazme|haz|genera(me)?|crea(me)?|arma(me)?|preparame|dame|manda(me)?)\s+(una?\s+)?'
               r'(presentacion(es)?|powerpoint|excel|reporte|informe)\s+(de|con|sobre)\s+', 'remisiones ', t)
    if re.match(r'^(hola|buen[oa]s|que tal|hey|gracias|ayuda|que puedes hacer|como funciona)', t) \
            and 'remision' not in t:
        return {'tipo': 'conversacion', 'mensaje': ''}
    if re.search(r'\b(diesel|combustible|gasolina|litros|nomina|sueldos?|vacaciones|prestamos?|empleados?'
                 r'|bancos?|cuentas por pagar|facturacion)\b', t) and 'remision' not in t:
        return {'tipo': 'conversacion', 'mensaje': (
            'Este módulo consulta **remisiones**: viajes, pesos, materiales, mermas, folios, operadores… '
            'Para diésel, nómina o bancos entra a su módulo desde el menú.')}

    desde, hasta = _periodo_reglas(tp, hoy)
    if desde or hasta:
        filtros['fecha_desde'] = desde.isoformat() if desde else None
        filtros['fecha_hasta'] = hasta.isoformat() if hasta else None
    if re.search(r'\bregistrad[oa]s\b|\bdad[oa]s de alta\b', t):
        filtros['campo_fecha'] = 'registro'
    elif 'captura' in t:
        filtros['campo_fecha'] = 'captura'
    elif re.search(r'\bfecha de carga\b', t):
        filtros['campo_fecha'] = 'carga'
    elif re.search(r'\bdestruid[oa]s\b|\bfecha de destruccion\b', t):
        filtros['campo_fecha'] = 'destruccion'

    # Folios
    folios = {
        'folio_salida': r'\bfolio de salida (?:no |numero )?([a-z0-9\-]+)',
        'folio_descarga': r'\bfolio de descarga (?:no |numero )?([a-z0-9\-]+)',
        'folio_carga': r'\bfolio de carga (?:no |numero )?([a-z0-9\-]+)',
        'folio_medline': r'\bfolio medline (?:no |numero )?([a-z0-9\-]+)',
    }
    for clave, patron in folios.items():
        m = re.search(patron, tp)
        if m and re.search(r'\d', m.group(1)):
            filtros[clave] = m.group(1).upper()
    if not any(filtros.get(k) for k in folios):
        m = re.search(r'\b(?:remision|folio)\s*(?:no |numero |num )?([a-z]{0,6}-?\d[\w\-]*)', tp)
        if m:
            filtros['remision'] = m.group(1).upper()

    # Textos: "que diga ...", placas, factura, quién auditó
    m = re.search(r'\bque (?:diga|digan|contenga|contengan|mencione|mencionen|tenga escrito)\s+(.+)$', tp)
    if m:
        filtros['texto'] = m.group(1).strip(' "\'')[:80]
    m = re.search(r'\bplacas?\s+([a-z0-9\-]*\d[a-z0-9\-]*)', tp)
    if m:
        filtros['placas'] = m.group(1).upper()
    m = re.search(r'\bfactura\s+(?:no |numero )?([a-z0-9\-]*\d[a-z0-9\-]*)', tp)
    if m:
        filtros['factura'] = m.group(1).upper()
    m = re.search(r'\bauditad[oa]s? por\s+([a-z ]{3,40}?)(?=\s+(?:en|el|la|de|del|este|esta|con)\b|$)', t)
    if m:
        filtros['auditado_por'] = m.group(1).strip()

    # Sí / no ("sin factura", "con evidencias", "destrucción pendiente"...)
    si_no = {
        'con_factura': (r'\bcon factura\b|\bfacturad[oa]s\b', r'\bsin factura\b|\bno facturad[oa]s\b|\bsin facturar\b'),
        'con_evidencia': (r'\bcon evidencias?\b', r'\bsin evidencias?\b'),
        'con_manifiesto': (r'\bcon manifiesto\b', r'\bsin manifiesto\b'),
        'con_descarga': (r'\bcon descarga\b|\bya descargad', r'\bsin descarga(?:r)?\b|\bno (?:se han |han )?descargad'),
        'con_rechazo': (r'\bcon rechazos?\b', r'\bsin rechazos?\b'),
        'con_folio_salida': (r'\bcon folio de salida\b', r'\bsin folio de salida\b'),
        'destruccion_completa': (r'\bdestruccion (?:fiscal )?complet',
                                 r'\bdestruccion (?:fiscal )?pendiente|\bpendientes? de destruccion'),
    }
    for clave, (si, no) in si_no.items():
        if re.search(no, t):
            filtros[clave] = False
        elif re.search(si, t):
            filtros[clave] = True

    # Rangos: "pendientes de más de 7 días", "de más de 20 toneladas"
    m = re.search(r'\b(?:de |con )?mas de (\d+) dias\b', t)
    if m:
        filtros['antiguedad_min'] = int(m.group(1))
    m = re.search(r'\b(?:de |con )?menos de (\d+) dias\b', t)
    if m:
        filtros['antiguedad_max'] = int(m.group(1))
    campo_peso = 'descarga' if 'descarg' in t else 'carga'
    for m in re.finditer(r'\b(mas|menos) de (\d+(?:\.\d+)?)\s*(toneladas?|tons?|t|kilos?|kilogramos?|kgs?)\b', tp):
        kg = float(m.group(2)) * (1000 if m.group(3).startswith('t') else 1)
        filtros[f'{campo_peso}_{"min" if m.group(1) == "mas" else "max"}'] = kg

    # Nombres de catálogos que aparecen en la pregunta
    restante = t
    for clave in ('empresa', 'origen', 'material', 'operador'):
        # Empresas: se reconocen TODAS; los permisos se aplican al ejecutar (así
        # una no autorizada da 0 y un aviso, en vez de ignorarse en silencio).
        indice = (_indice(clave, user) if clave != 'empresa' else
                  [(pk, n, _norm(n)) for pk, n in Empresa.objects.values_list('pk', 'nombre') if n])
        hallados = _encontrar_en_texto(restante, indice)
        if not hallados:
            continue
        if clave == 'origen':
            origenes, destinos = [], []
            for nombre, inicio, _ in hallados:
                antes = restante[max(0, inicio - 25):inicio]
                (destinos if re.search(r'\b(a|hacia|para|destino|al)\s*$', antes) else origenes).append(nombre)
            if origenes:
                filtros['origen'] = origenes
            if destinos:
                filtros['destino'] = destinos
        else:
            filtros[clave] = [nombre for nombre, _, _ in hallados]
        for _, _, texto in hallados:
            restante = restante.replace(texto, ' ')

    # Estatus
    status = []
    sin_destruccion = re.sub(r'(?:destruccion (?:fiscal )?)?pendientes? de destruccion|destruccion (?:fiscal )?pendientes?', ' ', t)
    for patron, valor in ((r'\bpendientes?\b', 'PENDIENTE'), (r'\bterminad[oa]s?\b|\bpor auditar\b', 'TERMINADO'),
                          (r'\bauditad[oa]s?\b', 'AUDITADO'), (r'\bcancelad[oa]s?\b', 'CANCELADO')):
        if re.search(patron, sin_destruccion) and not (valor == 'AUDITADO' and 'por auditar' in t):
            status.append(valor)
    if status:
        filtros['status'] = status
        # "auditadas en septiembre" = auditadas en ese periodo
        if status == ['AUDITADO'] and (desde or hasta) and 'descarg' not in t:
            filtros['campo_fecha'] = 'auditoria'

    m = re.search(r'merma\s+(?:(?:mayor|superior)\s+(?:a|al|de)|(?:de\s+)?mas\s+del?|(?:arriba|encima)\s+del?'
                  r'|por encima\s+del?|>=?)\s*(\d+(?:\.\d+)?)', tp)
    if m:
        filtros['merma_min'] = float(m.group(1))
    m = re.search(r'merma\s+(?:(?:menor|inferior)\s+(?:a|al|de)|(?:de\s+)?menos\s+del?|(?:abajo|debajo)\s+del?'
                  r'|<=?)\s*(\d+(?:\.\d+)?)', tp)
    if m:
        filtros['merma_max'] = float(m.group(1))

    # Agrupación (el orden importa: "día de la semana" antes que "día")
    dims = {
        'empresa': r'unidad(?:es)? de negocio|empresas?', 'material': r'materia(?:l|les)',
        'cliente': r'clientes?', 'origen': r'origen(?:es)?', 'destino': r'destinos?',
        'operador': r'operador(?:es)?|chofer(?:es)?', 'linea_transporte': r'lineas?(?: de transporte)?|transportistas?',
        'patio_rechazo': r'patios? de rechazo',
        'unidad': r'unidad(?:es)?|camion(?:es)?|tractos?', 'contenedor': r'contenedor(?:es)?|cajas?',
        'status': r'estatus|status|estados?', 'auditado_por': r'auditor(?:es)?|quien audito',
        'dia_semana': r'dias? de la semana', 'dia': r'dias?', 'semana': r'semanas?', 'mes': r'mes(?:es)?',
        'anio': r'anos?',
    }
    agrupar = []
    alternativas = '|'.join(f'(?:{p})' for p in dims.values())
    ranking = re.search(rf'\b(?:top\s+\d+|l[oa]s\s+\d+|que|cual(?:es)?|quien(?:es)?)\s+({alternativas})\b.*\b(?:mas|menos|mayor|menor)\b', t)
    for m in ([ranking] if ranking else []) + list(re.finditer(rf'\b(?:por|x|cada)\s+({alternativas})\b', t)):
        for dim, patron in dims.items():
            if re.fullmatch(patron, m.group(1)) and dim not in agrupar:
                agrupar.append(dim)
                break
    for palabra, dim in (('diario', 'dia'), ('semanal', 'semana'), ('mensual', 'mes'), ('anual', 'anio')):
        if re.search(rf'\b{palabra}', t) and dim not in agrupar:
            agrupar.append(dim)
    if agrupar:
        if seguimiento and agrupar[:2] != c['agrupar_por']:
            c['orden'], c['limite'] = None, None  # nueva agrupación: orden y tope por defecto
        c['agrupar_por'] = agrupar[:2]

    # Métricas y orden
    ton = 'tonelada' in t
    metricas = ['remisiones', 'carga_ton' if ton else 'carga_kg', 'descarga_ton' if ton else 'descarga_kg']
    if 'rechazo' in t:
        metricas.append('rechazo_ton' if ton else 'rechazo_kg')
    metricas.append('merma_pct')
    extras = []
    if 'bulto' in t:
        extras.append('bultos')
    if 'promedio' in t:
        extras += ['promedio_carga_kg', 'promedio_descarga_kg']
    if re.search(r'\btiempos?\b|\btarda|\bcuanto dura', t):
        extras += ['tiempo_carga_h', 'tiempo_descarga_h']
    if 'transito' in t:
        extras.append('tiempo_transito_h')
    if re.search(r'\bimportes?\b|\bventas?\b|\bdinero\b|\bprecios?\b|\bvendi', t):
        extras.append('importe')
    if 'bascula' in t:
        extras.append('peso_bascula_kg')
    metricas += [m for m in extras if m not in metricas]
    if not seguimiento or ton or 'rechazo' in t or extras:
        c['metricas'] = metricas
    if ton and not seguimiento:
        c['columnas'] = []

    m = (re.search(r'\b(?:top|los|las|primer[oa]s|principales)\s+(\d{1,3})\b', t)
         or re.search(r'\b(\d{1,3})\s+(?:principales|mayores|primer[oa]s)\b', t))
    if m and re.search(r'\b(mas|mayor|mayores|top|menos|menor|principales)\b', t):
        c['limite'] = int(m.group(1))
        asc = bool(re.search(r'\b(menos|menor)\b', t))
        campo = 'remisiones' if re.search(r'viaje|remision', t) else ('descarga_ton' if ton else 'descarga_kg')
        if 'merma' in t:
            campo = 'merma_pct'
        elif 'importe' in extras:
            campo = 'importe'
        elif 'tiempo_carga_h' in extras:
            campo = 'tiempo_carga_h' if re.search(r'\bcarga', t) and 'descarg' not in t else 'tiempo_descarga_h'
        c['orden'] = {'campo': campo, 'dir': 'asc' if asc else 'desc'}

    if c['agrupar_por']:
        c['tipo'] = 'agrupado'
    elif not seguimiento or not c['tipo']:
        cuantos = re.search(r'\b(cuant[oa]s?|total(es)?|suma|cuanto)\b', t)
        listar = re.search(r'\b(lista|listado|cuales|muestra|muestrame|dame|ver|detalle|ensena)\b', t)
        c['tipo'] = 'total' if cuantos and not listar else 'lista'
    if not c['tipo']:
        c['tipo'] = 'lista'

    # Datos extra pedidos para la lista: "con operador, folios y factura"
    if c['tipo'] == 'lista':
        extras = []
        for patron, claves in COLUMNAS_POR_PALABRA:
            if re.search(patron, t):
                extras += [k for k in claves if k not in extras]
        if extras:
            defecto = [k.replace('_kg', '_ton') if ton else k for k in COLUMNAS_DEFECTO]
            base_cols = [k for k in (c['columnas'] or defecto) if k != 'status']
            c['columnas'] = base_cols + [k for k in extras if k not in base_cols] + ['status']
        if re.search(r'\b(todos los datos|toda la informacion|todas las columnas|todos los campos'
                     r'|datos completos|informacion completa|todo de la remision)\b', t):
            c['columnas'] = list(COLUMNAS)

    for nombre in ('proboca', 'huaxing', 'bachoco', 'trane'):
        if re.search(rf'\b(reporte|formato)\b.*\b{nombre}\b', t):
            c['reporte_formal'] = nombre
    if re.search(r'\b(reporte|formato)\b.*\bsealed air\b', t):
        c['reporte_formal'] = 'sealed-air'

    c['titulo'] = (pregunta.strip().rstrip('?¿.').strip('¿ ')[:80] or 'Reporte de remisiones')
    c['titulo'] = c['titulo'][0].upper() + c['titulo'][1:]
    return c


# ════════════════════════════════════════════════════════════════════════════
# VISTAS
# ════════════════════════════════════════════════════════════════════════════

class _Encoder(json.JSONEncoder):
    """Fechas en ISO; las horas en la zona local (America/Monterrey)."""
    def default(self, o):
        if isinstance(o, dt.datetime):
            return (timezone.localtime(o) if timezone.is_aware(o) else o).isoformat()
        if isinstance(o, dt.date):
            return o.isoformat()
        if isinstance(o, dt.time):
            return o.strftime('%H:%M')
        return super().default(o)


def _respuesta(datos, status=200):
    return JsonResponse(datos, status=status, encoder=_Encoder)


def _con_errores(vista):
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'detail': 'No autenticado.'}, status=401)
        if not puede_usar(request.user):
            return JsonResponse({'detail': 'No tienes acceso al módulo de Remisiones.'}, status=403)
        try:
            return vista(request, *args, **kwargs)
        except ErrorReporte as e:
            return JsonResponse({'detail': e.detalle}, status=e.status)
    envoltura.__name__ = vista.__name__
    return envoltura


def _dentro_del_limite(user):
    clave = f'reportes-ia:{user.pk}'
    if cache.add(clave, 1, VENTANA_SEG):
        return True
    try:
        return cache.incr(clave) <= PETICIONES_POR_VENTANA
    except ValueError:
        cache.set(clave, 1, VENTANA_SEG)
        return True


AYUDA = ('Soy el asistente de **Reportes con IA**. Pídeme datos de tus remisiones con texto o con el '
         'micrófono, por ejemplo: "¿cuántas remisiones de PROBOCA llevamos este mes?", '
         '"toneladas descargadas por material el mes pasado" o "remisiones pendientes de esta semana '
         'con operador y folios". Te contesto con los datos y puedes descargarlos en Excel.')


def _bloque(consulta, resultado):
    """Un bloque de datos para la pantalla: una consulta con su tabla y su Excel."""
    return {
        'tipo': consulta['tipo'], 'titulo': resultado['titulo'],
        'filtros_texto': resultado['filtros_texto'], 'resumen': resultado['resumen'],
        'tabla': resultado['tabla'], 'consulta': consulta, 'reporte_formal': resultado['reporte_formal'],
    }


def _entregable(pregunta):
    """'presentacion' o 'excel' si la pregunta pide ese archivo (se descarga solo)."""
    t = _norm(pregunta)
    if re.search(r'\b(presentacion(es)?|powerpoint|power point|diapositivas?|ppt|pptx)\b', t):
        return 'presentacion'
    if re.search(r'\b(excel|hoja de calculo|xlsx)\b', t):
        return 'excel'
    return None


def _nombre_modelo(modelo):
    """'claude-haiku-5-5' → 'Claude Haiku 5.5'."""
    partes = modelo.split('-')
    if len(partes) >= 3 and partes[0] == 'claude':
        version = '.'.join(p for p in partes[2:] if p.isdigit())
        return f'Claude {partes[1].capitalize()} {version}'.strip()
    return modelo


@require_http_methods(['GET', 'POST'])
@_con_errores
def api_reportes_ia(request):
    """GET: estado del módulo (IA conectada, empresas).
    POST {pregunta, contexto?, historial?: [{pregunta, respuesta}]}: responde con texto
    y los bloques de datos de cada consulta que se hizo para contestar."""
    user = request.user
    if request.method == 'GET':
        if _config_agente():
            proveedor, nombre = 'anthropic', _nombre_modelo(MODELO_AGENTE)
        else:
            proveedor = ia_disponible()
            nombre = NOMBRE_PROVEEDOR.get(proveedor or '', proveedor or '')
        return JsonResponse({
            'ia_disponible': bool(proveedor),
            'agente': proveedor == 'anthropic',
            'proveedor': proveedor,
            'proveedor_nombre': nombre,
            'empresas': list(_empresas_permitidas(user).order_by('nombre').values_list('nombre', flat=True)[:40]),
            'hoy': _hoy().isoformat(),
        })

    try:
        body = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise ErrorReporte('Datos no válidos.')
    pregunta = ' '.join(str(body.get('pregunta') or '').split())[:MAX_PREGUNTA]
    if not pregunta:
        raise ErrorReporte('Escribe o dicta tu pregunta.')
    if not _dentro_del_limite(user):
        raise ErrorReporte('Hiciste muchas consultas seguidas. Espera unos minutos e intenta de nuevo.', 429)
    contexto = body.get('contexto') if isinstance(body.get('contexto'), dict) else None
    historial = [
        {'pregunta': ' '.join(str(h.get('pregunta') or '').split())[:MAX_PREGUNTA],
         'respuesta': str(h.get('respuesta') or '')[:3000]}
        for h in (body.get('historial') or []) if isinstance(h, dict)
    ][-3:]
    previas = [h['pregunta'] for h in historial if h['pregunta']]
    conversacion = re.sub(r'[^A-Za-z0-9\-]', '', str(body.get('conversacion') or ''))[:40]

    inicio = time.monotonic()
    duracion = lambda: int((time.monotonic() - inicio) * 1000)  # noqa: E731
    avisos_motor = []
    uso = uso_vacio()

    def responder(datos):
        _registrar(user, pregunta, conversacion, datos, uso)
        return _respuesta(datos)

    # 1) Agente con Claude: contesta cualquier pregunta usando consultas seguras
    api_key = _config_agente()
    if api_key:
        try:
            texto, consultas = responder_con_agente(pregunta, user, api_key, historial, contexto, uso)
            bloques = [_bloque(c, r) for c, r in consultas]
            avisos = []
            for _, r in consultas:
                avisos += [a for a in r['avisos'] if a not in avisos]
            logger.info('Reportes IA [%s] %s → agente con %d consultas', user.username, pregunta, len(consultas))
            return responder({
                'tipo': 'datos' if bloques else 'conversacion', 'motor': 'ia', 'proveedor': 'anthropic',
                'proveedor_nombre': _nombre_modelo(MODELO_AGENTE),
                'titulo': bloques[-1]['titulo'] if bloques else '', 'respuesta': texto, 'avisos': avisos,
                'resultados': bloques, 'consulta': bloques[-1]['consulta'] if bloques else contexto,
                'entregable': _entregable(pregunta) if bloques else None, 'duracion_ms': duracion(),
            })
        except AgenteNoDisponible as e:
            avisos_motor.append(e.aviso)

    # 2) Respaldo: otra IA traduce a UNA consulta, o el intérprete básico
    cruda, motor, proveedor, aviso = interpretar(pregunta, user, contexto, previas,
                                                 incluir_anthropic=not api_key)
    if aviso:
        avisos_motor.append(aviso)
    consulta = normalizar(cruda)
    base = {'motor': motor, 'proveedor': proveedor,
            'proveedor_nombre': NOMBRE_PROVEEDOR.get(proveedor or '', proveedor or '')}

    if consulta['tipo'] == 'conversacion':
        return responder({
            **base, 'tipo': 'conversacion', 'titulo': '', 'respuesta': consulta['mensaje'] or AYUDA,
            'avisos': avisos_motor, 'resultados': [], 'consulta': contexto, 'duracion_ms': duracion(),
        })

    try:
        resultado = ejecutar(consulta, user)
    except Exception:
        logger.exception('Reportes IA: falló la consulta %s', consulta)
        raise ErrorReporte('No pude obtener esos datos. Intenta decirlo de otra forma.', 500)

    logger.info('Reportes IA [%s] %s → %s', user.username, pregunta, json.dumps(consulta, ensure_ascii=False))
    return responder({
        **base, 'tipo': 'datos', 'titulo': resultado['titulo'], 'respuesta': redactar(consulta, resultado),
        'avisos': avisos_motor + resultado['avisos'], 'resultados': [_bloque(consulta, resultado)],
        'consulta': consulta, 'entregable': _entregable(pregunta), 'duracion_ms': duracion(),
    })


def _registrar(user, pregunta, conversacion, datos, uso):
    """Guarda la petición en la bitácora (panel Consumo de IA). Nunca rompe la respuesta."""
    from decimal import Decimal
    from django.db import transaction
    from .models import RegistroReporteIA
    claude = uso['llamadas'] > 0
    registro = RegistroReporteIA(
        usuario=user, conversacion=conversacion, pregunta=pregunta,
        respuesta=datos.get('respuesta') or '', motor=datos.get('motor') or '',
        proveedor=datos.get('proveedor') or ('anthropic' if claude else ''),
        # Si Claude falló y respondió el respaldo, el costo es el de Claude
        modelo=uso['modelo'] if claude else (datos.get('proveedor') or ''),
        consultas=[b['consulta'] for b in datos.get('resultados') or []],
        num_consultas=len(datos.get('resultados') or []),
        llamadas_modelo=uso['llamadas'], tokens_entrada=uso['entrada'], tokens_salida=uso['salida'],
        tokens_cache_lectura=uso['cache_lectura'], tokens_cache_escritura=uso['cache_escritura'],
        costo_usd=Decimal(str(round(uso['costo_usd'], 6))),
        # Claude informa sus tokens; el intérprete básico no gasta; otros proveedores no informan
        medido=claude or datos.get('motor') == 'reglas',
        duracion_ms=datos.get('duracion_ms') or 0, avisos=datos.get('avisos') or [],
    )
    try:
        with transaction.atomic():  # si falla, no arrastra la transacción de la petición
            registro.save()
    except Exception:
        logger.exception('Reportes IA: no se pudo guardar la bitácora')


MAX_CONSULTAS_DESCARGA = 8


def _peticion_descarga(request):
    """consultas=<JSON lista> (o consulta=<JSON>) + titulo, pregunta y respuesta opcionales.
    Las cifras se vuelven a calcular aquí: del navegador solo llegan las consultas."""
    try:
        if request.POST.get('consultas'):
            consultas = json.loads(request.POST['consultas'])
        else:
            consultas = [json.loads(request.POST.get('consulta') or '{}')]
    except ValueError:
        raise ErrorReporte('Consulta no válida.')
    if not isinstance(consultas, list):
        raise ErrorReporte('Consulta no válida.')
    consultas = [c for c in consultas if isinstance(c, dict)][:MAX_CONSULTAS_DESCARGA]
    textos = {k: ' '.join(str(request.POST.get(k) or '').split()) if k != 'respuesta'
              else str(request.POST.get(k) or '').strip()
              for k in ('titulo', 'pregunta', 'respuesta')}
    textos['titulo'] = textos['titulo'][:120]
    textos['pregunta'] = textos['pregunta'][:MAX_PREGUNTA]
    textos['respuesta'] = textos['respuesta'][:4000]
    return consultas, textos


def _archivo(contenido, tipo, titulo, extension):
    sin_acentos = unicodedata.normalize('NFD', titulo or '').encode('ascii', 'ignore').decode('ascii')
    nombre = re.sub(r'[^A-Za-z0-9]+', '_', sin_acentos).strip('_')[:60] or 'Reporte'
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta['Content-Disposition'] = f'attachment; filename="Reporte_IA_{nombre}_{_hoy().isoformat()}.{extension}"'
    return respuesta


@require_http_methods(['POST'])
@_con_errores
def api_reportes_ia_excel(request):
    """Excel con fórmulas: hoja Resumen + una hoja por consulta (todos los renglones)."""
    from .reportes_ia_export import construir_excel, ejecutar_consultas
    consultas, textos = _peticion_descarga(request)
    hojas = ejecutar_consultas(consultas, request.user, para_excel=True)
    if not hojas:
        raise ErrorReporte('Esa respuesta no tiene datos para exportar.')
    titulo = textos['titulo'] or hojas[0][1]['titulo']
    contenido = construir_excel(hojas, request.user, titulo, textos['pregunta'], textos['respuesta'])
    return _archivo(contenido, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', titulo, 'xlsx')


@require_http_methods(['POST'])
@_con_errores
def api_reportes_ia_presentacion(request):
    """Presentación de PowerPoint: portada, respuesta e indicadores y una diapositiva por consulta."""
    from .reportes_ia_export import construir_presentacion, ejecutar_consultas
    consultas, textos = _peticion_descarga(request)
    hojas = ejecutar_consultas(consultas, request.user, para_excel=False)
    if not hojas:
        raise ErrorReporte('Esa respuesta no tiene datos para la presentación.')
    titulo = textos['titulo'] or hojas[0][1]['titulo']
    contenido = construir_presentacion(hojas, request.user, titulo, textos['pregunta'], textos['respuesta'])
    return _archivo(contenido, 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    titulo, 'pptx')
