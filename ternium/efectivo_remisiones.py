"""
Efectivo: pestaña de "Asignación de factura" (Next: /asignacion-factura) para las operaciones que se
cobraron en efectivo y no llevan factura.

Cada operación (EfectivoRemision) lleva su número de captura consecutivo (3R-E-001), la unidad de
negocio, la fecha, notas y las remisiones que cubre (el cliente no se captura: se toma de las
remisiones). No hay XML, número de factura ni impuestos. Las remisiones se eligen igual que los folios de una factura: solo las que no tienen
factura ni efectivo, de una o varias unidades de negocio del usuario.

Monto: se captura el precio por kg de cada material de cada remisión y el sistema lo multiplica por
sus kg descargados (peso de descarga). La suma es el monto calculado; el usuario puede corregir el
monto a mano y entonces queda marcado como ajustado. Cada material queda en una EfectivoLinea con los
kg que tenía al guardar; se rehacen en cada guardado, así que volver a guardar toma el peso actual.
Si la moneda es USD se pide el tipo de cambio (pesos por dólar) y se muestra el equivalente en pesos.

Una remisión en efectivo queda con Remision.efectivo_registro (por UPDATE directo, como los folios de
una factura, para no recalcular el estatus ni tocar remisiones auditadas): deja de contar como "sin
factura" y no se puede ligar a una factura. Quitarla de la operación o borrar la operación la deja otra
vez sin factura. Todo cambio queda en la bitácora (HistorialEfectivoRemision).

Permiso: el mismo de Asignación de factura (ternium.acceso_asignacion_factura).
"""
import json
import re
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import asignacion_factura as af
from .models import DetalleRemision, EfectivoLinea, EfectivoRemision, HistorialEfectivoRemision, Remision

POR_PAGINA = 25


class ErrorEfectivo(Exception):
    pass


def _efectivos(user):
    return (EfectivoRemision.objects.filter(empresa__in=af._empresas(user)).select_related('empresa', 'creado_por')
            .prefetch_related('lineas'))


def _orden_folio(remision):
    return (af._numero_folio(remision) or 0, remision)


def _dict(e):
    lista = list(e.remisiones.exclude(status='CANCELADO')
                 .select_related('cliente', 'destino', 'empresa', 'efectivo_registro').order_by('remision'))
    kg = af._kg_por_remision([r.pk for r in lista])
    # Materiales de cada remisión con sus kg descargados de hoy y el precio que se guardó
    mats = af.materiales_por_remision([r.pk for r in lista])
    guardadas = {li.detalle_id: li for li in e.lineas.all() if li.detalle_id}
    numero = lambda n: float(n) if n is not None else None  # noqa: E731
    for filas in mats.values():
        for m in filas:
            li = guardadas.get(m['detalle'])
            m['precio'] = numero(li.precio) if li else None
            m['importe'] = numero(li.importe) if li else None
            m['kg_guardado'] = float(li.kg) if li else None  # si difiere de kg, el peso cambió después de guardar
    folios = sorted((af._folio_dict(r, kg, mats) for r in lista), key=lambda x: _orden_folio(x['remision']))
    return {
        'id': e.pk, 'captura': e.numero_captura, 'empresa': {'id': e.empresa_id, 'nombre': e.empresa.nombre},
        'fecha': e.fecha.isoformat(), 'cliente': e.cliente,
        'monto': numero(e.monto), 'monto_calculado': numero(e.monto_calculado), 'monto_ajustado': e.monto_ajustado,
        'precios': _precios_resumen(e), 'moneda': e.moneda, 'notas': e.notas,
        # En USD: pesos por dólar y lo que equivale el monto en pesos
        'tipo_cambio': float(e.tipo_cambio), 'monto_mxn': numero(_en_pesos(e)),
        'creado_por': af._nombre(e.creado_por),
        'creado_en': timezone.localtime(e.creado_en).strftime('%d/%m/%Y %H:%M'),
        'folios': folios, 'num_folios': len(folios),
        'carga_kg': round(sum(x['carga_kg'] for x in folios), 3),
        'descarga_kg': round(sum(x['descarga_kg'] for x in folios), 3),
        'historial': [{
            'fecha': timezone.localtime(h.fecha).strftime('%d/%m/%Y %H:%M'), 'usuario': af._nombre(h.usuario) or '—',
            'accion': h.get_accion_display(), 'cambios': h.cambios or [],
        } for h in HistorialEfectivoRemision.objects.filter(efectivo=e).select_related('usuario')],
    }


