"""
Asignación de factura a remisiones (HTML: /remisiones/asignacion-factura/ · Next: /asignacion-factura).

Lista las remisiones que no están canceladas (de las unidades de negocio del
usuario), con búsqueda y filtros, y permite ver los datos de una remisión. Ahí la
factura solo se ve: se asigna únicamente desde "Facturas (alta y folios)". Todo lo
que se escribe se guarda en MAYÚSCULAS.

Facturas dadas de alta (FacturaRemision): número, fecha, cliente e importes
(subtotal, descuento, IVA, IEPS, retenciones de IVA e ISR, total), con los folios
que ampara (solo folios sin factura de la misma unidad de negocio). Se capturan a
mano (los impuestos se calculan con las tasas) o subiendo el XML del CFDI: de ahí
salen todos los datos y los folios escritos en la descripción de los conceptos se
proponen ya ligados para que el usuario solo los verifique. Los folios ligados
llevan el número en `Remision.factura_nombre` (el mismo campo "Nombre/Folio
Factura" del formulario de remisiones), con quién y cuándo, por UPDATE directo para
no recalcular el estatus ni tocar remisiones auditadas. Reporte detallado en Excel:
ternium/reporte_facturas.py.

Permiso: ternium.acceso_asignacion_factura (Permisos de usuario › Asignación de Factura).
"""
import datetime as dt
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from .cfdi_xml import ErrorCFDI, leer_cfdi
from .models import Empresa, FacturaRemision, HistorialFacturaRemision, Remision

PERMISO = 'ternium.acceso_asignacion_factura'
POR_PAGINA = 50
MAX_FACTURA = 100
ESTATUS = dict(Remision.STATUS_CHOICES)


def puede_usar(user):
    return user.is_authenticated and (user.is_superuser or user.has_perm(PERMISO))


def _empresas(user):
    if user.is_superuser:
        return Empresa.objects.all()
    perfil = getattr(user, 'ternium_profile', None)
    return perfil.empresas_autorizadas.all() if perfil else Empresa.objects.none()


def _mayusculas(texto, largo=MAX_FACTURA):
    return ' '.join(str(texto or '').split()).upper()[:largo]


def _fecha(texto):
    try:
        return dt.date.fromisoformat(str(texto)[:10]) if texto else None
    except ValueError:
        return None


def _base(user):
    """Remisiones que no están canceladas y tienen número de remisión, de las empresas del usuario."""
    return (Remision.objects.filter(empresa__in=_empresas(user))
            .exclude(status='CANCELADO').exclude(remision__isnull=True).exclude(remision='')
            .select_related('empresa', 'cliente', 'destino', 'origen', 'factura_asignada_por', 'factura_registro'))


def _sin_factura_q():
    return Q(factura_nombre__isnull=True) | Q(factura_nombre='')


def _nombre(user):
    return (user.get_full_name() or user.username) if user else ''


def _fila(r):
    return {
        'id': r.pk,
        'remision': r.remision,
        'fecha': r.fecha.isoformat() if r.fecha else None,
        'empresa': r.empresa.nombre if r.empresa_id else '',
        'cliente': (r.cliente.nombre if r.cliente_id else '') or (r.destino.nombre if r.destino_id else ''),
        'origen': r.origen.nombre if r.origen_id else '',
        'status': r.status,
        'status_texto': ESTATUS.get(r.status, r.status),
        'factura': r.factura_nombre or '',
        # Si el folio está ligado a una factura dada de alta: su total
        'factura_id': r.factura_registro_id,
        'factura_total': float(r.factura_registro.total) if r.factura_registro_id else None,
        'factura_moneda': r.factura_registro.moneda if r.factura_registro_id else '',
        'asignada_por': _nombre(r.factura_asignada_por),
        'asignada_en': timezone.localtime(r.factura_asignada_en).strftime('%d/%m/%Y %H:%M') if r.factura_asignada_en else '',
    }


