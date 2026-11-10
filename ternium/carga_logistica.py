"""
Carga masiva de registros de logística (salidas a Ternium) desde el Excel
"REPORTE DE SALIDAS TERNIUM" (una hoja por mes: ENERO, FEBRERO…).

HTML: /registros-logistica/carga-masiva/. Se sube el Excel y se revisa renglón por
renglón sin guardar nada (api_revisar); al confirmar (api_importar) se vuelve a leer el
mismo archivo y se dan de alta, todas juntas o ninguna, solo las remisiones que no
existen. Lo que ya está en el sistema no se modifica.

Reglas:
- La remisión es la llave. Se compara sin espacios, guiones ni ceros a la izquierda
  (C-0547 = C00547). Si se repite dentro del archivo se sube una sola: la elegida en la
  revisión; por omisión la primera que no es rechazo.
- Fechas: si el día y el mes vienen volteados (1/7 en la hoja JULIO) se corrigen con el
  mes de la hoja. Las que aun así no cuadran con la hoja quedan marcadas con una fecha
  sugerida (mismo día, mes de la hoja, año del archivo), que solo se usa si el usuario
  lo pide. La entrega se corrige igual comparándola con la carga (de 3 días antes a 60
  después); si no cuadra, la sugerida lleva el mismo día en el mes de la carga o el siguiente.
- Rechazo: "RECHAZ…" en entrega, toneladas recibidas, factura, papeles, permiso, folio
  MTY o comentarios → estatus Rechazado; si no trae toneladas remisionadas se sube con 0.
- Transportistas: los parecidos se juntan con el del catálogo (TARNSPORTES MORANTES →
  MORANTES); los que no existen se dan de alta. Materiales: por código de Ternium con su
  descripción; los que no existen se dan de alta. Los que se usan quedan ligados a
  Ternium (si no, no aparecerían al editar el registro).
- Comentarios 3R, factura, papeles, penalización, costo, folio MTY y kilos facturados
  van a Comentarios. Permiso de circulación → Número de Permiso SCT.
"""
import datetime as dt
import difflib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

from .models import Empresa, LineaTransporte, Material, RegistroLogistico

MAX_ARCHIVO = 15 * 1024 * 1024
MAX_COLUMNAS = 60
MESES = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO',
         'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
ERRORES_EXCEL = {'#REF!', '#DIV/0!', '#N/A', '#VALUE!', '#ERROR!', '#NAME?', '#NUM!', '#NULL!', '#SPILL!', '#CALC!'}

# campo → encabezados aceptados (sin acentos, en mayúsculas)
COLUMNAS = {
    'fecha_carga': ('FECHA CARGA', 'FECHA DE CARGA'),
    'boleta': ('# BOLETA BASCULA', 'BOLETA BASCULA', 'NO. BOLETA BASCULA', 'BOLETA'),
    'remision': ('REMISION',),
    'transportista': ('TRANSPORTISTA',),
    'placas_tractor': ('PLACA TRACTOR', 'PLACAS TRACTOR'),
    'placas_tolva': ('PLACA TOLVA', 'PLACAS TOLVA'),
    'tractor': ('NO. TRACTOR', 'NO TRACTOR', '# TRACTOR'),
    'tolva': ('NO. TOLVA', 'NO TOLVA', '# TOLVA'),
    'chofer': ('CHOFER',),
    'ton_rem': ('TONELADAS REMISIONADAS', 'TONELADAS REMISIONADA'),
    'fecha_entrega': ('FECHA ENTREGA A TERNIUM', 'FECHA DE ENTREGA A TERNIUM', 'FECHA ENTREGA'),
    'ton_rec': ('TONELADAS RECIBIDAS TERNIUM', 'TONELADAS RECIBIDAS'),
    'codigo_material': ('CODIGO MATERIAL', 'CODIGO DE MATERIAL'),
    'material': ('DESCRIPCION DEL MATERIAL', 'DESCRIPCION MATERIAL', 'MATERIAL'),
    'permiso': ('PERMISO CIRCULACION', 'PERMISO CIRULACION', 'PERMISO DE CIRCULACION'),
    'comentarios': ('COMENTARIOS 3R', 'COMENTARIOS'),
    'papeles': ('PAPELES',),
    'factura': ('FACTURA',),
    'penalizacion': ('PENALIZACION',),
    'costo': ('COSTO',),
    'folio_mty': ('FOLIO MTY',),
    'kilos_facturados': ('KILOS FACTURADOS',),
}
ETIQUETAS = {
    'fecha_entrega': 'Entrega', 'ton_rec': 'Ton. recibidas', 'factura': 'Factura', 'papeles': 'Papeles',
    'permiso': 'Permiso', 'folio_mty': 'Folio MTY', 'comentarios': 'Comentarios', 'penalizacion': 'Penalización',
    'costo': 'Costo', 'kilos_facturados': 'Kilos facturados',
}
DONDE_RECHAZO = ('fecha_entrega', 'ton_rec', 'factura', 'papeles', 'permiso', 'folio_mty', 'comentarios')
A_COMENTARIOS = ('factura', 'papeles', 'penalizacion', 'costo', 'folio_mty', 'kilos_facturados')