def _precios_resumen(e):
    """Precios de la operación por material: [{material, precio, kg, importe}], un renglón por cada precio
    distinto de cada material (lo normal es uno por material)."""
    grupos = {}
    for li in e.lineas.all():
        g = grupos.setdefault((li.material_nombre or 'SIN MATERIAL', li.precio), {'kg': Decimal(0), 'importe': Decimal(0)})
        g['kg'] += li.kg or 0
        g['importe'] += li.importe or 0
    return [{'material': material, 'precio': float(precio) if precio is not None else None, 'kg': float(g['kg']),
             'importe': float(g['importe']) if precio is not None else None}
            for (material, precio), g in sorted(grupos.items(), key=lambda x: (x[0][0], x[0][1] or 0))]


def _precio(valor, material):
    """Precio por kg de un material: opcional (None si no se escribe); si se escribe, mayor a cero."""
    if valor in (None, ''):
        return None
    try:
        n = Decimal(str(valor).replace(',', '').replace('$', '').strip()).quantize(Decimal('0.0001'))
    except (InvalidOperation, ValueError):
        raise ErrorEfectivo(f'El precio de {material}: escribe una cantidad (o déjalo vacío).')
    if n <= 0:
        raise ErrorEfectivo(f'El precio de {material} debe ser mayor a cero (o déjalo vacío).')
    if n >= Decimal('1000000'):
        raise ErrorEfectivo(f'El precio de {material} es demasiado grande.')
    return n


