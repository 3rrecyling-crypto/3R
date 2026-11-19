"""
Resultados (Next: /finanzas/resultados): estado de resultados de dirección por cuenta (cliente) y por mes.

Se captura a mano. Cada celda (cuenta + concepto + mes) es la suma de sus partidas; una partida puede
llevar referencia (folio de factura) y nota, y se puede marcar cancelada: se sigue viendo pero no suma.

Los conceptos pertenecen a una sección y de ahí salen las sumas:
  venta archivos, venta emitida real, ingreso a bancos, costo de material y gastos operativos.
  margen  = venta (archivo | emitida | ingreso a bancos) − costo de material
  utilidad = margen − gastos operativos
Los conceptos en dólares se guardan en dólares y se pasan a pesos con el tipo de cambio del mes
(ResultadoTipoCambio). Si el mes no tiene tipo de cambio, sus dólares NO suman y la pantalla lo avisa.

IVA: en Catálogos el usuario dice si captura los montos con IVA o sin IVA (ResultadoAjustes). Los resultados
siempre se calculan sin IVA: si captura con IVA, a cada renglón que lo lleva (ResultadoConcepto.lleva_iva) se le
quita. Lo capturado se guarda tal cual; cambiar el ajuste solo cambia cómo se calcula.

Permiso: flujo_bancos.acceso_resultados (o superusuario).
"""
import calendar
import json
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import ResultadoAjustes, ResultadoConcepto, ResultadoCuenta, ResultadoPartida, ResultadoTipoCambio

PERMISO = 'flujo_bancos.acceso_resultados'
MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre',
         'Noviembre', 'Diciembre']
SECCIONES = [clave for clave, _ in ResultadoConcepto.SECCIONES]
CENTAVO = Decimal('0.01')
MONTO_MAXIMO = Decimal('9999999999999')  # 15 dígitos con 2 decimales


class ErrorResultados(Exception):
    def __init__(self, detalle, status=400):
        super().__init__(detalle)
        self.detalle, self.status = detalle, status


def puede_usar(user):
    return user.is_authenticated and (user.is_superuser or user.has_perm(PERMISO))


def requiere(vista):
    """Sesión y permiso de Resultados; los errores de validación salen como JSON {detail}."""
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'detail': 'No autenticado.'}, status=401)
        if not puede_usar(request.user):
            return JsonResponse({'detail': 'No tienes el permiso "Resultados".'}, status=403)
        try:
            return vista(request, *args, **kwargs)
        except ErrorResultados as e:
            return JsonResponse({'detail': e.detalle}, status=e.status)
    envoltura.__name__ = vista.__name__
    return envoltura


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de lo que llega
# ─────────────────────────────────────────────────────────────────────────────
def _cuerpo(request):
    try:
        datos = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise ErrorResultados('El cuerpo de la petición no es JSON válido.')
    if not isinstance(datos, dict):
        raise ErrorResultados('Se esperaba un objeto JSON.')
    return datos


def _entero(valor, nombre, minimo, maximo):
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErrorResultados(f'Falta {nombre} o no es un número.')
    if not minimo <= n <= maximo:
        raise ErrorResultados(f'{nombre.capitalize()} fuera de rango ({minimo} a {maximo}).')
    return n


def _anio(valor):
    return _entero(valor, 'el año', 2000, 2100)


def _mes(valor):
    return _entero(valor, 'el mes', 1, 12)


def _monto(valor, nombre='el monto'):
    """Decimal a centavos. Acepta '1,234.50' y '$1 234.50'. Los negativos se permiten (ajustes)."""
    if isinstance(valor, bool) or valor is None:
        raise ErrorResultados(f'Falta {nombre}.')
    texto = str(valor).replace(',', '').replace('$', '').replace(' ', '').strip()
    try:
        n = Decimal(texto)
    except InvalidOperation:
        raise ErrorResultados(f'{nombre.capitalize()} no es un número: "{valor}".')
    if not n.is_finite() or abs(n) > MONTO_MAXIMO:
        raise ErrorResultados(f'{nombre.capitalize()} es demasiado grande.')
    return n.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _texto(valor, largo):
    return ' '.join(str(valor or '').split())[:largo]


def _cuenta(pk):
    try:
        return ResultadoCuenta.objects.get(pk=int(pk))
    except (ResultadoCuenta.DoesNotExist, TypeError, ValueError):
        raise ErrorResultados('La cuenta no existe.', 404)