class ErrorCarga(Exception):
    """Error que se muestra tal cual al usuario."""


# ---------------------------------------------------------------- textos y números

def _norm(valor):
    """Sin acentos, en mayúsculas y con un solo espacio."""
    s = unicodedata.normalize('NFKD', str(valor if valor is not None else ''))
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).split()).upper()


def _clave(valor):
    """Para comparar nombres: solo letras y números."""
    return ' '.join(re.sub(r'[^A-Z0-9]+', ' ', _norm(valor)).split())


def _nucleo(nombre):
    """Nombre del transportista sin "TRANSPORTES" (aunque venga mal escrito) ni "SA DE CV"."""
    partes = _clave(nombre).split()
    if len(partes) > 1 and difflib.SequenceMatcher(None, partes[0], 'TRANSPORTES').ratio() >= 0.8:
        partes = partes[1:]
    return re.sub(r'\s+(S\s?A|S\s?A\s+DE\s+C\s?V|S\s+DE\s+R\s?L(\s+DE\s+C\s?V)?)$', '', ' '.join(partes))


def _limpiar_material(texto):
    """Descripción en mayúsculas y sin espacios dentro de los paréntesis; '' si no trae letras."""
    if not re.search(r'[A-Za-z]', texto or ''):
        return ''
    return re.sub(r'\s+\)', ')', re.sub(r'\(\s+', '(', ' '.join(texto.split()))).upper()


def _texto(valor, largo=None):
    if valor is None or isinstance(valor, bool):
        return ''
    if isinstance(valor, float):
        s = str(int(valor)) if valor.is_integer() else f'{valor:.6f}'.rstrip('0').rstrip('.')
    elif isinstance(valor, (dt.datetime, dt.date)):
        s = valor.strftime('%d/%m/%Y')
    else:
        s = ' '.join(str(valor).split())
    if s.upper() in ERRORES_EXCEL:
        return ''
    return s[:largo] if largo else s