def _api(vista):
    """Sesión y permiso para las APIs del módulo (respuestas JSON)."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'detail': 'No autenticado.'}, status=401)
        if not puede_usar(request.user):
            return JsonResponse({'detail': 'No tienes el permiso "Asignación de Factura".'}, status=403)
        return vista(request, *args, **kwargs)
    return envoltura


FECHAS_FILTRO = {  # ?fecha_de= → campo de la remisión
    'carga': 'inicia_ld',                            # inicio de carga
    'captura': 'creado_en',                          # captura de la remisión en el sistema
    'timbrado': 'factura_registro__fecha_timbrado',  # timbrado de la factura (XML)
}


@require_http_methods(['GET'])
@_api
def api_lista(request):
    """GET ?q&factura=sin|con&empresa&status&desde&hasta&fecha_de&page → filas, conteos y empresas.
    fecha_de: a qué fecha aplican desde/hasta (inicio de carga, captura en el sistema o timbrado de la factura)."""
    p = request.GET
    qs = _base(request.user)
    q = _mayusculas(p.get('q'), 100)
    if q:
        filtro = Q()
        for campo in ('remision', 'factura_nombre', 'empresa__nombre', 'cliente__nombre', 'destino__nombre',
                      'origen__nombre', 'folio_ld', 'folio_dlv', 'folio_medline', 'folio_salida',
                      'operador__nombre', 'operador_manual', 'unidad__internal_id', 'unidad_manual'):
            filtro |= Q(**{f'{campo}__icontains': q})
        qs = qs.filter(filtro)
    if str(p.get('empresa', '')).isdigit():
        qs = qs.filter(empresa_id=int(p['empresa']))
    if p.get('status') in ('PENDIENTE', 'TERMINADO', 'AUDITADO'):
        qs = qs.filter(status=p['status'])
    campo = FECHAS_FILTRO.get(p.get('fecha_de'), FECHAS_FILTRO['carga'])
    if _fecha(p.get('desde')):
        qs = qs.filter(**{f'{campo}__date__gte': _fecha(p.get('desde'))})
    if _fecha(p.get('hasta')):
        qs = qs.filter(**{f'{campo}__date__lte': _fecha(p.get('hasta'))})

    sin = qs.filter(_sin_factura_q()).count()
    total = qs.count()
    if p.get('factura') == 'sin':
        qs = qs.filter(_sin_factura_q())
    elif p.get('factura') == 'con':
        qs = qs.exclude(_sin_factura_q())

    pagina = Paginator(qs.order_by('-fecha', '-pk'), POR_PAGINA).get_page(p.get('page') or 1)
    return JsonResponse({
        'resultados': [_fila(r) for r in pagina.object_list],
        'page': pagina.number, 'pages': pagina.paginator.num_pages, 'count': pagina.paginator.count,
        'conteos': {'total': total, 'sin_factura': sin, 'con_factura': total - sin},
        'empresas': [{'id': e.pk, 'nombre': e.nombre} for e in _empresas(request.user).order_by('nombre')],
    })


def catalogo_sat(tipo, claves):
    """{clave: descripción} del catálogo del SAT cargado en facturación (52 mil claves)."""
    claves = {c for c in claves if c}
    if not claves:
        return {}
    try:
        from facturacion.models import CatalogoSAT
    except ImportError:
        return {}
    return dict(CatalogoSAT.objects.filter(tipo=tipo, clave__in=claves).values_list('clave', 'descripcion'))


def _factura_de_remision(r):
    """La factura dada de alta de la remisión, con los datos de su XML y sus conceptos;
    se marcan los conceptos cuyo folio (en la descripción) es el de esta remisión."""
    f = r.factura_registro
    if f is None:
        return None
    conceptos = list(f.conceptos or [])
    prod = catalogo_sat('ClaveProdServ', {c.get('clave_prod_serv') for c in conceptos})
    unidad = catalogo_sat('ClaveUnidad', {c.get('clave_unidad') for c in conceptos})
    propias = claves_de_folio(r)
    return {
        **_factura_dict(f, folios=False),
        'conceptos': [{
            **c, 'clave_sat_desc': prod.get(c.get('clave_prod_serv'), ''),
            'unidad': c.get('unidad') or unidad.get(c.get('clave_unidad'), ''),
            'de_esta_remision': bool(propias & {_norm(x) for x in c.get('folios') or []}),
        } for c in conceptos],
        'remisiones': list(f.remisiones.exclude(status='CANCELADO').order_by('remision').values_list('remision', flat=True)),
    }


ARCHIVOS_REMISION = [  # (campo, nombre) de las fotos y documentos que se guardan en la remisión
    ('evidencia_documento', 'Evidencia'), ('manifiesto', 'Manifiesto'),
    ('foto_ingreso', 'Ingreso de la unidad'), ('foto_ingreso_2', 'Ingreso de la unidad (2)'),
    ('foto_vertido', 'Vertido del material'), ('foto_vertido_2', 'Vertido del material (2)'),
    ('foto_destruccion', 'Destrucción'), ('foto_destruccion_2', 'Destrucción (2)'),
    ('boleta_salida_medline', 'Boleta de salida Medline'),
]
IMAGENES = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif')


def _archivos(r):
    """Fotografías y documentos cargados a la remisión: [{nombre, url, imagen}]."""
    def item(archivo, nombre):
        try:
            url = archivo.url
        except Exception:  # archivo sin almacenamiento disponible
            return None
        return {'nombre': nombre, 'url': url, 'imagen': archivo.name.lower().endswith(IMAGENES)}

    salida = []
    for campo, nombre in ARCHIVOS_REMISION:
        archivo = getattr(r, campo, None)
        if archivo and archivo.name:
            salida.append(item(archivo, nombre))
    for n, ev in enumerate(r.evidencias.all(), 1):
        if ev.archivo and ev.archivo.name:
            salida.append(item(ev.archivo, f'Evidencia {n}'))
    return [x for x in salida if x]


def _detalle(r):
    """Todos los datos de la remisión para la ventana emergente."""
    detalles = list(r.detalles.select_related('material', 'cliente').all())
    pesos = r.detalles.aggregate(carga=Sum('peso_ld'), descarga=Sum('peso_dlv'), rechazo=Sum('peso_rechazado'))
    carga, descarga, rechazo = (float(pesos[k] or 0) for k in ('carga', 'descarga', 'rechazo'))
    fecha_hora = lambda v: timezone.localtime(v).strftime('%d/%m/%Y %H:%M') if v else ''  # noqa: E731
    try:
        cfdi = [{'folio': f'{f.serie or ""}{f.folio or ""}' or str(f.pk), 'estado': getattr(f, 'estado', '')}
                for f in r.facturas.all()]
    except Exception:  # el módulo de facturación CFDI es opcional
        cfdi = []
    return {
        **_fila(r),
        'operador': (r.operador.nombre if r.operador_id else '') or (r.operador_manual or ''),
        'unidad': (r.unidad.internal_id if r.unidad_id else '') or (r.unidad_manual or ''),
        'placas_unidad': (r.unidad.license_plate if r.unidad_id else '') or (r.placas_unidad_manual or ''),
        'contenedor': (str(r.contenedor) if r.contenedor_id else '') or (r.contenedor_manual or ''),
        'linea_transporte': str(r.linea_transporte) if r.linea_transporte_id else '',
        'destino': r.destino.nombre if r.destino_id else '',
        'folio_ld': r.folio_ld or '', 'folio_dlv': r.folio_dlv or '',
        'folio_medline': r.folio_medline or '', 'folio_salida': r.folio_salida or '',
        'inicia_ld': fecha_hora(r.inicia_ld), 'termina_ld': fecha_hora(r.termina_ld),
        'inicia_dlv': fecha_hora(r.inicia_dlv), 'termina_dlv': fecha_hora(r.termina_dlv),
        'carga_kg': carga, 'descarga_kg': descarga, 'rechazo_kg': rechazo,
        'merma_pct': round((carga - descarga - rechazo) / carga * 100, 2) if carga else 0,
        'peso_bascula': float(r.peso_bascula) if r.peso_bascula is not None else None,
        'materiales': [{
            'material': d.material.nombre if d.material_id else '—',
            'cliente': d.cliente.nombre if d.cliente_id else '',
            'carga': float(d.peso_ld or 0), 'descarga': float(d.peso_dlv or 0), 'rechazo': float(d.peso_rechazado or 0),
            'unidad': d.unidad_medida, 'bultos': d.bultos,
        } for d in detalles],
        'descripcion': r.descripcion or '', 'comentario': r.comentario or '',
        'auditado_por': _nombre(r.auditado_por), 'auditado_en': fecha_hora(r.auditado_en),
        'cfdi': cfdi,
        'factura_alta': _factura_de_remision(r),
        'archivos': _archivos(r),
    }


@require_http_methods(['GET'])
@_api
def api_remision(request, pk):
    """GET: datos de la remisión (solo lectura; la factura se asigna en "Facturas (alta y folios)")."""
    r = _base(request.user).select_related('operador', 'unidad', 'contenedor', 'linea_transporte', 'auditado_por') \
        .filter(pk=pk).first()
    if not r:
        return JsonResponse({'detail': 'Remisión no encontrada (o está cancelada).'}, status=404)
    return JsonResponse(_detalle(r))


def _numero_folio(texto):
    """Número del folio de remisión: los dígitos del final ('MTY-1787' → 1787)."""
    m = re.search(r'(\d+)\s*$', str(texto or ''))
    return int(m.group(1)) if m else None


# ════════════════════════════════════════════════════════════════════════════
# FACTURAS DADAS DE ALTA: número, fecha, cliente, total y los folios que ampara.
# Solo se ligan folios SIN factura de la misma unidad de negocio; al ligarlos
# toman el número (factura_nombre). Quitar un folio o borrar la factura los deja
# otra vez sin factura.
# ════════════════════════════════════════════════════════════════════════════
MAX_DISPONIBLES = 1000


class ErrorFactura(Exception):
    pass


def _facturas(user):
    return FacturaRemision.objects.filter(empresa__in=_empresas(user)).select_related('empresa', 'creado_por')


def _kg_por_remision(ids):
    filas = (Remision.objects.filter(pk__in=ids).values('pk')
             .annotate(carga=Sum('detalles__peso_ld'), descarga=Sum('detalles__peso_dlv')))
    return {f['pk']: (float(f['carga'] or 0), float(f['descarga'] or 0)) for f in filas}


def _folio_dict(r, kg):
    carga, descarga = kg.get(r.pk, (0.0, 0.0))
    return {
        'id': r.pk, 'remision': r.remision, 'fecha': r.fecha.isoformat() if r.fecha else None,
        'cliente': (r.cliente.nombre if r.cliente_id else '') or (r.destino.nombre if r.destino_id else ''),
        'status_texto': ESTATUS.get(r.status, r.status), 'carga_kg': carga, 'descarga_kg': descarga,
        'factura': r.factura_nombre or '',
    }


IMPORTES = ('subtotal', 'descuento', 'iva_tasa', 'iva_importe', 'ieps_tasa', 'ieps_importe',
            'ret_iva_tasa', 'ret_iva_importe', 'ret_isr_tasa', 'ret_isr_importe', 'tipo_cambio', 'total')
DATOS_CFDI = ('serie', 'folio', 'uuid', 'tipo_comprobante', 'forma_pago', 'metodo_pago', 'uso_cfdi',
              'lugar_expedicion', 'emisor_rfc', 'emisor_nombre', 'receptor_rfc')


def _factura_dict(f, folios=True):
    datos = {
        'id': f.pk, 'empresa': {'id': f.empresa_id, 'nombre': f.empresa.nombre}, 'numero': f.numero,
        'fecha': f.fecha.isoformat(), 'cliente': f.cliente, 'moneda': f.moneda,
        'notas': f.notas, 'creado_por': _nombre(f.creado_por),
        'creado_en': timezone.localtime(f.creado_en).strftime('%d/%m/%Y %H:%M'),
        **{k: float(getattr(f, k)) for k in IMPORTES},
        **{k: getattr(f, k) for k in DATOS_CFDI},
        'fecha_timbrado': timezone.localtime(f.fecha_timbrado).strftime('%d/%m/%Y %H:%M') if f.fecha_timbrado else '',
        'conceptos': f.conceptos or [], 'tiene_xml': bool(f.xml),
        'xml_url': f'/api/asignacion-factura/facturas/{f.pk}/xml/' if f.xml else None,
    }
    if folios:
        lista = list(f.remisiones.exclude(status='CANCELADO').select_related('cliente', 'destino')
                     .order_by('remision'))
        kg = _kg_por_remision([r.pk for r in lista])
        datos['folios'] = sorted((_folio_dict(r, kg) for r in lista),
                                 key=lambda x: (_numero_folio(x['remision']) or 0, x['remision']))
        datos['num_folios'] = len(lista)
        datos['descarga_kg'] = round(sum(x['descarga_kg'] for x in datos['folios']), 3)
        datos['historial'] = _historial(f)
    return datos


def _historial(f):
    """Modificaciones de la factura (la más reciente primero). Las facturas dadas de alta antes de
    la bitácora muestran su alta con quién y cuándo la crearon."""
    entradas = [{
        'fecha': timezone.localtime(h.fecha).strftime('%d/%m/%Y %H:%M'), 'usuario': _nombre(h.usuario) or '—',
        'accion': h.get_accion_display(), 'cambios': h.cambios or [],
    } for h in HistorialFacturaRemision.objects.filter(factura=f).select_related('usuario')]
    if not any(e['accion'] == 'Alta' for e in entradas):
        entradas.append({'fecha': timezone.localtime(f.creado_en).strftime('%d/%m/%Y %H:%M'),
                         'usuario': _nombre(f.creado_por) or '—', 'accion': 'Alta', 'cambios': []})
    return entradas


def _foto(f):
    """Lo que se compara para la bitácora: {campo: texto}."""
    dinero = lambda n: f'${float(n):,.2f}'  # noqa: E731
    tasa = lambda n: f'{float(n):g} %'  # noqa: E731
    return {
        'Número': f.numero, 'Fecha': f.fecha.strftime('%d/%m/%Y') if f.fecha else '',
        'Unidad de negocio': f.empresa.nombre if f.empresa_id else '', 'Cliente': f.cliente, 'Moneda': f.moneda,
        'Notas': f.notas, 'Subtotal': dinero(f.subtotal), 'Descuento': dinero(f.descuento),
        'IVA': tasa(f.iva_tasa), 'IEPS': tasa(f.ieps_tasa), 'Retención IVA': tasa(f.ret_iva_tasa),
        'Retención ISR': tasa(f.ret_isr_tasa), 'Total': dinero(f.total), 'UUID': f.uuid,
    }


def _cambios(antes, despues, folios_antes, folios_despues, xml):
    """Lista legible de lo que cambió entre dos fotos de la factura."""
    cambios = [f'{campo}: {antes[campo] or "—"} → {despues[campo] or "—"}'
               for campo in despues if antes.get(campo) != despues[campo]]
    agregados = sorted(folios_despues - folios_antes, key=lambda x: (_numero_folio(x) or 0, x))
    quitados = sorted(folios_antes - folios_despues, key=lambda x: (_numero_folio(x) or 0, x))
    if agregados:
        cambios.append('Folios agregados: ' + ', '.join(agregados))
    if quitados:
        cambios.append('Folios quitados: ' + ', '.join(quitados))
    if xml:
        cambios.append(xml)
    return cambios


def _decimal(valor, campo):
    try:
        n = Decimal(str(valor).replace(',', '').replace('$', '').strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ErrorFactura(f'{campo}: escribe una cantidad.')
    if n <= 0:
        raise ErrorFactura(f'{campo} debe ser mayor a cero.')
    if n >= Decimal('1000000000000'):
        raise ErrorFactura(f'{campo} es demasiado grande.')
    return n


def _tasa(valor, nombre):
    """Tasa en % escrita por el usuario (16, 8, 0.53…); vacía = 0."""
    if valor in (None, ''):
        return Decimal(0)
    try:
        n = Decimal(str(valor).replace('%', '').replace(',', '').strip()).quantize(Decimal('0.0001'))
    except (InvalidOperation, ValueError):
        raise ErrorFactura(f'{nombre}: escribe un porcentaje (ej. 16).')
    if n < 0 or n > 100:
        raise ErrorFactura(f'{nombre} debe estar entre 0 y 100 %.')
    return n


def _importes_manual(body):
    """Importes de una factura capturada a mano: con subtotal, descuento y las tasas se
    calculan IEPS, IVA, retenciones y el total (como en un CFDI)."""
    if body.get('subtotal') in (None, '') and body.get('total') not in (None, ''):
        total = _decimal(body.get('total'), 'El total')  # solo el total, sin desglose
        return {'subtotal': total, 'descuento': Decimal(0), 'total': total}
    subtotal = _decimal(body.get('subtotal'), 'El subtotal')
    descuento = Decimal(0) if body.get('descuento') in (None, '') else _decimal(body.get('descuento'), 'El descuento')
    base = subtotal - descuento
    if base <= 0:
        raise ErrorFactura('El descuento no puede ser mayor o igual al subtotal.')
    t = {k: _tasa(body.get(k), n) for k, n in (('iva_tasa', 'IVA'), ('ieps_tasa', 'IEPS'),
                                                ('ret_iva_tasa', 'Retención de IVA'), ('ret_isr_tasa', 'Retención de ISR'))}
    d2 = lambda n: n.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)  # noqa: E731
    ieps = d2(base * t['ieps_tasa'] / 100)
    iva = d2((base + ieps) * t['iva_tasa'] / 100)  # el IVA se calcula sobre el precio con IEPS
    ret_iva, ret_isr = d2(base * t['ret_iva_tasa'] / 100), d2(base * t['ret_isr_tasa'] / 100)
    total = base + ieps + iva - ret_iva - ret_isr
    if total <= 0:
        raise ErrorFactura('Con esas retenciones el total queda en cero o negativo.')
    return {'subtotal': subtotal, 'descuento': descuento, **t, 'ieps_importe': ieps, 'iva_importe': iva,
            'ret_iva_importe': ret_iva, 'ret_isr_importe': ret_isr, 'total': total}


def _importes_cfdi(cfdi):
    return {**{k: Decimal(str(cfdi[k])) for k in ('subtotal', 'descuento', 'iva_tasa', 'iva_importe', 'ieps_tasa',
                                                    'ieps_importe', 'ret_iva_tasa', 'ret_iva_importe', 'ret_isr_tasa',
                                                    'ret_isr_importe', 'tipo_cambio', 'total')}}


def _borrar_xml_al_confirmar(archivo):
    """Borra del almacenamiento el XML guardado, solo si la transacción se confirma."""
    if not archivo:
        return
    almacen, nombre = archivo.storage, archivo.name

    def borrar():
        try:
            almacen.delete(nombre)
        except Exception:
            pass
    transaction.on_commit(borrar)


def _guardar_factura(user, body, factura=None, xml=None):
    """Crea o actualiza la factura y deja ligados exactamente los folios de body['remisiones'].
    Con XML (CFDI) los importes y datos fiscales salen del XML; si no, se calculan de lo capturado."""
    empresa = _empresas(user).filter(pk=body.get('empresa') if str(body.get('empresa', '')).isdigit() else None).first()
    if not empresa:
        raise ErrorFactura('Elige la unidad de negocio.')
    cfdi = contenido_xml = None
    if xml:
        contenido_xml = xml.read()
        try:
            cfdi = leer_cfdi(contenido_xml)
        except ErrorCFDI as e:
            raise ErrorFactura(str(e))
        if cfdi['tipo_comprobante'] in ('P', 'T') or cfdi['total'] <= 0:
            raise ErrorFactura('Ese XML no es una factura con importe (parece un complemento de pago o un traslado).')
        if cfdi['uuid']:
            otra = FacturaRemision.objects.filter(uuid__iexact=cfdi['uuid'])
            if factura:
                otra = otra.exclude(pk=factura.pk)
            otra = otra.first()
            if otra:
                raise ErrorFactura(f'Este XML (UUID {cfdi["uuid"]}) ya está dado de alta en la factura {otra.numero}.')
    numero = _mayusculas(body.get('numero')) or (cfdi['numero_sugerido'] if cfdi else '')
    if not numero:
        raise ErrorFactura('Escribe el número de factura.')
    repetida = FacturaRemision.objects.filter(numero__iexact=numero)
    if factura:
        repetida = repetida.exclude(pk=factura.pk)
    if repetida.exists():
        raise ErrorFactura(f'Ya existe la factura {numero}.')
    if cfdi and cfdi['fecha']:
        fecha = _fecha(cfdi['fecha'])
    elif factura and factura.xml:
        fecha = factura.fecha  # la fecha del XML no se cambia a mano
    else:
        fecha = _fecha(body.get('fecha'))
    if not fecha:
        raise ErrorFactura('Escribe la fecha de la factura.')
    if cfdi:
        importes = _importes_cfdi(cfdi)
        moneda = cfdi['moneda'] if cfdi['moneda'] in dict(FacturaRemision.MONEDAS) else 'MXN'
    elif factura and factura.xml:
        importes, moneda = {}, factura.moneda  # ya tiene XML: sus importes no se tocan
    else:
        importes = _importes_manual(body)
        moneda = body.get('moneda') if body.get('moneda') in dict(FacturaRemision.MONEDAS) else 'MXN'

    ids = {int(i) for i in (body.get('remisiones') or []) if str(i).isdigit()}
    folios = {r.pk: r for r in _base(user).filter(pk__in=ids)}
    faltan = ids - set(folios)
    if faltan:
        raise ErrorFactura(f'{len(faltan)} folio(s) no existen, están cancelados o no son de tus unidades de negocio.')
    otra_empresa = [r.remision for r in folios.values() if r.empresa_id != empresa.pk]
    if otra_empresa:
        raise ErrorFactura(f'Estos folios no son de {empresa.nombre}: {", ".join(otra_empresa[:10])}.')
    con_otra = [f'{r.remision} ({r.factura_nombre})' for r in folios.values()
                if r.factura_nombre and (not factura or r.factura_registro_id != factura.pk)]
    if con_otra:
        raise ErrorFactura('Estos folios ya tienen factura y no se pueden ligar: ' + ', '.join(con_otra[:10]) + '.')

    ahora = timezone.now()
    nueva = factura is None
    # Para la bitácora: cómo estaba antes
    antes = None if nueva else _foto(factura)
    folios_antes = set() if nueva else set(Remision.objects.filter(factura_registro=factura).values_list('remision', flat=True))
    tenia_xml = bool(factura and factura.xml)
    with transaction.atomic():
        if factura is None:
            factura = FacturaRemision(creado_por=user)
        factura.empresa, factura.numero, factura.fecha, factura.moneda = empresa, numero, fecha, moneda
        if importes:
            for campo in ('iva_tasa', 'iva_importe', 'ieps_tasa', 'ieps_importe', 'ret_iva_tasa', 'ret_iva_importe',
                          'ret_isr_tasa', 'ret_isr_importe'):
                setattr(factura, campo, Decimal(0))  # lo que no venga queda en cero
            for campo, valor in importes.items():
                setattr(factura, campo, valor)
        # Con XML el cliente es el receptor del CFDI (no se puede cambiar a mano)
        if cfdi:
            factura.cliente = _mayusculas(cfdi['receptor']['nombre'], 200)
        elif not factura.xml:
            factura.cliente = _mayusculas(body.get('cliente'), 200)
        factura.notas = ' '.join(str(body.get('notas') or '').split()).upper()[:2000]
        if cfdi:
            factura.serie, factura.folio, factura.uuid = cfdi['serie'][:25], cfdi['folio'][:40], cfdi['uuid'][:40]
            timbrado = parse_datetime(cfdi['fecha_timbrado'] or '')
            if timbrado and timezone.is_naive(timbrado):
                timbrado = timezone.make_aware(timbrado)
            factura.fecha_timbrado = timbrado
            factura.tipo_comprobante, factura.forma_pago = cfdi['tipo_comprobante'][:2], cfdi['forma_pago'][:5]
            factura.metodo_pago, factura.uso_cfdi = cfdi['metodo_pago'][:5], cfdi['receptor']['uso_cfdi'][:5]
            factura.lugar_expedicion = cfdi['lugar_expedicion'][:10]
            factura.emisor_rfc, factura.emisor_nombre = cfdi['emisor']['rfc'][:13], cfdi['emisor']['nombre'][:255]
            factura.receptor_rfc = cfdi['receptor']['rfc'][:13]
            factura.conceptos = cfdi['conceptos']
            _borrar_xml_al_confirmar(factura.xml)  # el XML anterior (si se reemplaza)
            factura.xml.save(f'{(cfdi["uuid"] or numero)[:40]}.xml', ContentFile(contenido_xml), save=False)
        factura.save()
        # Los folios que se quitaron quedan otra vez sin factura
        Remision.objects.filter(factura_registro=factura).exclude(pk__in=ids).update(
            factura_registro=None, factura_nombre=None, factura_asignada_por=None, factura_asignada_en=None,
            actualizado_en=ahora)
        # Ligar: solo los que siguen sin factura o ya eran de esta (el filtro va en el UPDATE)
        ligados = Remision.objects.filter(pk__in=ids).filter(_sin_factura_q() | Q(factura_registro=factura)).update(
            factura_registro=factura, factura_nombre=numero, factura_asignada_por=user, factura_asignada_en=ahora,
            actualizado_en=ahora)
        if ligados != len(ids):
            raise ErrorFactura('Alguien le asignó factura a uno de los folios mientras tanto. Vuelve a intentarlo.')
        # Bitácora: quién, cuándo y qué cambió
        folios_despues = {folios[i].remision for i in ids}
        if nueva:
            cambios = [f'Alta {"con XML (UUID " + factura.uuid + ")" if cfdi else "capturada a mano"} · '
                       f'Total ${factura.total:,.2f} {factura.moneda}']
            if folios_despues:
                cambios.append('Folios: ' + ', '.join(sorted(folios_despues, key=lambda x: (_numero_folio(x) or 0, x))))
            HistorialFacturaRemision.objects.create(factura=factura, usuario=user, accion='ALTA', cambios=cambios)
        else:
            nota_xml = (f'XML {"reemplazado" if tenia_xml else "cargado"} (UUID {factura.uuid})' if cfdi else '')
            cambios = _cambios(antes, _foto(factura), folios_antes, folios_despues, nota_xml)
            if cambios:
                HistorialFacturaRemision.objects.create(factura=factura, usuario=user, accion='MODIFICACION', cambios=cambios)
    return factura


def filtrar_facturas(qs, p):
    """Filtros de la lista de facturas (y del reporte): ?q&empresa&desde&hasta."""
    q = _mayusculas(p.get('q'), 100)
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(cliente__icontains=q) | Q(remisiones__remision__icontains=q)
                       | Q(notas__icontains=q) | Q(uuid__icontains=q)).distinct()
    if str(p.get('empresa', '')).isdigit():
        qs = qs.filter(empresa_id=int(p['empresa']))
    if _fecha(p.get('desde')):
        qs = qs.filter(fecha__gte=_fecha(p.get('desde')))
    if _fecha(p.get('hasta')):
        qs = qs.filter(fecha__lte=_fecha(p.get('hasta')))
    return qs


@require_http_methods(['GET', 'POST'])
@_api
def api_facturas(request):
    """GET ?q&empresa&desde&hasta&page → facturas dadas de alta con sus folios.
    POST {empresa, numero, fecha, cliente, total, moneda, notas, remisiones: [ids]} → alta."""
    if request.method == 'POST':
        try:
            body, xml = _cuerpo(request)
            factura = _guardar_factura(request.user, body, xml=xml)
        except ValueError:
            return JsonResponse({'detail': 'Datos no válidos.'}, status=400)
        except ErrorFactura as e:
            return JsonResponse({'detail': str(e)}, status=400)
        return JsonResponse(_factura_dict(factura), status=201)

    p = request.GET
    qs = filtrar_facturas(_facturas(request.user), p)
    totales = {m: float(qs.filter(moneda=m).aggregate(t=Sum('total'))['t'] or 0) for m, _ in FacturaRemision.MONEDAS}
    pagina = Paginator(qs.order_by('-fecha', '-pk'), 25).get_page(p.get('page') or 1)
    return JsonResponse({
        'resultados': [_factura_dict(f) for f in pagina.object_list],
        'page': pagina.number, 'pages': pagina.paginator.num_pages, 'count': pagina.paginator.count,
        'totales': totales,
    })


@require_http_methods(['GET', 'PATCH', 'POST', 'DELETE'])
@_api
def api_factura(request, pk):
    """GET: la factura con sus folios. PATCH/POST: actualiza (y los folios ligados). DELETE: la borra
    y sus folios quedan sin factura."""
    factura = _facturas(request.user).filter(pk=pk).first()
    if not factura:
        return JsonResponse({'detail': 'Factura no encontrada.'}, status=404)
    if request.method == 'GET':
        return JsonResponse(_factura_dict(factura))
    if request.method == 'DELETE':
        with transaction.atomic():
            Remision.objects.filter(factura_registro=factura).update(
                factura_registro=None, factura_nombre=None, factura_asignada_por=None, factura_asignada_en=None,
                actualizado_en=timezone.now())
            numero = factura.numero
            _borrar_xml_al_confirmar(factura.xml)
            factura.delete()
        return JsonResponse({'ok': True, 'detail': f'Factura {numero} eliminada; sus folios quedaron sin factura.'})
    try:
        body, xml = _cuerpo(request)
        factura = _guardar_factura(request.user, body, factura, xml=xml)
    except ValueError:
        return JsonResponse({'detail': 'Datos no válidos.'}, status=400)
    except ErrorFactura as e:
        return JsonResponse({'detail': str(e)}, status=400)
    return JsonResponse(_factura_dict(factura))


def _cuerpo(request):
    """(datos, xml): JSON normal, o multipart con 'datos' (JSON) y el archivo 'xml'."""
    if request.content_type.startswith('multipart/'):
        return json.loads(request.POST.get('datos') or '{}'), request.FILES.get('xml')
    return json.loads(request.body or b'{}'), None


def _norm(texto):
    return re.sub(r'[^A-Z0-9]', '', str(texto or '').upper())


def claves_de_folio(r):
    """Los números con que se puede escribir una remisión (remisión y folios), normalizados."""
    return {k for k in (_norm(r.remision), _norm(r.folio_ld), _norm(r.folio_dlv), _norm(r.folio_medline),
                        _norm(r.folio_salida)) if k}


def remisiones_del_folio(qs, folio):
    """Remisiones de qs cuyo número o folio es `folio`, sin importar guiones ni espacios."""
    n = _norm(folio)
    digitos = re.search(r'(\d+)$', n)
    if not digitos:
        return []
    d = digitos.group(1)
    candidatas = qs.filter(Q(remision__icontains=d) | Q(folio_ld__icontains=d) | Q(folio_dlv__icontains=d)
                           | Q(folio_medline__icontains=d) | Q(folio_salida__icontains=d))[:100]
    return [r for r in candidatas if n in claves_de_folio(r)]


def _buscar_folios(user, folios, factura_id=None):
    """Para cada folio escrito en el XML, las remisiones (no canceladas, de las unidades de
    negocio del usuario) cuyo número o folio coincide, sin importar guiones ni espacios."""
    base = _base(user)
    por_folio = [(folio, remisiones_del_folio(base, folio)) for folio in folios[:200]]
    kg = _kg_por_remision([r.pk for _, rs in por_folio for r in rs])
    return [{'folio': folio, 'remisiones': [{
        **_folio_dict(r, kg), 'empresa_id': r.empresa_id, 'empresa': r.empresa.nombre,
        'libre': not r.factura_nombre or (factura_id is not None and r.factura_registro_id == factura_id),
    } for r in rs]} for folio, rs in por_folio]


@require_http_methods(['GET'])
@_api
def api_factura_xml(request, pk):
    """Descarga el XML (CFDI) guardado de la factura."""
    factura = _facturas(request.user).filter(pk=pk).first()
    if not factura or not factura.xml:
        return JsonResponse({'detail': 'La factura no tiene XML.'}, status=404)
    try:
        with factura.xml.open('rb') as archivo:
            contenido = archivo.read()
    except (FileNotFoundError, OSError):
        return JsonResponse({'detail': 'No se encontró el archivo XML.'}, status=404)
    respuesta = HttpResponse(contenido, content_type='application/xml')
    nombre = re.sub(r'[^A-Za-z0-9_-]', '_', factura.numero) or 'factura'
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}.xml"'
    return respuesta


MAX_ZIP = 3000


@require_http_methods(['GET'])
@_api
def api_xml_zip(request):
    """GET ?desde&hasta (fecha de timbrado) → ZIP con los XML guardados de las facturas timbradas en ese rango."""
    desde, hasta = _fecha(request.GET.get('desde')), _fecha(request.GET.get('hasta'))
    if not desde or not hasta:
        return JsonResponse({'detail': 'Escribe la fecha de timbrado desde y hasta.'}, status=400)
    if desde > hasta:
        desde, hasta = hasta, desde
    qs = (_facturas(request.user).exclude(xml='').exclude(xml__isnull=True)
          .filter(fecha_timbrado__date__gte=desde, fecha_timbrado__date__lte=hasta).order_by('fecha_timbrado', 'numero'))
    cuantas = qs.count()
    if not cuantas:
        return JsonResponse({'detail': 'No hay facturas con XML timbradas en esas fechas.'}, status=404)
    if cuantas > MAX_ZIP:
        return JsonResponse({'detail': f'Son {cuantas:,} XML: acota las fechas (máximo {MAX_ZIP:,}).'}, status=400)
    import io
    import zipfile
    salida, usados, faltan = io.BytesIO(), set(), []
    with zipfile.ZipFile(salida, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in qs:
            try:
                with f.xml.open('rb') as archivo:
                    contenido = archivo.read()
            except (FileNotFoundError, OSError):
                faltan.append(f.numero)
                continue
            nombre = re.sub(r'[^A-Za-z0-9_-]', '_', f.numero) + (f'_{f.uuid}' if f.uuid else '')
            while f'{nombre}.xml' in usados:
                nombre += '_'
            usados.add(f'{nombre}.xml')
            zf.writestr(f'{nombre}.xml', contenido)
        if faltan:
            zf.writestr('LEEME - XML no encontrados.txt', 'No se encontró el archivo XML de: ' + ', '.join(faltan))
    respuesta = HttpResponse(salida.getvalue(), content_type='application/zip')
    respuesta['Content-Disposition'] = f'attachment; filename="XML facturas timbradas {desde:%Y-%m-%d} a {hasta:%Y-%m-%d}.zip"'
    return respuesta


@require_http_methods(['POST'])
@_api
def api_leer_xml(request):
    """POST multipart {xml, factura?}: lee el CFDI y busca las remisiones de los folios que trae.
    No guarda nada: sirve para llenar el formulario de alta."""
    archivo = request.FILES.get('xml')
    if not archivo or not archivo.name.lower().endswith('.xml'):
        return JsonResponse({'detail': 'Sube el XML de la factura (.xml).'}, status=400)
    try:
        cfdi = leer_cfdi(archivo.read())
    except ErrorCFDI as e:
        return JsonResponse({'detail': str(e)}, status=400)
    factura_id = int(request.POST['factura']) if str(request.POST.get('factura', '')).isdigit() else None
    coincidencias = _buscar_folios(request.user, cfdi['folios_detectados'], factura_id)
    empresas = [r['empresa_id'] for c in coincidencias for r in c['remisiones']]
    ya = FacturaRemision.objects.filter(uuid__iexact=cfdi['uuid']).exclude(pk=factura_id).first() if cfdi['uuid'] else None
    return JsonResponse({
        'cfdi': cfdi, 'coincidencias': coincidencias,
        'empresa_sugerida': max(set(empresas), key=empresas.count) if empresas else None,
        'ya_registrada': {'id': ya.pk, 'numero': ya.numero} if ya else None,
    })


@require_http_methods(['GET'])
@_api
def api_disponibles(request):
    """GET ?empresa&q&folio_desde&folio_hasta&factura=<id> → folios que se pueden ligar: los de la unidad de
    negocio que no tienen factura (y, al editar, los que ya son de esa factura)."""
    p = request.GET
    if not str(p.get('empresa', '')).isdigit():
        return JsonResponse({'resultados': [], 'limitado': False})
    qs = _base(request.user).filter(empresa_id=int(p['empresa']))
    # Al editar, los folios que ya son de la factura siempre salen (aunque sean viejos).
    propios = []
    if str(p.get('factura', '')).isdigit():
        propios = list(qs.filter(factura_registro_id=int(p['factura'])))
    qs = qs.filter(_sin_factura_q())
    q = _mayusculas(p.get('q'), 100)
    if q:
        qs = qs.filter(Q(remision__icontains=q) | Q(cliente__nombre__icontains=q) | Q(destino__nombre__icontains=q))
    desde, hasta = _numero_folio(p.get('folio_desde')), _numero_folio(p.get('folio_hasta'))
    filas = list(propios)
    for r in qs.order_by('-fecha', '-pk'):
        n = _numero_folio(r.remision)
        if (desde is not None or hasta is not None) and n is None:
            continue
        if desde is not None and n < desde or hasta is not None and n > hasta:
            continue
        filas.append(r)
        if len(filas) >= MAX_DISPONIBLES:
            break
    kg = _kg_por_remision([r.pk for r in filas])
    resultado = sorted((_folio_dict(r, kg) for r in filas), key=lambda x: (_numero_folio(x['remision']) or 0, x['remision']))
    return JsonResponse({'resultados': resultado, 'limitado': len(filas) >= MAX_DISPONIBLES})


@login_required
def pagina(request):
    """Versión HTML (Django) del módulo; usa las mismas APIs."""
    if not puede_usar(request.user):
        return render(request, 'ternium/asignacion_factura.html', {'sin_permiso': True}, status=403)
    return render(request, 'ternium/asignacion_factura.html', {'sin_permiso': False})