def _concepto(pk):
    try:
        return ResultadoConcepto.objects.get(pk=int(pk))
    except (ResultadoConcepto.DoesNotExist, TypeError, ValueError):
        raise ErrorResultados('El concepto no existe.', 404)


def _celda_de(datos):
    """(cuenta, concepto, año, mes) de una petición."""
    return _cuenta(datos.get('cuenta')), _concepto(datos.get('concepto')), _anio(datos.get('anio')), _mes(datos.get('mes'))


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo (la pantalla hace las mismas sumas con estos mismos datos)
# ─────────────────────────────────────────────────────────────────────────────
def tipos_de_cambio(anio):
    return {t.mes: t for t in ResultadoTipoCambio.objects.filter(anio=anio)}


def celdas_del_anio(anio):
    """Total de cada celda con captura: lo que suma (sin canceladas), cuántas partidas y cuántas canceladas."""
    return list(
        ResultadoPartida.objects.filter(anio=anio).values('cuenta_id', 'concepto_id', 'mes')
        .annotate(monto=Sum('monto', filter=Q(cancelada=False)), n=Count('id'),
                  canceladas=Count('id', filter=Q(cancelada=True)))
        .order_by('cuenta_id', 'concepto_id', 'mes'))


def divisor_iva(ajustes=None):
    """Entre cuánto se divide un monto capturado con IVA para dejarlo sin IVA (1.16 con tasa de 16%).
    None si los montos se capturan sin IVA."""
    a = ajustes or ResultadoAjustes.actuales()
    return Decimal('1') + a.tasa_iva / Decimal('100') if a.montos_con_iva and a.tasa_iva > 0 else None


def nota_iva(ajustes=None):
    """Cómo leer los montos respecto al IVA, en una frase (Excel y asistente)."""
    a = ajustes or ResultadoAjustes.actuales()
    if divisor_iva(a):
        return f'sin IVA (se capturan con IVA: se les quitó el {a.tasa_iva.normalize():f}%, salvo a los renglones que no llevan IVA)'
    return 'tal como se capturan (sin IVA)'


def en_pesos(monto, concepto, tc, iva=None):
    """Monto del concepto en pesos y sin IVA. Dólares sin tipo de cambio del mes → 0 (la pantalla lo avisa).
    `iva` es el divisor de `divisor_iva()`: con él, al renglón que lleva IVA se le quita."""
    if concepto.moneda == 'USD':
        valor = (monto * tc).quantize(CENTAVO, rounding=ROUND_HALF_UP) if tc else Decimal('0')
    else:
        valor = monto
    if iva and concepto.lleva_iva and valor:
        valor = (valor / iva).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return valor


def derivados(por_concepto, conceptos):
    """Sumas, márgenes y utilidades a partir de {concepto_id: pesos}."""
    s = dict.fromkeys(SECCIONES, Decimal('0'))
    for c in conceptos:
        v = por_concepto.get(c.pk)
        if v:
            s[c.seccion] += -v if c.resta else v
    costo, gastos = s['COSTO_MATERIAL'], s['GASTO']
    r = {
        'venta_archivo': s['VENTA_ARCHIVO'], 'venta_emitida': s['VENTA_EMITIDA'], 'ingreso_bancos': s['INGRESO_BANCOS'],
        'costo_material': costo, 'gastos': gastos,
        'margen_archivo': s['VENTA_ARCHIVO'] - costo, 'margen_real': s['VENTA_EMITIDA'] - costo,
        'margen_flujo': s['INGRESO_BANCOS'] - costo,
    }
    for base in ('archivo', 'real', 'flujo'):
        r[f'utilidad_{base}'] = r[f'margen_{base}'] - gastos
    return r


def matriz(anio):
    """{cuenta_id: {mes: {concepto_id: pesos sin IVA}}} y los meses con dólares sin tipo de cambio."""
    conceptos = {c.pk: c for c in ResultadoConcepto.objects.all()}
    tcs = tipos_de_cambio(anio)
    iva = divisor_iva()
    valores = defaultdict(lambda: defaultdict(dict))
    sin_tc = set()
    for f in celdas_del_anio(anio):
        concepto, monto = conceptos[f['concepto_id']], f['monto'] or Decimal('0')
        tc = tcs[f['mes']].tc if f['mes'] in tcs else None
        if concepto.moneda == 'USD' and monto and not tc:
            sin_tc.add(f['mes'])
        valores[f['cuenta_id']][f['mes']][concepto.pk] = en_pesos(monto, concepto, tc, iva)
    return valores, sorted(sin_tc)