def _en_pesos(e):
    """El monto en pesos: el mismo en MXN; en USD, monto × tipo de cambio. None si no hay monto."""
    if e.monto is None:
        return None
    return (e.monto * (e.tipo_cambio if e.moneda == 'USD' else 1)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _tipo_cambio(valor):
    """Pesos por dólar: obligatorio cuando la moneda es USD."""
    try:
        n = Decimal(str(valor).replace(',', '').replace('$', '').strip()).quantize(Decimal('0.0001'))
    except (InvalidOperation, ValueError):
        raise ErrorEfectivo('La moneda es USD: escribe el tipo de cambio (pesos por dólar).')
    if n <= 0 or n >= Decimal('10000'):
        raise ErrorEfectivo('El tipo de cambio debe ser mayor a cero (pesos por dólar, ej. 18.50).')
    return n


def _monto(valor):
    """Monto cobrado en efectivo escrito a mano: opcional (None si no se escribe); si se escribe, mayor a cero."""
    if valor in (None, ''):
        return None
    try:
        n = Decimal(str(valor).replace(',', '').replace('$', '').strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ErrorEfectivo('El monto: escribe una cantidad (o déjalo vacío).')
    if n <= 0:
        raise ErrorEfectivo('El monto debe ser mayor a cero (o déjalo vacío).')
    if n >= Decimal('1000000000000'):
        raise ErrorEfectivo('El monto es demasiado grande.')
    return n


def _txt_precio(n):
    """$2.50, $2.375: el precio por kg con dos decimales o los que tenga (hasta cuatro)."""
    texto = f'{n:,.4f}'
    while texto.endswith('0') and len(texto.split('.')[1]) > 2:
        texto = texto[:-1]
    return f'${texto}'


def _foto(e):
    """Lo que se compara para la bitácora: {campo: texto}."""
    return {
        'Fecha': e.fecha.strftime('%d/%m/%Y') if e.fecha else '',
        'Unidad de negocio': e.empresa.nombre if e.empresa_id else '', 'Cliente': e.cliente,
        'Monto': (f'${float(e.monto):,.2f} {e.moneda}' + (' (corregido a mano)' if e.monto_ajustado else '')
                  if e.monto is not None else ''),
        'Monto calculado': f'${float(e.monto_calculado):,.2f} {e.moneda}' if e.monto_calculado is not None else '',
        'Tipo de cambio': f'${float(e.tipo_cambio):,.4f}' if e.moneda == 'USD' else '',
        'Precios por kg': '; '.join(f'{p["material"]} {_txt_precio(p["precio"])}'
                                    for p in _precios_resumen(e) if p['precio'] is not None) if e.pk else '',
        'Notas': e.notas,
    }


def _alta_con_captura(registro):
    """Guarda la operación nueva con el siguiente número de captura (3R-E-001, 3R-E-002…). Si otra alta
    tomó ese número al mismo tiempo, toma el siguiente."""
    for intento in range(5):
        registro.captura = (EfectivoRemision.objects.aggregate(m=Max('captura'))['m'] or 0) + 1
        try:
            with transaction.atomic():
                registro.save()
            return
        except IntegrityError:
            if intento == 4 or not EfectivoRemision.objects.filter(captura=registro.captura).exists():
                raise


def _clientes_de(folios):
    """El cliente de la operación no se captura: son los clientes de sus remisiones (el cliente o, si no
    tiene, el destino), del que más remisiones tiene al que menos: 'NUNCIO' o 'NUNCIO, DEACERO'."""
    nombres = Counter((r.cliente.nombre if r.cliente_id else '') or (r.destino.nombre if r.destino_id else '')
                      for r in folios)
    nombres.pop('', None)
    return af._mayusculas(', '.join(n for n, _ in sorted(nombres.items(), key=lambda x: (-x[1], x[0].upper()))), 200)


def _guardar(user, body, registro=None):
    """Crea o actualiza la operación en efectivo y deja en ella exactamente las remisiones de body['remisiones']."""
    empresa = af._empresas(user).filter(pk=body.get('empresa') if str(body.get('empresa', '')).isdigit() else None).first()
    if not empresa:
        raise ErrorEfectivo('Elige la unidad de negocio.')
    fecha = af._fecha(body.get('fecha'))
    if not fecha:
        raise ErrorEfectivo('Escribe la fecha de la operación.')
    moneda = body.get('moneda') if body.get('moneda') in dict(EfectivoRemision.MONEDAS) else 'MXN'
    tipo_cambio = _tipo_cambio(body.get('tipo_cambio')) if moneda == 'USD' else Decimal(1)
    precios = body.get('precios') if isinstance(body.get('precios'), dict) else {}  # {id del detalle: precio por kg}
    # El monto solo se toma de lo escrito si el usuario pidió corregirlo a mano
    a_mano = _monto(body.get('monto')) if body.get('monto_manual') else None

    ids = {int(i) for i in (body.get('remisiones') or []) if str(i).isdigit()}
    if not ids:
        raise ErrorEfectivo('Selecciona al menos una remisión.' if registro is None else
                            'Deja al menos una remisión (para quitarlas todas, elimina la operación).')
    folios = {r.pk: r for r in af._base(user).filter(pk__in=ids)}
    faltan = ids - set(folios)
    if faltan:
        raise ErrorEfectivo(f'{len(faltan)} remisión(es) no existen, están canceladas o no son de tus unidades de negocio.')
    con_factura = [f'{r.remision} ({r.factura_nombre})' for r in folios.values() if r.factura_nombre]
    if con_factura:
        raise ErrorEfectivo('Estas remisiones ya tienen factura y no pueden ir en efectivo: '
                            + ', '.join(con_factura[:10]) + '.')
    en_otro = [f'{r.remision} ({r.efectivo_registro.numero_captura})' for r in folios.values()
               if r.efectivo_registro_id and (registro is None or r.efectivo_registro_id != registro.pk)]
    if en_otro:
        raise ErrorEfectivo('Estas remisiones ya están en otra operación en efectivo: ' + ', '.join(en_otro[:10]) + '.')

    ahora = timezone.now()
    nueva = registro is None
    antes = None if nueva else _foto(registro)
    folios_antes = set() if nueva else set(
        Remision.objects.filter(efectivo_registro=registro).values_list('remision', flat=True))
    with transaction.atomic():
        if nueva:
            registro = EfectivoRemision(creado_por=user)
        registro.empresa, registro.fecha, registro.moneda, registro.tipo_cambio = empresa, fecha, moneda, tipo_cambio
        registro.cliente = _clientes_de(folios.values())
        registro.notas = ' '.join(str(body.get('notas') or '').split()).upper()[:2000]
        if nueva:
            _alta_con_captura(registro)
        else:
            registro.save()
        # Las que se quitaron quedan otra vez sin factura
        Remision.objects.filter(efectivo_registro=registro).exclude(pk__in=ids).update(
            efectivo_registro=None, factura_asignada_por=None, factura_asignada_en=None, actualizado_en=ahora)
        # Se agregan solo las que siguen sin factura ni efectivo (el filtro va en el UPDATE); las que ya
        # eran de esta operación conservan quién y cuándo las puso.
        Remision.objects.filter(pk__in=ids).filter(af._libre_q()).update(
            efectivo_registro=registro, factura_asignada_por=user, factura_asignada_en=ahora, actualizado_en=ahora)
        if Remision.objects.filter(pk__in=ids, efectivo_registro=registro).count() != len(ids):
            raise ErrorEfectivo('Alguien le asignó factura o efectivo a una de las remisiones mientras tanto. '
                                'Vuelve a intentarlo.')
        # Precio por material: una línea por cada material de cada remisión, con sus kg descargados de hoy.
        # Importe = precio por kg × kg descargados. Se rehacen todas en cada guardado.
        lineas = []
        for d in DetalleRemision.objects.filter(remision_id__in=ids).select_related('material').order_by('remision_id', 'pk'):
            nombre = d.material.nombre if d.material_id else 'SIN MATERIAL'
            precio = _precio(precios.get(str(d.pk)), f'{nombre} ({folios[d.remision_id].remision})')
            kilos = d.peso_dlv or Decimal(0)
            lineas.append(EfectivoLinea(
                efectivo=registro, remision_id=d.remision_id, detalle=d, material_id=d.material_id,
                material_nombre=nombre[:200], kg=kilos, precio=precio,
                importe=(precio * kilos).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if precio is not None else None))
        EfectivoLinea.objects.filter(efectivo=registro).delete()
        EfectivoLinea.objects.bulk_create(lineas)
        # La operación venía con sus líneas precargadas: ya no son esas
        getattr(registro, '_prefetched_objects_cache', {}).pop('lineas', None)
        con_precio = [li.importe for li in lineas if li.importe is not None]
        registro.monto_calculado = sum(con_precio, Decimal(0)) if con_precio else None
        # El monto es el calculado, salvo que lo hayan corregido a mano con otra cantidad
        registro.monto = a_mano if a_mano is not None else registro.monto_calculado
        registro.monto_ajustado = a_mano is not None and a_mano != registro.monto_calculado
        registro.save(update_fields=['monto', 'monto_calculado', 'monto_ajustado'])
        # Bitácora: quién, cuándo y qué cambió
        folios_despues = {folios[i].remision for i in ids}
        if nueva:
            cambios = [f'Captura {registro.numero_captura} · Alta en efectivo'
                       + (f' · Monto ${registro.monto:,.2f} {registro.moneda}' if registro.monto is not None else ' · sin monto')
                       + (' (corregido a mano)' if registro.monto_ajustado else '')
                       + (f' · Tipo de cambio ${registro.tipo_cambio:,.4f}' if registro.moneda == 'USD' else ''),
                       'Remisiones: ' + ', '.join(sorted(folios_despues, key=_orden_folio))]
            precios_txt = _foto(registro)['Precios por kg']
            if precios_txt:
                cambios.append('Precios por kg: ' + precios_txt)
            HistorialEfectivoRemision.objects.create(efectivo=registro, usuario=user, accion='ALTA', cambios=cambios)
        else:
            cambios = af._cambios(antes, _foto(registro), folios_antes, folios_despues, '')
            if cambios:
                HistorialEfectivoRemision.objects.create(efectivo=registro, usuario=user, accion='MODIFICACION',
                                                         cambios=cambios)
    return registro


def _filtrar(qs, p):
    """Filtros de la lista: ?q&empresa&cliente&desde&hasta. La búsqueda encuentra también el número de
    captura (3R-E-001, E-1 o E1) y la remisión o el folio de descarga de sus remisiones."""
    q = af._mayusculas(p.get('q'), 100)
    if q:
        filtro = (Q(cliente__icontains=q) | Q(notas__icontains=q) | Q(remisiones__remision__icontains=q)
                  | Q(remisiones__folio_dlv__icontains=q))
        captura = re.fullmatch(r'(?:3R-?)?E-?0*(\d+)', q)
        if captura:
            filtro |= Q(captura=int(captura.group(1)))
        qs = qs.filter(filtro).distinct()
    if str(p.get('empresa', '')).isdigit():
        qs = qs.filter(empresa_id=int(p['empresa']))
    if (p.get('cliente') or '').strip():
        qs = qs.filter(cliente__iexact=p['cliente'].strip())
    if af._fecha(p.get('desde')):
        qs = qs.filter(fecha__gte=af._fecha(p.get('desde')))
    if af._fecha(p.get('hasta')):
        qs = qs.filter(fecha__lte=af._fecha(p.get('hasta')))
    return qs


def _cuerpo(request):
    datos = json.loads(request.body or b'{}')
    if not isinstance(datos, dict):
        raise ValueError
    return datos


@require_http_methods(['GET', 'POST'])
@af._api
def api_efectivos(request):
    """GET ?q&empresa&cliente&desde&hasta&page → operaciones en efectivo con sus remisiones, los totales
    por moneda y los clientes del filtro.
    POST {empresa, fecha, moneda, tipo_cambio (si es USD), notas, remisiones: [ids], precios: {id del detalle: precio por kg},
    monto_manual: bool, monto} → alta (con su número de captura). El monto es la suma de precio × kg
    descargados; con monto_manual se guarda el monto escrito y queda marcado como corregido a mano."""
    if request.method == 'POST':
        try:
            registro = _guardar(request.user, _cuerpo(request))
        except ValueError:
            return JsonResponse({'detail': 'Datos no válidos.'}, status=400)
        except ErrorEfectivo as e:
            return JsonResponse({'detail': str(e)}, status=400)
        return JsonResponse(_dict(registro), status=201)

    p = request.GET
    qs = _filtrar(_efectivos(request.user), p)
    # Sobre los pk: la búsqueda cruza con las remisiones y sumaría el monto una vez por cada una.
    filtrados = EfectivoRemision.objects.filter(pk__in=qs.values('pk'))
    totales = {m: float(filtrados.filter(moneda=m).aggregate(t=Sum('monto'))['t'] or 0) for m, _ in EfectivoRemision.MONEDAS}
    # Todo en pesos: lo cobrado en MXN más lo cobrado en USD a su tipo de cambio
    en_pesos = filtrados.filter(moneda='USD').aggregate(t=Sum(F('monto') * F('tipo_cambio')))['t'] or 0
    totales['equivalente_mxn'] = round(totales['MXN'] + float(en_pesos), 2)
    pagina = Paginator(qs.order_by('-fecha', '-pk'), POR_PAGINA).get_page(p.get('page') or 1)
    clientes = _efectivos(request.user).exclude(cliente='').order_by().values_list('cliente', flat=True).distinct()
    return JsonResponse({
        'resultados': [_dict(e) for e in pagina.object_list],
        'page': pagina.number, 'pages': pagina.paginator.num_pages, 'count': pagina.paginator.count,
        'totales': totales, 'sin_monto': filtrados.filter(monto__isnull=True).count(),
        'remisiones': Remision.objects.filter(efectivo_registro__in=filtrados).exclude(status='CANCELADO').count(),
        'clientes': sorted(set(clientes), key=str.upper),
    })


@require_http_methods(['GET', 'PATCH', 'POST', 'DELETE'])
@af._api
def api_efectivo(request, pk):
    """GET: la operación con sus remisiones. PATCH/POST: la actualiza (y sus remisiones). DELETE: la borra
    y sus remisiones quedan otra vez sin factura."""
    registro = _efectivos(request.user).filter(pk=pk).first()
    if not registro:
        return JsonResponse({'detail': 'Operación en efectivo no encontrada.'}, status=404)
    if request.method == 'GET':
        return JsonResponse(_dict(registro))
    if request.method == 'DELETE':
        with transaction.atomic():
            cuantas = Remision.objects.filter(efectivo_registro=registro).update(
                efectivo_registro=None, factura_asignada_por=None, factura_asignada_en=None,
                actualizado_en=timezone.now())
            captura = registro.numero_captura
            registro.delete()
        return JsonResponse({'ok': True, 'detail': f'Efectivo {captura} eliminado; sus {cuantas} remisión(es) '
                                                   'quedaron otra vez sin factura.'})
    try:
        registro = _guardar(request.user, _cuerpo(request), registro)
    except ValueError:
        return JsonResponse({'detail': 'Datos no válidos.'}, status=400)
    except ErrorEfectivo as e:
        return JsonResponse({'detail': str(e)}, status=400)
    return JsonResponse(_dict(registro))
