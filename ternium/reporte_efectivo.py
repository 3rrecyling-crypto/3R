"""
Excel de efectivo (Asignación de factura › Efectivo › "Descargar Excel").

Dos hojas (abre en el Resumen):
- Resumen: una fila por operación en efectivo con su folio de captura (3R-E-001), fecha, unidad de
  negocio, cliente, remisiones, kg descargados, monto calculado, monto cobrado (y si se corrigió a
  mano), moneda, tipo de cambio y el monto en pesos.
- Detalle: una fila por material de cada remisión: kg descargados × precio por kg = importe. Es una
  tabla de Excel con filtros y un renglón de totales que respeta lo filtrado.

Salen las operaciones de la lista con sus mismos filtros (?q&empresa&cliente&desde&hasta), o una sola
(?efectivo=<id>).
"""
import io
import re
from decimal import ROUND_HALF_UP, Decimal

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import asignacion_factura as af
from .efectivo_remisiones import _efectivos, _en_pesos, _filtrar, _orden_folio
from .models import EfectivoRemision, Remision

MAX_OPERACIONES = 2000
DINERO = '"$"#,##0.00;[Red]-"$"#,##0.00'

# título, ancho, formato
RESUMEN = [
    ('Captura', 12, 'texto'), ('Fecha', 12, 'fecha'), ('Unidad de negocio', 20, 'texto'), ('Cliente', 30, 'largo'),
    ('Remisiones', 34, 'largo'), ('Núm. de remisiones', 12, 'entero'), ('Kg descargados', 15, 'kg'),
    ('Moneda', 9, 'texto'), ('Monto calculado', 16, 'dinero'), ('Monto cobrado', 16, 'dinero'),
    ('Corregido a mano', 11, 'texto'), ('Tipo de cambio', 12, 'precio'), ('Monto en pesos', 16, 'dinero'),
    ('Notas', 34, 'largo'), ('Registró', 22, 'texto'), ('Registrado el', 17, 'fechahora'),
]
DETALLE = [
    ('Captura', 12, 'texto'), ('Fecha', 12, 'fecha'), ('Unidad de negocio', 20, 'texto'), ('Remisión', 13, 'texto'),
    ('Folio de descarga', 15, 'texto'), ('Cliente', 28, 'largo'), ('Material', 26, 'largo'),
    ('Kg descargados', 15, 'kg'), ('Precio por kg', 13, 'precio'), ('Importe', 15, 'dinero'), ('Moneda', 9, 'texto'),
    ('Tipo de cambio', 12, 'precio'), ('Importe en pesos', 16, 'dinero'),
]


def _num(valor):
    return float(valor) if valor is not None else None


def datos_efectivo(e):
    """La operación con sus remisiones (no canceladas) y un renglón por material de cada una."""
    remisiones = sorted(Remision.objects.filter(efectivo_registro=e).exclude(status='CANCELADO')
                        .select_related('cliente', 'destino'), key=lambda r: _orden_folio(r.remision))
    por_remision = {}
    for li in e.lineas.all():
        por_remision.setdefault(li.remision_id, []).append(li)
    cambio = e.tipo_cambio if e.moneda == 'USD' else Decimal(1)
    filas = []
    for r in remisiones:
        cliente = (r.cliente.nombre if r.cliente_id else '') or (r.destino.nombre if r.destino_id else '')
        base = [e.numero_captura, e.fecha, e.empresa.nombre, r.remision, r.folio_dlv or '', cliente]
        lineas = sorted(por_remision.get(r.pk, []), key=lambda li: li.pk)
        if not lineas:  # remisión sin materiales capturados: sale igual, sin importe
            filas.append(base + ['(sin materiales)', None, None, None, e.moneda, _num(cambio) if e.moneda == 'USD' else None, None])
        for li in lineas:
            en_pesos = (li.importe * cambio).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if li.importe is not None else None
            filas.append(base + [li.material_nombre, _num(li.kg), _num(li.precio), _num(li.importe), e.moneda,
                                 _num(cambio) if e.moneda == 'USD' else None, _num(en_pesos)])
    kilos = sum((li.kg or 0 for r in remisiones for li in por_remision.get(r.pk, [])), Decimal(0))
    resumen = [
        e.numero_captura, e.fecha, e.empresa.nombre, e.cliente, ', '.join(r.remision for r in remisiones), len(remisiones),
        _num(kilos), e.moneda, _num(e.monto_calculado), _num(e.monto), 'Sí' if e.monto_ajustado else 'No',
        _num(e.tipo_cambio) if e.moneda == 'USD' else None, _num(_en_pesos(e)), e.notas, af._nombre(e.creado_por),
        timezone.localtime(e.creado_en).replace(tzinfo=None, microsecond=0),
    ]
    return {'efectivo': e, 'resumen': resumen, 'filas': filas}