# ─────────────────────────────────────────────────────────────────────────────
# Lo que se manda a la pantalla
# ─────────────────────────────────────────────────────────────────────────────
def _cuenta_dict(c):
    return {'id': c.pk, 'nombre': c.nombre, 'orden': c.orden, 'activa': c.activa}


def _concepto_dict(c):
    return {'id': c.pk, 'seccion': c.seccion, 'nombre': c.nombre, 'moneda': c.moneda, 'resta': c.resta,
            'orden': c.orden, 'activo': c.activo, 'lleva_iva': c.lleva_iva}


def _partida_dict(p):
    return {
        'id': p.pk, 'cuenta': p.cuenta_id, 'concepto': p.concepto_id, 'anio': p.anio, 'mes': p.mes,
        'monto': float(p.monto), 'referencia': p.referencia, 'nota': p.nota, 'cancelada': p.cancelada,
        'usuario': (p.usuario.get_full_name() or p.usuario.username) if p.usuario else '',
        'actualizado': timezone.localtime(p.actualizado).strftime('%d/%m/%Y %H:%M'),
    }


def _celda_dict(cuenta_id, concepto_id, anio, mes):
    """Resumen de una celda después de un cambio (misma forma que las de `datos_del_anio`)."""
    r = ResultadoPartida.objects.filter(cuenta_id=cuenta_id, concepto_id=concepto_id, anio=anio, mes=mes).aggregate(
        monto=Sum('monto', filter=Q(cancelada=False)), n=Count('id'), canceladas=Count('id', filter=Q(cancelada=True)))
    return {'c': cuenta_id, 'k': concepto_id, 'm': mes, 'monto': float(r['monto'] or 0), 'n': r['n'],
            'canceladas': r['canceladas']}


def _ajustes_dict():
    a = ResultadoAjustes.actuales()
    return {'umbral_amarillo': float(a.umbral_amarillo), 'umbral_verde': float(a.umbral_verde),
            'montos_con_iva': a.montos_con_iva, 'tasa_iva': float(a.tasa_iva)}


