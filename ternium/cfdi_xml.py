"""
Lectura de un CFDI (XML del SAT, versión 3.3 o 4.0) para "Asignación de factura".

Saca todo lo que trae la factura: serie, folio, UUID, fechas, emisor, receptor,
uso de CFDI, forma y método de pago, subtotal, descuento, impuestos trasladados
(IVA, IEPS) y retenidos (IVA, ISR), total y conceptos. También detecta los folios
de remisión que vengan escritos en los conceptos (p. ej. "REMISION FOLIO APO26329").

El XML lo sube el usuario: se lee con un parser endurecido (sin DTD, sin
entidades externas, sin red) y se rechaza cualquier <!DOCTYPE>.
"""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.utils.dateparse import parse_datetime

MAX_BYTES = 5 * 1024 * 1024
IMPUESTOS = {'001': 'ISR', '002': 'IVA', '003': 'IEPS'}
# "REMISION FOLIO APO26329", "FOLIO: MTY-1787", "REMISIÓN MTY-1787", "REM. 1787"
_FOLIO_RE = re.compile(
    r'(?:\bFOLIOS?\b|\bREMISI[OÓ]N(?:ES)?\b|\bREM\.)\s*(?:DE\s+)?(?:FOLIO\s*)?[:#No.\s]*([A-Z0-9][A-Z0-9-]{2,})',
    re.IGNORECASE)
# Folios sueltos con forma de remisión: "APO26329", "MTY-1787" (letras + número)
_FOLIO_SUELTO_RE = re.compile(r'\b([A-Z]{2,6}-?\d{3,})\b', re.IGNORECASE)


class ErrorCFDI(Exception):
    pass


def _dec(valor, defecto='0'):
    try:
        return Decimal(str(valor if valor not in (None, '') else defecto))
    except (InvalidOperation, ValueError):
        return Decimal(defecto)


def _d2(n):
    return n.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _local(etiqueta):
    return etiqueta.rsplit('}', 1)[-1] if isinstance(etiqueta, str) else ''


def _hijo(nodo, nombre):
    if nodo is None:
        return None
    return next((h for h in nodo if _local(h.tag) == nombre), None)


def _hijos(nodo, nombre):
    return [h for h in (nodo if nodo is not None else []) if _local(h.tag) == nombre]


def _impuestos(nodo):
    """Traslados y retenciones de un nodo <Impuestos> (del comprobante o de un concepto)."""
    imp = _hijo(nodo, 'Impuestos')
    traslados = [{
        'impuesto': t.get('Impuesto', ''), 'nombre': IMPUESTOS.get(t.get('Impuesto', ''), t.get('Impuesto', '')),
        'tipo_factor': t.get('TipoFactor', ''), 'tasa': _dec(t.get('TasaOCuota')), 'base': _dec(t.get('Base')),
        'importe': _dec(t.get('Importe')),
    } for t in _hijos(_hijo(imp, 'Traslados'), 'Traslado')]
    retenciones = [{
        'impuesto': r.get('Impuesto', ''), 'nombre': IMPUESTOS.get(r.get('Impuesto', ''), r.get('Impuesto', '')),
        'tasa': _dec(r.get('TasaOCuota')), 'base': _dec(r.get('Base')), 'importe': _dec(r.get('Importe')),
    } for r in _hijos(_hijo(imp, 'Retenciones'), 'Retencion')]
    return imp, traslados, retenciones


def folios_en_texto(texto):
    """Folios de remisión escritos en un texto, en mayúsculas y sin repetir: los que van
    después de "FOLIO"/"REMISIÓN" y los sueltos con forma de folio (APO26329). Son
    candidatos: solo se ligan los que existen como remisión."""
    vistos = []
    encontrados = [m.group(1) for m in _FOLIO_RE.finditer(texto or '')]
    encontrados += [m.group(1) for m in _FOLIO_SUELTO_RE.finditer(texto or '')]
    for folio in encontrados:
        folio = folio.upper().strip('-')
        if any(ch.isdigit() for ch in folio) and folio not in vistos:
            vistos.append(folio)
    return vistos