def construir(datos, subtitulo):
    """Bytes del Excel (hojas Resumen y Detalle)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L
    from openpyxl.worksheet.table import Table, TableStyleInfo

    centro = Alignment(horizontal='center', vertical='center', wrap_text=True)
    izquierda = Alignment(horizontal='left', vertical='center', wrap_text=True)
    derecha = Alignment(horizontal='right', vertical='center')
    oscuro, tinta = PatternFill('solid', fgColor='0B1730'), Font(bold=True, color='FFFFFF')
    violeta = PatternFill('solid', fgColor='6D28D9')
    formatos = {'dinero': DINERO, 'precio': '"$"#,##0.00##', 'kg': '#,##0.###', 'entero': '#,##0',
                'fecha': 'dd/mm/yyyy', 'fechahora': 'dd/mm/yyyy hh:mm'}

    def hoja(ws, titulo, columnas, filas, nombre_tabla):
        ws.sheet_view.showGridLines = False
        n = len(columnas)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
        ws.cell(row=1, column=1, value=titulo).font = Font(bold=True, size=14, color='FFFFFF')
        ws.cell(row=1, column=1).fill, ws.cell(row=1, column=1).alignment = oscuro, centro
        ws.row_dimensions[1].height = 28
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
        ws.cell(row=2, column=1, value=subtitulo).font = Font(italic=True, size=10, color='475569')
        ws.cell(row=2, column=1).alignment = centro
        enc = 4
        for i, (texto, ancho, _) in enumerate(columnas, 1):
            celda = ws.cell(row=enc, column=i, value=texto)
            celda.font, celda.fill, celda.alignment = tinta, violeta, centro
            ws.column_dimensions[L(i)].width = ancho
        ws.row_dimensions[enc].height = 32
        for f, valores in enumerate(filas, enc + 1):
            for i, ((_, _, tipo), valor) in enumerate(zip(columnas, valores), 1):
                celda = ws.cell(row=f, column=i, value=valor if valor != '' else None)
                if tipo in formatos:
                    celda.number_format = formatos[tipo]
                celda.alignment = izquierda if tipo == 'largo' else centro
        ultima = enc + len(filas)
        tabla = Table(displayName=nombre_tabla, ref=f'A{enc}:{L(n)}{max(ultima, enc + 1)}')
        tabla.tableStyleInfo = TableStyleInfo(name='TableStyleMedium12', showRowStripes=True)
        ws.add_table(tabla)
        ws.freeze_panes = f'B{enc + 1}'
        ws.print_title_rows = f'{enc}:{enc}'
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        return enc, ultima

    def total(ws, fila, col, texto, formula, formato):
        """Etiqueta a la izquierda de la celda y la fórmula del total (SUBTOTAL respeta los filtros)."""
        ws.cell(row=fila, column=col - 1, value=texto).font = Font(bold=True)
        ws.cell(row=fila, column=col - 1).alignment = derecha
        celda = ws.cell(row=fila, column=col, value=formula)
        celda.number_format, celda.font, celda.alignment = formato, Font(bold=True), centro
        celda.border = Border(top=Side(style='medium', color='0B1730'))

    wb = Workbook()
    rs = wb.active
    rs.title = 'Resumen'
    enc, ultima = hoja(rs, 'Efectivo (sin factura) · 3R Recycling', RESUMEN, [d['resumen'] for d in datos], 'ResumenEfectivo')
    titulos = [t for t, _, _ in RESUMEN]
    col = lambda nombre: titulos.index(nombre) + 1  # noqa: E731
    rango = lambda nombre: f'{L(col(nombre))}{enc + 1}:{L(col(nombre))}{ultima}'  # noqa: E731
    # Lo cobrado, todo en pesos (los dólares a su tipo de cambio), y aparte por moneda
    fila_t = ultima + 1
    total(rs, fila_t, col('Monto en pesos'), 'Total en pesos', f'=SUBTOTAL(109,{rango("Monto en pesos")})', DINERO)
    kg_col = col('Kg descargados')
    celda = rs.cell(row=fila_t, column=kg_col, value=f'=SUBTOTAL(109,{rango("Kg descargados")})')
    celda.number_format, celda.font, celda.alignment = '#,##0.###', Font(bold=True), centro
    celda.border = Border(top=Side(style='medium', color='0B1730'))
    monedas = sorted({d['efectivo'].moneda for d in datos})
    if len(monedas) > 1:
        for n, moneda in enumerate(monedas, 1):
            total(rs, fila_t + n, col('Monto cobrado'), f'Cobrado en {moneda}',
                  f'=SUMIFS({rango("Monto cobrado")},{rango("Moneda")},"{moneda}")', DINERO)
            rs.cell(row=fila_t + n, column=col('Monto cobrado')).border = Border()

    ws = wb.create_sheet('Detalle')
    filas = [f for d in datos for f in d['filas']]
    enc_d, ultima_d = hoja(ws, 'Efectivo: precio por material · 3R Recycling', DETALLE, filas, 'DetalleEfectivo')
    titulos_d = [t for t, _, _ in DETALLE]
    if filas:
        for nombre, formato in (('Kg descargados', '#,##0.###'), ('Importe en pesos', DINERO)):
            c = titulos_d.index(nombre) + 1
            celda = ws.cell(row=ultima_d + 1, column=c, value=f'=SUBTOTAL(109,{L(c)}{enc_d + 1}:{L(c)}{ultima_d})')
            celda.number_format, celda.font, celda.alignment = formato, Font(bold=True), centro
            celda.border = Border(top=Side(style='medium', color='0B1730'))
        etiqueta = ws.cell(row=ultima_d + 1, column=titulos_d.index('Kg descargados'), value='Total de lo filtrado')
        etiqueta.font, etiqueta.alignment = Font(bold=True), derecha

    wb.active = 0
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


@require_http_methods(['GET'])
@af._api
def api_reporte(request):
    """GET ?q&empresa&cliente&desde&hasta (los filtros de la lista) o ?efectivo=<id> → Excel de efectivo."""
    p = request.GET
    qs = _efectivos(request.user)
    if str(p.get('efectivo', '')).isdigit():
        qs = qs.filter(pk=int(p['efectivo']))
    else:
        # Sobre los pk: la búsqueda cruza con las remisiones y repetiría la operación
        qs = EfectivoRemision.objects.filter(pk__in=_filtrar(qs, p).values('pk')).select_related(
            'empresa', 'creado_por').prefetch_related('lineas')
    qs = qs.order_by('fecha', 'captura')
    cuantas = qs.count()
    if not cuantas:
        return JsonResponse({'detail': 'No hay operaciones en efectivo con esos filtros.'}, status=404)
    if cuantas > MAX_OPERACIONES:
        return JsonResponse({'detail': f'Son {cuantas:,} operaciones: acota por fechas o unidad de negocio '
                                       f'(máximo {MAX_OPERACIONES:,}).'}, status=400)
    datos = [datos_efectivo(e) for e in qs]

    filtros = []
    if p.get('desde') or p.get('hasta'):
        filtros.append(f'del {p.get("desde") or "inicio"} al {p.get("hasta") or "hoy"}')
    if p.get('q'):
        filtros.append(f'búsqueda "{p["q"]}"')
    if str(p.get('empresa', '')).isdigit():
        filtros.append(datos[0]['efectivo'].empresa.nombre)
    if (p.get('cliente') or '').strip():
        filtros.append(f'cliente {p["cliente"].strip()}')
    subtitulo = (f'{cuantas} operación(es) en efectivo' + (' · ' + ' · '.join(filtros) if filtros else '')
                 + f' · generado el {timezone.localtime():%d/%m/%Y %H:%M}')
    contenido = construir(datos, subtitulo)
    if cuantas == 1 and str(p.get('efectivo', '')).isdigit():
        nombre = 'Efectivo ' + re.sub(r'[^A-Za-z0-9_-]', '_', datos[0]['efectivo'].numero_captura)
    else:
        nombre = f'Efectivo {timezone.localdate():%Y-%m-%d}'
    respuesta = HttpResponse(contenido, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}.xlsx"'
    return respuesta