def datos_del_anio(anio):
    hoy = timezone.localdate()
    anios = set(ResultadoPartida.objects.values_list('anio', flat=True).distinct()) | {hoy.year, anio}
    return {
        'anio': anio, 'anios': sorted(anios, reverse=True), 'hoy': {'anio': hoy.year, 'mes': hoy.month},
        'secciones': [{'clave': clave, 'nombre': nombre} for clave, nombre in ResultadoConcepto.SECCIONES],
        'cuentas': [_cuenta_dict(c) for c in ResultadoCuenta.objects.all()],
        'conceptos': [_concepto_dict(c) for c in ResultadoConcepto.objects.all()],
        'tc': {str(mes): {'tc': float(t.tc), 'origen': t.origen} for mes, t in tipos_de_cambio(anio).items()},
        'celdas': [{'c': f['cuenta_id'], 'k': f['concepto_id'], 'm': f['mes'], 'monto': float(f['monto'] or 0),
                    'n': f['n'], 'canceladas': f['canceladas']} for f in celdas_del_anio(anio)],
        'ajustes': _ajustes_dict(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────
@require_http_methods(['GET'])
@requiere
def api_resultados(request):
    """GET ?anio=2026 → catálogos, tipos de cambio, celdas del año y ajustes del semáforo."""
    anio = _anio(request.GET.get('anio') or timezone.localdate().year)
    return JsonResponse(datos_del_anio(anio))


def _puede_capturarse(cuenta, concepto):
    if not cuenta.activa:
        raise ErrorResultados(f'La cuenta {cuenta.nombre} está desactivada: actívala en Catálogos para capturar.')
    if not concepto.activo:
        raise ErrorResultados(f'El concepto "{concepto.nombre}" está desactivado: actívalo en Catálogos para capturar.')


@require_http_methods(['POST'])
@requiere
def api_celda(request):
    """Captura rápida: deja la celda en ese monto. Con 0 (o vacío) se limpia. Solo si la celda tiene a lo
    más una partida vigente; con desglose (varias) se cambia en el detalle."""
    datos = _cuerpo(request)
    cuenta, concepto, anio, mes = _celda_de(datos)
    valor = datos.get('monto')
    monto = Decimal('0') if valor in (None, '') else _monto(valor)
    with transaction.atomic():
        vigentes = list(ResultadoPartida.objects.select_for_update().filter(
            cuenta=cuenta, concepto=concepto, anio=anio, mes=mes, cancelada=False))
        if len(vigentes) > 1:
            raise ErrorResultados(f'Esta celda tiene {len(vigentes)} partidas: cámbialas en el detalle.', 409)
        if not monto:
            for p in vigentes:
                p.delete()
        elif vigentes:
            p = vigentes[0]
            p.monto, p.usuario = monto, request.user
            p.save(update_fields=['monto', 'usuario', 'actualizado'])
        else:
            _puede_capturarse(cuenta, concepto)
            ResultadoPartida.objects.create(cuenta=cuenta, concepto=concepto, anio=anio, mes=mes, monto=monto,
                                            usuario=request.user)
    return JsonResponse({'celda': _celda_dict(cuenta.pk, concepto.pk, anio, mes)})


@require_http_methods(['GET', 'POST'])
@requiere
def api_partidas(request):
    """GET ?cuenta&concepto&anio&mes → partidas de la celda. POST → agrega una partida."""
    if request.method == 'GET':
        cuenta, concepto, anio, mes = _celda_de(request.GET)
        partidas = ResultadoPartida.objects.filter(cuenta=cuenta, concepto=concepto, anio=anio, mes=mes).select_related('usuario')
        return JsonResponse({'partidas': [_partida_dict(p) for p in partidas]})
    datos = _cuerpo(request)
    cuenta, concepto, anio, mes = _celda_de(datos)
    _puede_capturarse(cuenta, concepto)
    monto = _monto(datos.get('monto'))
    if not monto:
        raise ErrorResultados('El monto no puede ser cero.')
    p = ResultadoPartida.objects.create(
        cuenta=cuenta, concepto=concepto, anio=anio, mes=mes, monto=monto, usuario=request.user,
        referencia=_texto(datos.get('referencia'), 80), nota=_texto(datos.get('nota'), 250))
    return JsonResponse({'partida': _partida_dict(p), 'celda': _celda_dict(cuenta.pk, concepto.pk, anio, mes)}, status=201)


@require_http_methods(['PATCH', 'PUT', 'DELETE'])
@requiere
def api_partida(request, pk):
    """Cambia monto, referencia, nota o cancelada de una partida; o la elimina."""
    try:
        p = ResultadoPartida.objects.select_related('usuario').get(pk=pk)
    except ResultadoPartida.DoesNotExist:
        raise ErrorResultados('La partida ya no existe.', 404)
    celda = (p.cuenta_id, p.concepto_id, p.anio, p.mes)
    if request.method == 'DELETE':
        p.delete()
        return JsonResponse({'celda': _celda_dict(*celda)})
    datos = _cuerpo(request)
    if 'monto' in datos:
        p.monto = _monto(datos['monto'])
        if not p.monto:
            raise ErrorResultados('El monto no puede ser cero: elimina la partida o márcala cancelada.')
    if 'referencia' in datos:
        p.referencia = _texto(datos['referencia'], 80)
    if 'nota' in datos:
        p.nota = _texto(datos['nota'], 250)
    if 'cancelada' in datos:
        p.cancelada = bool(datos['cancelada'])
    p.usuario = request.user
    p.save()
    return JsonResponse({'partida': _partida_dict(p), 'celda': _celda_dict(*celda)})


# ── Tipo de cambio ───────────────────────────────────────────────────────────
@require_http_methods(['POST'])
@requiere
def api_tc(request):
    """POST {anio, mes, tc, origen?} → guarda el tipo de cambio del mes. Con tc vacío se quita."""
    datos = _cuerpo(request)
    anio, mes = _anio(datos.get('anio')), _mes(datos.get('mes'))
    if datos.get('tc') in (None, ''):
        ResultadoTipoCambio.objects.filter(anio=anio, mes=mes).delete()
        return JsonResponse({'mes': mes, 'tc': None})
    try:
        tc = Decimal(str(datos['tc']).replace(',', '').replace('$', '').strip()).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ErrorResultados('El tipo de cambio no es un número.')
    if not Decimal('1') <= tc <= Decimal('200'):
        raise ErrorResultados('El tipo de cambio debe estar entre 1 y 200 pesos por dólar.')
    origen = 'BANXICO' if datos.get('origen') == 'BANXICO' else 'MANUAL'
    ResultadoTipoCambio.objects.update_or_create(anio=anio, mes=mes, defaults={'tc': tc, 'origen': origen})
    return JsonResponse({'mes': mes, 'tc': {'tc': float(tc), 'origen': origen}})


def tc_banxico(anio, mes):
    """Tipo de cambio FIX de Banxico del mes: el del último día publicado (cierre) y el promedio.
    Regresa None si no hay token, si Banxico no responde o si el mes todavía no tiene datos."""
    token = getattr(settings, 'BANXICO_API_TOKEN', None)
    if not token:
        return None
    fin = date(anio, mes, calendar.monthrange(anio, mes)[1])
    url = f'https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43718/datos/{anio}-{mes:02d}-01/{fin.isoformat()}'
    try:
        r = requests.get(url, headers={'Bmx-Token': token, 'Accept': 'application/json'}, timeout=6)
        r.raise_for_status()
        datos = r.json()['bmx']['series'][0].get('datos') or []
    except Exception:  # sin red, token vencido o respuesta rara: no hay sugerencia
        return None
    valores = []
    for d in datos:
        try:
            valores.append((d['fecha'], Decimal(str(d['dato']).replace(',', ''))))
        except (InvalidOperation, KeyError):
            continue  # días sin dato ("N/E")
    if not valores:
        return None
    promedio = (sum(v for _, v in valores) / len(valores)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return {'cierre': float(valores[-1][1]), 'fecha_cierre': valores[-1][0], 'promedio': float(promedio), 'dias': len(valores)}


@require_http_methods(['GET'])
@requiere
def api_tc_sugerido(request):
    """GET ?anio&mes → tipo de cambio de Banxico (cierre y promedio del mes) para proponerlo."""
    anio, mes = _anio(request.GET.get('anio')), _mes(request.GET.get('mes'))
    sugerido = tc_banxico(anio, mes)
    if not sugerido:
        return JsonResponse({'disponible': False, 'detail': 'No se pudo consultar Banxico para ese mes: captura el tipo de cambio a mano.'})
    return JsonResponse({'disponible': True, **sugerido})


# ── Catálogos ────────────────────────────────────────────────────────────────
def _nombre(datos, largo):
    nombre = _texto(datos.get('nombre'), largo)
    if not nombre:
        raise ErrorResultados('Escribe el nombre.')
    return nombre


@require_http_methods(['POST'])
@requiere
def api_cuentas(request):
    """POST {nombre} → nueva cuenta al final. POST {orden: [ids]} → reordena."""
    datos = _cuerpo(request)
    if 'orden' in datos:
        _reordenar(ResultadoCuenta, datos['orden'])
        return JsonResponse({'cuentas': [_cuenta_dict(c) for c in ResultadoCuenta.objects.all()]})
    nombre = _nombre(datos, 80).upper()
    if ResultadoCuenta.objects.filter(nombre__iexact=nombre).exists():
        raise ErrorResultados(f'Ya existe la cuenta {nombre}.', 409)
    ultimo = ResultadoCuenta.objects.aggregate(m=Max('orden'))['m'] or 0
    cuenta = ResultadoCuenta.objects.create(nombre=nombre, orden=ultimo + 1)
    return JsonResponse({'cuenta': _cuenta_dict(cuenta)}, status=201)


@require_http_methods(['PATCH', 'PUT', 'DELETE'])
@requiere
def api_cuenta(request, pk):
    cuenta = _cuenta(pk)
    if request.method == 'DELETE':
        if cuenta.partidas.exists():
            raise ErrorResultados(f'{cuenta.nombre} tiene capturas: no se puede eliminar. Desactívala para que deje de salir.', 409)
        cuenta.delete()
        return JsonResponse({'eliminada': True})
    datos = _cuerpo(request)
    if 'nombre' in datos:
        nombre = _nombre(datos, 80).upper()
        if ResultadoCuenta.objects.filter(nombre__iexact=nombre).exclude(pk=cuenta.pk).exists():
            raise ErrorResultados(f'Ya existe la cuenta {nombre}.', 409)
        cuenta.nombre = nombre
    if 'activa' in datos:
        cuenta.activa = bool(datos['activa'])
    cuenta.save()
    return JsonResponse({'cuenta': _cuenta_dict(cuenta)})


@require_http_methods(['POST'])
@requiere
def api_conceptos(request):
    """POST {seccion, nombre, moneda?, resta?, lleva_iva?} → nuevo concepto al final de su sección.
    POST {orden: [ids]} → reordena."""
    datos = _cuerpo(request)
    if 'orden' in datos:
        _reordenar(ResultadoConcepto, datos['orden'])
        return JsonResponse({'conceptos': [_concepto_dict(c) for c in ResultadoConcepto.objects.all()]})
    seccion = datos.get('seccion')
    if seccion not in SECCIONES:
        raise ErrorResultados('Elige la sección del concepto.')
    nombre = _nombre(datos, 120)
    if ResultadoConcepto.objects.filter(seccion=seccion, nombre__iexact=nombre).exists():
        raise ErrorResultados(f'Ya existe "{nombre}" en esa sección.', 409)
    ultimo = ResultadoConcepto.objects.aggregate(m=Max('orden'))['m'] or 0
    concepto = ResultadoConcepto.objects.create(
        seccion=seccion, nombre=nombre, moneda='USD' if datos.get('moneda') == 'USD' else 'MXN',
        resta=bool(datos.get('resta')), lleva_iva=bool(datos.get('lleva_iva', True)), orden=ultimo + 1)
    return JsonResponse({'concepto': _concepto_dict(concepto)}, status=201)


@require_http_methods(['PATCH', 'PUT', 'DELETE'])
@requiere
def api_concepto(request, pk):
    concepto = _concepto(pk)
    con_capturas = concepto.partidas.exists()
    if request.method == 'DELETE':
        if con_capturas:
            raise ErrorResultados(f'"{concepto.nombre}" tiene capturas: no se puede eliminar. Desactívalo para que deje de salir.', 409)
        concepto.delete()
        return JsonResponse({'eliminado': True})
    datos = _cuerpo(request)
    if 'nombre' in datos:
        nombre = _nombre(datos, 120)
        if ResultadoConcepto.objects.filter(seccion=concepto.seccion, nombre__iexact=nombre).exclude(pk=concepto.pk).exists():
            raise ErrorResultados(f'Ya existe "{nombre}" en esa sección.', 409)
        concepto.nombre = nombre
    if 'moneda' in datos and datos['moneda'] in ('MXN', 'USD') and datos['moneda'] != concepto.moneda:
        if con_capturas:  # los montos ya capturados cambiarían de significado
            raise ErrorResultados(f'"{concepto.nombre}" ya tiene capturas en {concepto.moneda}: no se le puede cambiar la moneda. Crea otro concepto.', 409)
        concepto.moneda = datos['moneda']
    if 'resta' in datos:
        concepto.resta = bool(datos['resta'])
    if 'activo' in datos:
        concepto.activo = bool(datos['activo'])
    if 'lleva_iva' in datos:
        concepto.lleva_iva = bool(datos['lleva_iva'])
    try:
        concepto.save()
    except IntegrityError:
        raise ErrorResultados('Ya existe un concepto con ese nombre en la sección.', 409)
    return JsonResponse({'concepto': _concepto_dict(concepto)})


def _reordenar(modelo, ids):
    """Deja `orden` según la lista de ids (los que no vengan quedan al final, en su orden)."""
    if not isinstance(ids, list):
        raise ErrorResultados('El orden debe ser una lista de ids.')
    existentes = {o.pk: o for o in modelo.objects.all()}
    pedidos = []
    for i in ids:
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if i in existentes and i not in pedidos:
            pedidos.append(i)
    resto = [pk for pk in existentes if pk not in pedidos]
    with transaction.atomic():
        for posicion, pk in enumerate(pedidos + resto, start=1):
            if existentes[pk].orden != posicion:
                modelo.objects.filter(pk=pk).update(orden=posicion)


@require_http_methods(['POST'])
@requiere
def api_ajustes(request):
    """POST con lo que se quiera cambiar:
    {umbral_amarillo, umbral_verde} → cortes del semáforo (% de utilidad sobre la venta);
    {montos_con_iva} → si los montos se capturan con IVA (los resultados se calculan sin IVA);
    {tasa_iva} → tasa de IVA en %."""
    datos = _cuerpo(request)
    a = ResultadoAjustes.actuales()
    if 'umbral_amarillo' in datos or 'umbral_verde' in datos:
        try:
            amarillo = Decimal(str(datos.get('umbral_amarillo'))).quantize(CENTAVO)
            verde = Decimal(str(datos.get('umbral_verde'))).quantize(CENTAVO)
        except InvalidOperation:
            raise ErrorResultados('Los cortes del semáforo deben ser números.')
        if not (Decimal('-100') <= amarillo < verde <= Decimal('100')):
            raise ErrorResultados('El corte amarillo debe ser menor que el verde, y los dos entre -100 y 100.')
        a.umbral_amarillo, a.umbral_verde = amarillo, verde
    if 'tasa_iva' in datos:
        try:
            tasa = Decimal(str(datos.get('tasa_iva')).replace('%', '').strip()).quantize(CENTAVO)
        except InvalidOperation:
            raise ErrorResultados('La tasa de IVA debe ser un número.')
        if not Decimal('0') < tasa <= Decimal('50'):
            raise ErrorResultados('La tasa de IVA debe ser mayor que 0 y de 50% como máximo.')
        a.tasa_iva = tasa
    if 'montos_con_iva' in datos:
        a.montos_con_iva = bool(datos['montos_con_iva'])
    a.save()
    return JsonResponse({'ajustes': _ajustes_dict()})


# ─────────────────────────────────────────────────────────────────────────────
# Excel (mismo acomodo que el "Vista Resultados" de dirección)
# ─────────────────────────────────────────────────────────────────────────────
FILAS_DERIVADAS = [  # (después de la sección, etiqueta, sub, clave)
    ('COSTO_MATERIAL', 'MARGEN DE OPERACIÓN', 'ARCHIVO', 'margen_archivo'),
    ('COSTO_MATERIAL', 'MARGEN DE OPERACIÓN', 'REAL', 'margen_real'),
    ('COSTO_MATERIAL', 'MARGEN DE OPERACIÓN', 'FLUJO', 'margen_flujo'),
    ('GASTO', 'UTILIDAD REAL', 'ARCHIVO', 'utilidad_archivo'),
    ('GASTO', 'UTILIDAD REAL', 'REAL', 'utilidad_real'),
    ('GASTO', 'UTILIDAD REAL', 'FLUJO', 'utilidad_flujo'),
]
SUMA_DE = {'VENTA_ARCHIVO': 'venta_archivo', 'VENTA_EMITIDA': 'venta_emitida', 'INGRESO_BANCOS': 'ingreso_bancos',
           'COSTO_MATERIAL': 'costo_material', 'GASTO': 'gastos'}
COLOR_SECCION = {'VENTA_ARCHIVO': 'FDE9C9', 'VENTA_EMITIDA': 'FDE9C9', 'INGRESO_BANCOS': 'FFF6BF',
                 'COSTO_MATERIAL': 'D9EFC2', 'GASTO': 'D6E4F2'}


def _hoja(ws, titulo, subtitulo, columnas, conceptos):
    """Escribe una tabla de resultados. `columnas`: [(encabezado, {concepto_id: pesos})]; se agrega TOTAL."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    total = defaultdict(Decimal)
    for _, valores in columnas:
        for k, v in valores.items():
            total[k] += v
    columnas = columnas + [('TOTAL', dict(total))]
    calculos = [derivados(valores, conceptos) for _, valores in columnas]

    linea = Side(style='thin', color='D9D9D9')
    borde = Border(left=linea, right=linea, top=linea, bottom=linea)
    ws['A1'], ws['A2'] = titulo, subtitulo
    ws['A1'].font, ws['A2'].font = Font(bold=True, size=14), Font(color='666666')
    fila = 4
    for i, (encabezado, _) in enumerate(columnas):
        c = ws.cell(fila, 3 + i, encabezado)
        c.font, c.fill, c.border = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='1F3A5F'), borde
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[fila].height = 30

    def renglon(etiqueta, sub, valores, negrita=False, color=None):
        nonlocal fila
        fila += 1
        for col, texto in ((1, etiqueta), (2, sub)):
            c = ws.cell(fila, col, texto)
            c.font, c.border = Font(bold=negrita), borde
            if color:
                c.fill = PatternFill('solid', fgColor=color)
        for i, v in enumerate(valores):
            c = ws.cell(fila, 3 + i, float(v or 0))
            c.number_format, c.font, c.border = '#,##0.00;[Red]-#,##0.00', Font(bold=negrita), borde
            if color:
                c.fill = PatternFill('solid', fgColor=color)

    for clave, nombre in ResultadoConcepto.SECCIONES:
        renglon(nombre.upper(), '', [c[SUMA_DE[clave]] for c in calculos], negrita=True, color=COLOR_SECCION[clave])
        for concepto in conceptos:
            if concepto.seccion != clave:
                continue
            valores = [v.get(concepto.pk, Decimal('0')) for _, v in columnas]
            if not concepto.activo and not any(valores):
                continue
            etiqueta = concepto.nombre + (' (resta)' if concepto.resta else '')
            renglon('' if clave != 'GASTO' else etiqueta, etiqueta if clave != 'GASTO' else '', valores)
        for despues, etiqueta, sub, llave in FILAS_DERIVADAS:
            if despues == clave:
                renglon(etiqueta, sub, [c[llave] for c in calculos], negrita=True, color='F3D9F2')

    # % de utilidad real sobre la venta emitida
    fila += 1
    ws.cell(fila, 1, '% UTILIDAD REAL').font = Font(bold=True)
    ws.cell(fila, 2, 'sobre venta emitida')
    for i, c in enumerate(calculos):
        celda = ws.cell(fila, 3 + i, float(c['utilidad_real'] / c['venta_emitida']) if c['venta_emitida'] else None)
        celda.number_format, celda.font, celda.border = '0.0%', Font(bold=True), borde

    ws.column_dimensions['A'].width, ws.column_dimensions['B'].width = 44, 30
    for i in range(len(columnas)):
        ws.column_dimensions[get_column_letter(3 + i)].width = 17
    ws.freeze_panes = 'C5'


def _nombre_hoja(texto, usados):
    limpio = ''.join(ch for ch in texto if ch not in '[]:*?/\\')[:28].strip() or 'Hoja'
    nombre, n = limpio, 2
    while nombre.upper() in usados:
        nombre, n = f'{limpio[:25]} {n}', n + 1
    usados.add(nombre.upper())
    return nombre


def construir_excel(anio, mes):
    """Libro con la vista del mes (cuentas en columnas), el año completo y una hoja por cuenta."""
    from openpyxl import Workbook

    conceptos = list(ResultadoConcepto.objects.all())
    valores, sin_tc = matriz(anio)
    cuentas = [c for c in ResultadoCuenta.objects.all() if c.activa or c.pk in valores]
    tcs = tipos_de_cambio(anio)
    aviso = ('  ·  OJO: hay dólares sin tipo de cambio en ' + ', '.join(MESES[m - 1] for m in sin_tc)
             + ' (no están sumando)') if sin_tc else ''

    def suma_meses(cuenta_ids, meses):
        total = defaultdict(Decimal)
        for cid in cuenta_ids:
            for m in meses:
                for k, v in valores.get(cid, {}).get(m, {}).items():
                    total[k] += v
        return dict(total)

    montos = f'Montos en pesos, {nota_iva()}'
    wb, usados = Workbook(), set()
    ws = wb.active
    ws.title = _nombre_hoja(f'{MESES[mes - 1]} {anio}', usados)
    tc_mes = f'  ·  Tipo de cambio: {tcs[mes].tc:.4f}' if mes in tcs else ''
    _hoja(ws, f'VISTA DE RESULTADOS X MES · {MESES[mes - 1].upper()} {anio}', f'{montos}{tc_mes}{aviso}',
          [(c.nombre, suma_meses([c.pk], [mes])) for c in cuentas], conceptos)

    todos = [c.pk for c in cuentas]
    _hoja(wb.create_sheet(_nombre_hoja(f'Año {anio}', usados)), f'RESULTADOS {anio} · TODAS LAS CUENTAS',
          f'{montos}{aviso}', [(MESES[m - 1].upper(), suma_meses(todos, [m])) for m in range(1, 13)], conceptos)
    for c in cuentas:
        _hoja(wb.create_sheet(_nombre_hoja(c.nombre, usados)), f'VISTA DE RESULTADOS X CLIENTE · {c.nombre} · {anio}',
              f'{montos}{aviso}', [(MESES[m - 1].upper(), suma_meses([c.pk], [m])) for m in range(1, 13)], conceptos)
    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()


@require_http_methods(['GET'])
@requiere
def api_excel(request):
    """GET ?anio&mes → Excel de Resultados."""
    hoy = timezone.localdate()
    anio = _anio(request.GET.get('anio') or hoy.year)
    mes = _mes(request.GET.get('mes') or hoy.month)
    respuesta = HttpResponse(construir_excel(anio, mes),
                             content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    respuesta['Content-Disposition'] = f'attachment; filename="Resultados {anio}-{mes:02d}.xlsx"'
    respuesta['Access-Control-Expose-Headers'] = 'Content-Disposition'
    return respuesta