def leer_cfdi(contenido):
    """dict con los datos del CFDI. Lanza ErrorCFDI si no es un CFDI válido."""
    from lxml import etree

    if not contenido:
        raise ErrorCFDI('El archivo está vacío.')
    if len(contenido) > MAX_BYTES:
        raise ErrorCFDI('El XML es demasiado grande (máximo 5 MB).')
    if b'<!DOCTYPE' in contenido[:4096].upper() or b'<!ENTITY' in contenido.upper():
        raise ErrorCFDI('El XML no es un CFDI válido.')
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, remove_comments=True)
    try:
        raiz = etree.fromstring(contenido, parser=parser)
    except etree.XMLSyntaxError:
        raise ErrorCFDI('No se pudo leer el XML (no es un archivo XML válido).')
    if _local(raiz.tag) != 'Comprobante':
        raise ErrorCFDI('El XML no es un CFDI (no tiene <cfdi:Comprobante>).')

    g = raiz.get
    emisor, receptor = _hijo(raiz, 'Emisor'), _hijo(raiz, 'Receptor')
    _, traslados, retenciones = _impuestos(raiz)
    timbre = next((n for n in raiz.iter() if _local(n.tag) == 'TimbreFiscalDigital'), None)

    def de(lista, clave):
        """(tasa en %, importe) de un impuesto en una lista de traslados o retenciones."""
        items = [x for x in lista if x['impuesto'] == clave]
        tasas = [x['tasa'] for x in items if x.get('tipo_factor', 'Tasa') == 'Tasa' and x['tasa']]
        tasa = (max(tasas) * 100).quantize(Decimal('0.0001')) if tasas else Decimal(0)
        return float(tasa), float(_d2(sum((x['importe'] for x in items), Decimal(0))))

    conceptos = []
    for c in _hijos(_hijo(raiz, 'Conceptos'), 'Concepto'):
        _, c_tras, c_ret = _impuestos(c)
        importe, desc = _d2(_dec(c.get('Importe'))), _d2(_dec(c.get('Descuento')))
        c_trasladado = _d2(sum((t['importe'] for t in c_tras), Decimal(0)))
        c_retenido = _d2(sum((r['importe'] for r in c_ret), Decimal(0)))
        (iva_t, iva), (ieps_t, ieps) = de(c_tras, '002'), de(c_tras, '003')
        (riva_t, riva), (risr_t, risr) = de(c_ret, '002'), de(c_ret, '001')
        conceptos.append({
            'clave_prod_serv': c.get('ClaveProdServ', ''), 'no_identificacion': (c.get('NoIdentificacion') or '').strip(),
            'cantidad': float(_dec(c.get('Cantidad'))), 'clave_unidad': c.get('ClaveUnidad', ''), 'unidad': c.get('Unidad', ''),
            'descripcion': ' '.join((c.get('Descripcion') or '').split()), 'valor_unitario': float(_dec(c.get('ValorUnitario'))),
            'importe': float(importe), 'descuento': float(desc),
            'traslados': float(c_trasladado), 'retenciones': float(c_retenido),
            # Desglose por impuesto (tasa en %)
            'iva_tasa': iva_t, 'iva': iva, 'ieps_tasa': ieps_t, 'ieps': ieps,
            'ret_iva_tasa': riva_t, 'ret_iva': riva, 'ret_isr_tasa': risr_t, 'ret_isr': risr,
            'total': float(importe - desc + c_trasladado - c_retenido),
            'folios': folios_en_texto(c.get('Descripcion')),
        })

    subtotal, descuento = _d2(_dec(g('SubTotal'))), _d2(_dec(g('Descuento')))
    base = subtotal - descuento

    def suma(lista, clave):
        return _d2(sum((x['importe'] for x in lista if x['impuesto'] == clave), Decimal(0)))

    def tasa_traslado(clave):
        tasas = [x['tasa'] for x in traslados if x['impuesto'] == clave and x['tipo_factor'] == 'Tasa']
        return (max(tasas) * 100).quantize(Decimal('0.0001')) if tasas else Decimal(0)

    def tasa_retencion(clave, importe):
        # Las retenciones globales no traen tasa: la de los conceptos, o importe / base
        de_conceptos = [r['tasa'] for c in _hijos(_hijo(raiz, 'Conceptos'), 'Concepto')
                        for r in _impuestos(c)[2] if r['impuesto'] == clave and r['tasa']]
        if de_conceptos:
            return (max(de_conceptos) * 100).quantize(Decimal('0.0001'))
        return (importe / base * 100).quantize(Decimal('0.0001')) if importe and base else Decimal(0)

    iva, ieps = suma(traslados, '002'), suma(traslados, '003')
    ret_iva, ret_isr = suma(retenciones, '002'), suma(retenciones, '001')
    total = _d2(_dec(g('Total')))
    serie, folio = (g('Serie') or '').strip(), (g('Folio') or '').strip()
    uuid = (timbre.get('UUID') if timbre is not None else '') or ''
    fecha = parse_datetime(g('Fecha') or '')
    folios = []
    for c in conceptos:
        folios += [f for f in c['folios'] if f not in folios]
    return {
        'version': g('Version', ''), 'serie': serie, 'folio': folio,
        'numero_sugerido': (f'{serie}{folio}' or uuid[:8]).upper(),
        'uuid': uuid.upper(), 'fecha': fecha.date().isoformat() if fecha else None,
        'fecha_emision': fecha.isoformat() if fecha else None,  # con hora, como viene en el XML
        'fecha_timbrado': timbre.get('FechaTimbrado') if timbre is not None else None,
        'tipo_comprobante': g('TipoDeComprobante', ''), 'forma_pago': g('FormaPago', ''), 'metodo_pago': g('MetodoPago', ''),
        'moneda': g('Moneda', 'MXN'), 'tipo_cambio': float(_dec(g('TipoCambio'), '1')), 'lugar_expedicion': g('LugarExpedicion', ''),
        'emisor': {'rfc': emisor.get('Rfc', '') if emisor is not None else '', 'nombre': emisor.get('Nombre', '') if emisor is not None else '',
                   'regimen': emisor.get('RegimenFiscal', '') if emisor is not None else ''},
        'receptor': {'rfc': receptor.get('Rfc', '') if receptor is not None else '',
                     'nombre': receptor.get('Nombre', '') if receptor is not None else '',
                     'uso_cfdi': receptor.get('UsoCFDI', '') if receptor is not None else ''},
        'subtotal': float(subtotal), 'descuento': float(descuento),
        'iva_tasa': float(tasa_traslado('002')), 'iva_importe': float(iva),
        'ieps_tasa': float(tasa_traslado('003')), 'ieps_importe': float(ieps),
        'ret_iva_tasa': float(tasa_retencion('002', ret_iva)), 'ret_iva_importe': float(ret_iva),
        'ret_isr_tasa': float(tasa_retencion('001', ret_isr)), 'ret_isr_importe': float(ret_isr),
        'total_trasladados': float(_d2(_dec(_hijo(raiz, 'Impuestos').get('TotalImpuestosTrasladados') if _hijo(raiz, 'Impuestos') is not None else 0))),
        'total_retenidos': float(_d2(_dec(_hijo(raiz, 'Impuestos').get('TotalImpuestosRetenidos') if _hijo(raiz, 'Impuestos') is not None else 0))),
        'total': float(total),
        'conceptos': conceptos, 'folios_detectados': folios,
    }