def _ton(valor):
    """Toneladas con 3 decimales, o None si no es número."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip().replace(',', '')
        if not re.fullmatch(r'-?\d+(\.\d+)?', valor):
            return None
    try:
        n = Decimal(str(valor)).quantize(Decimal('0.001'))
    except (InvalidOperation, ValueError):
        return None
    return n if abs(n) < Decimal('10000000') else None


def llave_remision(texto):
    """C-0547, c 00547 y C00547 son la misma remisión."""
    s = re.sub(r'[\s\-_./]', '', _norm(texto))
    m = re.fullmatch(r'([A-Z]*)0*(\d+)', s)
    return f'{m[1]}{int(m[2])}' if m else s


# ---------------------------------------------------------------- fechas

def _fecha(anio, mes, dia):
    try:
        return dt.date(anio, mes, dia)
    except (ValueError, TypeError):
        return None


def _larga(f):
    return f'{f.day} de {MESES[f.month - 1].lower()} de {f.year}'


def candidatos_fecha(valor):
    """Fechas posibles de una celda: [(fecha, volteada)]. La primera es la lectura tal cual;
    si el día puede ser mes, sigue la misma fecha con día y mes volteados."""
    if isinstance(valor, dt.datetime):
        valor = valor.date()
    elif isinstance(valor, (int, float)) and not isinstance(valor, bool) and 20000 <= valor <= 80000:
        try:
            valor = from_excel(valor).date()  # número de serie de Excel
        except (ValueError, TypeError, OverflowError):
            return []
    if isinstance(valor, dt.date):
        posibles = [(valor, False)]
        if valor.day <= 12 and valor.day != valor.month:
            volteada = _fecha(valor.year, valor.day, valor.month)
            if volteada:
                posibles.append((volteada, True))
        return posibles
    if not isinstance(valor, str):
        return []
    s = valor.strip()
    m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?', s)
    if m:
        f = _fecha(int(m[1]), int(m[2]), int(m[3]))
        return candidatos_fecha(f) if f else []
    m = re.fullmatch(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})', s)
    if not m:
        return []
    a, b, anio = int(m[1]), int(m[2]), int(m[3])
    anio += 2000 if anio < 100 else 0
    posibles = []
    for mes, dia in ((a, b), (b, a)):  # como texto vienen mes/día; también se acepta día/mes
        f = _fecha(anio, mes, dia)
        if f and all(f != x for x, _ in posibles):
            posibles.append((f, False))
    return posibles


def _elegir_carga(posibles, mes, anio, hoja):
    """→ (fecha, sugerida, aviso, corrección). Sin mes (hoja que no es de un mes) se toma tal cual."""
    if not mes:
        return posibles[0][0], None, None, None
    for f, volteada in posibles:
        if f.month == mes and f.year == anio:
            return f, None, None, (f'Día y mes volteados, se corrigió (venía {_larga(posibles[0][0])})' if volteada else None)
    for f, volteada in posibles:
        if f.month == mes:
            sug = _fecha(anio, mes, f.day)
            return f, sug, (f'{"Día y mes volteados; " if volteada else ""}el año ({f.year}) no cuadra con el del '
                            f'archivo ({anio}).' + (f' Sugerida: {_larga(sug)}' if sug else '')), None
    f = posibles[0][0]
    sug = _fecha(anio, mes, f.day)
    return f, sug, (f'La fecha ({_larga(f)}) no cuadra con la hoja {hoja}.'
                    + (f' Sugerida: {_larga(sug)}' if sug else '')), None


def _en_rango(f, carga):
    return carga - dt.timedelta(days=3) <= f <= carga + dt.timedelta(days=60)


def _elegir_entrega(posibles, carga):
    """La lectura que cae entre 3 días antes y 60 después de la carga (de preferencia la que viene).
    Si ninguna cae: sugerida con el mismo día en el mes de la carga o en el siguiente.
    → (fecha, sugerida, aviso, corrección)."""
    if not carga:
        return posibles[0][0], None, None, None
    validas = [(f, v) for f, v in posibles if _en_rango(f, carga)]
    if validas:
        f, volteada = validas[0] if validas[0] == posibles[0] else min(validas, key=lambda x: abs((x[0] - carga).days))
        return f, None, None, (f'Entrega: día y mes volteados, se corrigió (venía {_larga(posibles[0][0])})' if volteada else None)
    sug = None
    for dia in dict.fromkeys(f.day for f, _ in posibles):
        for k in (0, 1):
            m = carga.month + k
            x = _fecha(carga.year + (m - 1) // 12, (m - 1) % 12 + 1, dia)
            if x and _en_rango(x, carga):
                sug = x
                break
        if sug:
            break
    return posibles[0][0], sug, (f'La fecha de entrega ({_larga(posibles[0][0])}) no cuadra con la de carga.'
                                 + (f' Sugerida: {_larga(sug)}' if sug else '')), None


# ---------------------------------------------------------------- lectura del Excel

def _encabezado(filas):
    """(índice del renglón de encabezados, {campo: columna}) o None."""
    for i, fila in enumerate(filas[:40]):
        nombres = [_norm(v) for v in fila]
        if 'REMISION' not in nombres or not any(a in nombres for a in COLUMNAS['fecha_carga']):
            continue
        col = {}
        for campo, alias in COLUMNAS.items():
            for a in alias:
                if a in nombres:
                    col[campo] = nombres.index(a)
                    break
        return i, col
    return None


def _mes_de(titulo):
    t = _norm(titulo).replace('SETIEMBRE', 'SEPTIEMBRE')
    return next((i + 1 for i, nombre in enumerate(MESES) if t.startswith(nombre[:3])), None)


def _leer_libro(archivo):
    try:
        libro = load_workbook(archivo, read_only=True, data_only=True)
    except Exception:
        raise ErrorCarga('No se pudo leer el archivo: debe ser un Excel .xlsx.')
    hojas, omitidas = [], []
    try:
        for ws in libro.worksheets:
            filas, vacias = [], 0
            for fila in ws.iter_rows(max_col=MAX_COLUMNAS, values_only=True):
                vacias = 0 if any(v not in (None, '') for v in fila) else vacias + 1
                if vacias > 300:
                    break
                filas.append(fila)
            enc = _encabezado(filas)
            if enc:
                hojas.append((ws.title, enc, filas))
            else:
                omitidas.append(ws.title)
    finally:
        libro.close()
    if not hojas:
        raise ErrorCarga('No se encontró ninguna hoja con encabezados REMISION y FECHA CARGA.')
    return hojas, omitidas


# ---------------------------------------------------------------- catálogos

class _Catalogos:
    """Transportistas y materiales del Excel → los del sistema (o nuevos, que se crean al importar)."""

    def __init__(self, crudos):
        self.ternium = Empresa.objects.filter(nombre__iexact='TERNIUM').first()
        en_ternium_t = set(self.ternium.lineas_transporte.values_list('id', flat=True)) if self.ternium else set()
        en_ternium_m = set(self.ternium.materiales.values_list('id', flat=True)) if self.ternium else set()
        uso = dict(RegistroLogistico.objects.order_by().filter(transportista__isnull=False)
                   .values_list('transportista').annotate(n=Count('id')))
        mejores = {}
        for lt in LineaTransporte.objects.all():
            k = _nucleo(lt.nombre)
            puntos = (lt.id in en_ternium_t, uso.get(lt.id, 0), k == _clave(lt.nombre))
            if k and (k not in mejores or puntos > mejores[k][0]):
                mejores[k] = (puntos, lt)
        self._transportistas = {k: lt for k, (_, lt) in mejores.items()}
        self._en_ternium_t, self._en_ternium_m = en_ternium_t, en_ternium_m
        self._materiales = {}
        for mat in Material.objects.all():
            k = _clave(mat.nombre)
            if k and (k not in self._materiales or (mat.id in en_ternium_m and self._materiales[k].id not in en_ternium_m)):
                self._materiales[k] = mat
        self._por_excel_t, self._por_id_t, self._nuevos_t = {}, {}, {}
        self._por_codigo_m, self._por_id_m, self._nuevos_m = {}, {}, {}
        # descripción más usada de cada código de material
        descripciones = defaultdict(Counter)
        for c in crudos:
            codigo = re.sub(r'\D', '', _texto(c['v'].get('codigo_material')))
            desc = _limpiar_material(_texto(c['v'].get('material')))
            if codigo and desc:
                descripciones[codigo][desc] += 1
        self._descripcion = {k: v.most_common(1)[0][0] for k, v in descripciones.items()}

    def _entrada(self, obj, nuevo, nombre, en_ternium):
        return {'obj': obj, 'nuevo': nuevo, 'nombre': nombre[:150],
                'ligar_ternium': bool(self.ternium) and not en_ternium, 'excel': set()}

    def transportista(self, nombre):
        if not nombre:
            return None
        k = _clave(nombre)
        if k not in self._por_excel_t:
            nucleo = _nucleo(nombre)
            lt = self._transportistas.get(nucleo)
            if not lt and len(nucleo) >= 5:
                cerca = difflib.get_close_matches(nucleo, [x for x in self._transportistas if len(x) >= 5], 1, 0.85)
                lt = self._transportistas[cerca[0]] if cerca else None
            if lt:
                e = self._por_id_t.setdefault(lt.id, self._entrada(lt, False, lt.nombre, lt.id in self._en_ternium_t))
            else:
                cerca = difflib.get_close_matches(nucleo, [x for x in self._nuevos_t if len(x) >= 5], 1, 0.85) if len(nucleo) >= 5 else []
                clave = cerca[0] if cerca else nucleo
                e = self._nuevos_t.setdefault(clave, self._entrada(None, True, clave, False))
            self._por_excel_t[k] = e
        e = self._por_excel_t[k]
        e['excel'].add(_norm(nombre))
        return e

    def material(self, codigo, descripcion):
        codigo = re.sub(r'\D', '', codigo)
        desc = _limpiar_material(descripcion)
        nombre = self._descripcion.get(codigo) or desc
        if not nombre and not codigo:
            return None
        llave = codigo or 'D:' + _clave(nombre)
        if llave not in self._por_codigo_m:
            mat = self._materiales.get(_clave(nombre)) if nombre else None
            if not mat and codigo:  # por si en el sistema el nombre lleva el código
                mat = next((m for k, m in self._materiales.items() if codigo in k.split()), None)
            if mat:
                e = self._por_id_m.setdefault(mat.id, self._entrada(mat, False, mat.nombre, mat.id in self._en_ternium_m))
            else:
                nombre = nombre or f'MATERIAL {codigo}'
                e = self._nuevos_m.setdefault(_clave(nombre), self._entrada(None, True, nombre, False))
            self._por_codigo_m[llave] = e
        e = self._por_codigo_m[llave]
        e['excel'].add(' '.join(x for x in (codigo, desc) if x))
        return e

    def transportistas(self):
        return [*self._por_id_t.values(), *self._nuevos_t.values()]

    def materiales(self):
        return [*self._por_id_m.values(), *self._nuevos_m.values()]


# ---------------------------------------------------------------- revisión

def _interpretar(c, anio, cat):
    """Un renglón del Excel → dict con lo que se guardaría, avisos y errores. None si es un renglón vacío o de totales."""
    v, hoja, n, mes = c['v'], c['hoja'], c['renglon'], c['mes']
    remision = _texto(v.get('remision'))
    t = {k: _texto(v.get(k)) for k in COLUMNAS}
    fila = {'key': f'{hoja}:{n}', 'hoja': hoja, 'renglon': n, 'remision': remision.upper()[:100],
            'llave': llave_remision(remision), 'errores': [], 'avisos': [], 'correcciones': [], 'fecha': None,
            'sugerida': None, 'entrega': None, 'entrega_sugerida': None, 't': None, 'm': None, 'ton_rem': None,
            'ton_rec': None, 'status': 'PENDIENTE', 'motivo_rechazo': '', 'boleta': t['boleta'][:100], 'comentario': ''}
    if not remision:
        if not (t['fecha_carga'] or t['transportista']):
            return None  # renglón vacío o de totales
        fila['errores'].append('Sin remisión')
        return fila
    if not any(t[k] for k in ('fecha_carga', 'transportista', 'ton_rem', 'chofer')):
        return None  # remisión sin ningún dato (folio apartado)
    if len(remision) > 100:
        fila['errores'].append('La remisión es demasiado larga')

    rechazo = next((k for k in DONDE_RECHAZO if 'RECHAZ' in _norm(t[k])), None)
    if rechazo:
        fila['status'], fila['motivo_rechazo'] = 'RECHAZADO', f'{ETIQUETAS[rechazo]}: {t[rechazo]}'
    notas = []

    def anotar(aviso, correccion):
        if aviso:
            fila['avisos'].append(aviso)
        if correccion:
            fila['correcciones'].append(correccion)

    posibles = candidatos_fecha(v.get('fecha_carga'))
    if posibles:
        fila['fecha'], fila['sugerida'], *notas_fecha = _elegir_carga(posibles, mes, anio, hoja)
        anotar(*notas_fecha)
    else:
        fila['errores'].append(f'Fecha de carga no válida: "{t["fecha_carga"]}"' if t['fecha_carga'] else 'Sin fecha de carga')

    posibles = candidatos_fecha(v.get('fecha_entrega'))
    if posibles:
        fila['entrega'], fila['entrega_sugerida'], *notas_fecha = _elegir_entrega(posibles, fila['sugerida'] or fila['fecha'])
        anotar(*notas_fecha)
    elif t['fecha_entrega'] and 'RECHAZ' not in _norm(t['fecha_entrega']):
        notas.append(f'Entrega en el Excel: {t["fecha_entrega"]}')
        fila['avisos'].append(f'La entrega no es una fecha ("{t["fecha_entrega"]}"): queda vacía y el texto va a Comentarios')

    fila['ton_rem'] = _ton(v.get('ton_rem'))
    if fila['ton_rem'] is None:
        if rechazo:
            fila['ton_rem'] = Decimal('0.000')
            fila['avisos'].append('Sin toneladas remisionadas: se sube con 0')
        else:
            fila['errores'].append(f'Toneladas remisionadas no válidas: "{t["ton_rem"]}"' if t['ton_rem'] else 'Sin toneladas remisionadas')
    fila['ton_rec'] = _ton(v.get('ton_rec'))
    if fila['ton_rec'] is None and t['ton_rec'] and 'RECHAZ' not in _norm(t['ton_rec']):
        notas.append(f'Ton. recibidas en el Excel: {t["ton_rec"]}')

    fila['t'] = cat.transportista(t['transportista'])
    fila['m'] = cat.material(t['codigo_material'], t['material'])
    if not fila['t']:
        fila['avisos'].append('Sin transportista')
    if not fila['m']:
        fila['avisos'].append('Sin material')

    fila.update({
        'chofer': t['chofer'][:200], 'tractor': t['tractor'][:100], 'tolva': t['tolva'][:100],
        'placas_tractor': t['placas_tractor'].upper()[:50], 'placas_tolva': t['placas_tolva'].upper()[:50],
        'permiso': '' if 'RECHAZ' in _norm(t['permiso']) else t['permiso'][:50],
    })
    partes = [t['comentarios']] if t['comentarios'] else []
    for k in A_COMENTARIOS:
        if t[k] and not (k == 'folio_mty' and llave_remision(t[k]) == fila['llave']):
            partes.append(f'{ETIQUETAS[k]}: {t[k]}')
    fila['comentario'] = ' | '.join(partes + notas)
    return fila


def revisar(archivo):
    """Lee el Excel y clasifica cada renglón (nuevo, ya existe, repetido en el archivo, error) sin guardar nada."""
    hojas, omitidas = _leer_libro(archivo)
    crudos = []
    for titulo, (i, col), filas in hojas:
        mes = _mes_de(titulo)
        for n, f in enumerate(filas[i + 1:], start=i + 2):
            crudos.append({'hoja': titulo, 'renglon': n, 'mes': mes,
                           'v': {campo: (f[j] if j < len(f) else None) for campo, j in col.items()}})
    # año del archivo: el de las fechas de carga que cuadran con el mes de su hoja
    anios = Counter(f.year for c in crudos if c['mes']
                    for f, _ in candidatos_fecha(c['v'].get('fecha_carga')) if f.month == c['mes'])
    anio = anios.most_common(1)[0][0] if anios else timezone.localdate().year
    cat = _Catalogos(crudos)
    filas = [f for f in (_interpretar(c, anio, cat) for c in crudos) if f]

    existentes = {}
    for r in RegistroLogistico.objects.values_list('remision', flat=True):
        existentes.setdefault(llave_remision(r), r)
    grupos = defaultdict(list)
    for f in filas:
        if f['errores']:
            f['estado'] = 'error'
        elif f['llave'] in existentes:
            f['estado'], f['existe_como'] = 'existe', existentes[f['llave']]
        else:
            f['estado'] = 'nuevo'
            grupos[f['llave']].append(f)
    for llave, g in grupos.items():
        if len(g) > 1:
            defecto = next((f for f in g if f['status'] != 'RECHAZADO'), g[0])
            for f in g:
                f['grupo'], f['defecto'] = llave, f is defecto
    return {'filas': filas, 'anio': anio, 'omitidas': omitidas, 'hojas': [h[0] for h in hojas], 'cat': cat}


def seleccion(filas, elegidas=None):
    """Renglones que se dan de alta: los nuevos y, de cada remisión repetida, la elegida
    (elegidas = {llave: key}, '' = ninguna; si no viene, la de por omisión)."""
    elegidas = elegidas or {}
    out = []
    for f in filas:
        if f['estado'] != 'nuevo':
            continue
        if 'grupo' not in f:
            out.append(f)
        elif f['key'] == elegidas.get(f['grupo'], next(x['key'] for x in filas if x.get('grupo') == f['grupo'] and x['defecto'])):
            out.append(f)
    return out


def _catalogo_json(entradas, usadas):
    """Los transportistas/materiales que usan los renglones nuevos (los nuevos primero)."""
    usos = Counter(id(e) for e in usadas if e)
    return sorted(({'nombre': e['nombre'], 'nuevo': e['nuevo'], 'ligar_ternium': e['ligar_ternium'],
                    'excel': sorted(e['excel'])} for e in entradas if usos[id(e)]),
                  key=lambda x: (not x['nuevo'], x['nombre']))


def respuesta(rev):
    filas = rev['filas']
    subir = seleccion(filas)
    resumen = Counter(f['estado'] for f in filas)
    resumen.update({
        'a_subir': len(subir),
        'repetidas': resumen['nuevo'] - len(subir),
        'rechazados': sum(f['status'] == 'RECHAZADO' for f in subir),
        'con_aviso': sum(bool(f['avisos']) for f in subir),
        'corregidas': sum(bool(f['correcciones']) for f in subir),
        'sugeridas': sum(bool(f['sugerida'] or f['entrega_sugerida']) for f in subir),
        'sin_boleta': sum(not f['boleta'] for f in subir),
    })
    iso = lambda d: d.isoformat() if d else None
    return {
        'anio': rev['anio'],
        'hojas': rev['hojas'],
        'hojas_omitidas': rev['omitidas'],
        'resumen': dict(resumen),
        'transportistas': _catalogo_json(rev['cat'].transportistas(), [f['t'] for f in filas if f['estado'] == 'nuevo']),
        'materiales': _catalogo_json(rev['cat'].materiales(), [f['m'] for f in filas if f['estado'] == 'nuevo']),
        'filas': [{
            'key': f['key'], 'hoja': f['hoja'], 'renglon': f['renglon'], 'remision': f['remision'],
            'estado': f['estado'], 'existe_como': f.get('existe_como', ''), 'grupo': f.get('grupo', ''),
            'defecto': f.get('defecto', False), 'fecha': iso(f['fecha']), 'sugerida': iso(f['sugerida']),
            'entrega': iso(f['entrega']), 'entrega_sugerida': iso(f['entrega_sugerida']),
            'transportista': f['t']['nombre'] if f['t'] else '', 'transportista_nuevo': bool(f['t'] and f['t']['nuevo']),
            'material': f['m']['nombre'] if f['m'] else '', 'material_nuevo': bool(f['m'] and f['m']['nuevo']),
            'ton_rem': float(f['ton_rem']) if f['ton_rem'] is not None else None,
            'ton_rec': float(f['ton_rec']) if f['ton_rec'] is not None else None,
            'status': f['status'], 'motivo_rechazo': f['motivo_rechazo'], 'boleta': f['boleta'],
            'chofer': f.get('chofer', ''), 'comentario': f['comentario'],
            'avisos': f['avisos'], 'errores': f['errores'], 'correcciones': f['correcciones'],
        } for f in filas],
    }


# ---------------------------------------------------------------- alta

def _asegurar(entrada, modelo, ternium):
    """Crea el transportista/material nuevo (o reutiliza uno con el mismo nombre) y lo liga a Ternium."""
    if entrada['obj'] is None:
        entrada['obj'] = (modelo.objects.filter(nombre__iexact=entrada['nombre']).first()
                          or modelo.objects.create(nombre=entrada['nombre']))
    if ternium and (entrada['nuevo'] or entrada['ligar_ternium']):
        entrada['obj'].empresas.add(ternium)
    return entrada['obj']


@transaction.atomic
def importar(rev, user, elegidas=None, usar_sugeridas=False):
    filas = seleccion(rev['filas'], elegidas)
    ternium = rev['cat'].ternium
    for e in {id(f['t']): f['t'] for f in filas if f['t']}.values():
        _asegurar(e, LineaTransporte, ternium)
    for e in {id(f['m']): f['m'] for f in filas if f['m']}.values():
        _asegurar(e, Material, ternium)
    quien = (user.get_full_name() or user.username) if user else ''
    hoy = timezone.localdate().strftime('%d/%m/%Y')
    registros = [RegistroLogistico(
        remision=f['remision'],
        fecha_carga=(f['sugerida'] if usar_sugeridas and f['sugerida'] else f['fecha']),
        boleta_bascula=f['boleta'],
        fecha_envio=(f['entrega_sugerida'] if usar_sugeridas and f['entrega_sugerida'] else f['entrega']),
        transportista=f['t']['obj'] if f['t'] else None,
        chofer=f['chofer'] or None,
        tractor=f['tractor'] or None,
        tolva=f['tolva'] or None,
        placas_tractor=f['placas_tractor'] or None,
        placas_tolva=f['placas_tolva'] or None,
        material=f['m']['obj'] if f['m'] else None,
        toneladas_remisionadas=f['ton_rem'],
        toneladas_recibidas=f['ton_rec'],
        numero_permiso_sct=f['permiso'] or None,
        comentario=' | '.join(x for x in (
            f['comentario'], f'Carga masiva desde Excel ({f["hoja"]}, renglón {f["renglon"]}) por {quien} el {hoy}') if x),
        # Sin documentos nunca queda Terminado: el save() del modelo lo dejaría Pendiente.
        status=f['status'],
        carga_masiva=True,  # para Terminado no se le exige la boleta
    ) for f in filas]
    RegistroLogistico.objects.bulk_create(registros, batch_size=200)
    return {
        'creados': len(registros),
        'rechazados': sum(r.status == 'RECHAZADO' for r in registros),
        'fechas_sugeridas': sum(bool(usar_sugeridas and (f['sugerida'] or f['entrega_sugerida'])) for f in filas),
        'transportistas_nuevos': sorted({f['t']['nombre'] for f in filas if f['t'] and f['t']['nuevo']}),
        'materiales_nuevos': sorted({f['m']['nombre'] for f in filas if f['m'] and f['m']['nuevo']}),
    }


# ---------------------------------------------------------------- vistas

def _api(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'detail': 'No autenticado.'}, status=401)
        return vista(request, *args, **kwargs)
    return envoltura


def _revision(request):
    archivo = request.FILES.get('archivo')
    if not archivo:
        raise ErrorCarga('Sube el Excel del reporte de salidas.')
    if not archivo.name.lower().endswith(('.xlsx', '.xlsm')):
        raise ErrorCarga('El archivo debe ser un Excel .xlsx.')
    if archivo.size > MAX_ARCHIVO:
        raise ErrorCarga('El archivo pesa más de 15 MB.')
    return revisar(archivo)


@login_required
def pagina(request):
    return render(request, 'ternium/carga_logistica.html')


@require_http_methods(['POST'])
@_api
def api_revisar(request):
    try:
        return JsonResponse(respuesta(_revision(request)))
    except ErrorCarga as e:
        return JsonResponse({'detail': str(e)}, status=400)


@require_http_methods(['POST'])
@_api
def api_importar(request):
    try:
        elegidas = json.loads(request.POST.get('elegidas') or '{}')
    except json.JSONDecodeError:
        elegidas = None
    if not isinstance(elegidas, dict) or not all(isinstance(v, str) for v in elegidas.values()):
        return JsonResponse({'detail': 'Selección de repetidas no válida.'}, status=400)
    try:
        rev = _revision(request)
        return JsonResponse(importar(rev, request.user, elegidas, request.POST.get('usar_sugeridas') == '1'))
    except ErrorCarga as e:
        return JsonResponse({'detail': str(e)}, status=400)
    except IntegrityError:
        return JsonResponse({'detail': 'Mientras tanto se dio de alta alguna de estas remisiones. '
                                       'Vuelve a revisar el archivo.'}, status=409)
