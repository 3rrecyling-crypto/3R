"""
Excel semanal de cargas (Next: /diesel/cargas, botón "Excel semanal").

Mismo formato que el archivo del ingeniero ("S43-26"): una hoja por semana con la tabla de cargas
(FECHA, REGISTRO, OPERACIÓN, CLIENTE/PROVEEDOR, QUIEN CARGA, # DE UNIDAD, OPERADOR, CANTIDAD DIESEL,
KILOMETRAJE, SUMA DIESEL, RESTA DIESEL, Tabla Dinamica, MONTO, ESTATUS) y a un lado la tabla dinámica
por cliente › fecha › unidad con la suma de litros y de monto, filtrable por ESTATUS.
Cada carga es una venta: 3R RECYCLING va como "3R", los thermos como "TERMO <identificador>" y el
monto es litros × precio por litro de la carga (el mismo costo de Control Diésel).
Usa los filtros del listado (patio, permisionario, unidad, auditoría) en la semana elegida.
"""
import datetime as dt
import io
import zipfile

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .excel_cargas import MAX_FILAS
from .models import es_3r_nombre
from .views import filtrar_cargas

APTOS, ARIAL = 'Aptos Narrow', 'Arial'
DINERO = '"$"#,##0.00'
CONTABLE = '_-"$"* #,##0.00_-;\\-"$"* #,##0.00_-;_-"$"* "-"??_-;_-@'
AZUL = '104861'
# (título, ancho, fuente, alineación, formato), como en el archivo del ingeniero (FECHA, Tabla Dinamica y
# MONTO un poco más anchos para que no salgan "####" si la computadora no tiene la fuente Aptos Narrow)
COLUMNAS = [
    ('FECHA', 11.5, APTOS, None, 'mm-dd-yy'), ('REGISTRO', 20.125, ARIAL, None, None),
    ('OPERACIÓN', 13, ARIAL, 'center', None), ('CLIENTE/PROVEEDOR', 20.625, APTOS, 'center', None),
    ('QUIEN CARGA', 14.5, ARIAL, 'center', None), ('# DE UNIDAD', 21.5, ARIAL, 'center', None),
    ('OPERADOR', 23.625, ARIAL, 'center', None), ('CANTIDAD DIESEL', 17.625, ARIAL, 'center', CONTABLE),
    ('KILOMETRAJE', 14, ARIAL, 'center', '0.00'), ('SUMA DIESEL', 13.875, ARIAL, 'center', None),
    ('RESTA DIESEL', 14.375, ARIAL, 'center', None), ('Tabla Dinamica', 15, APTOS, 'center', None),
    ('MONTO', 14, APTOS, 'left', DINERO), ('ESTATUS', 17.375, APTOS, 'left', None),
]
FECHA, CLIENTE, UNIDAD, SUMA, MONTO, ESTATUS = 0, 3, 5, 9, 12, 13  # columnas que usa la tabla dinámica
# Excel 2010+ no muestra el renglón "Valores" arriba de los encabezados de la tabla dinámica.
SIN_RENGLON_VALORES = (
    '<extLst><ext uri="{962EF5D1-5CA2-4c93-8EF4-DBF5C05439D2}" '
    'xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">'
    '<x14:pivotTableDefinition hideValuesRow="1" '
    'xmlns:xm="http://schemas.microsoft.com/office/excel/2006/main"/></ext></extLst>'
)


def semana_de(texto):
    """Lunes de la semana ISO '2026-W43' (la del <input type="week">); la actual si no viene o no se entiende."""
    try:
        anio, semana = (texto or '').split('-W')
        return dt.date.fromisocalendar(int(anio), int(semana), 1)
    except ValueError:
        hoy = timezone.localdate()
        return hoy - dt.timedelta(days=hoy.weekday())


def _equipo(c):
    if c.tipo_carga != 'thermo':
        return c.equipo or 'SIN UNIDAD'
    nombre = (c.equipo or '').upper()
    return nombre if nombre.startswith(('TERMO', 'THERMO')) else f'TERMO {nombre}'.strip()


def _fila(c, semana):
    """Los 14 valores de la carga en el orden de COLUMNAS (MONTO va aparte: es fórmula)."""
    litros = float(c.litros_diesel + c.litros_thermo)
    cliente = '3R' if es_3r_nombre(c.permisionario_nombre) else (c.permisionario_nombre or 'SIN PERMISIONARIO').upper()
    quien = (c.usuario.first_name or c.usuario.get_full_name() or c.usuario.username).strip().upper()
    km = float(c.odometro) if c.odometro is not None and c.tipo_carga != 'thermo' else None
    return [timezone.localtime(c.fecha_carga).date(), None, 'VENTA', cliente, quien or None, _equipo(c),
            (c.operador_nombre or '').strip().upper() or None, None, km, litros, -litros, semana,
            litros * float(c.precio_litro), None]


def _compartidos(valores):
    """sharedItems del caché de una columna que no va en filas: los tipos que trae (lo que espera Excel)."""
    from openpyxl.pivot.cache import SharedItems

    hay = [v for v in valores if v is not None]
    vacios = len(hay) < len(valores)
    if not hay:
        return SharedItems(containsNonDate=False, containsString=False, containsBlank=True)
    if all(isinstance(v, (int, float)) for v in hay):
        enteros = all(float(v).is_integer() for v in hay)
        return SharedItems(containsSemiMixedTypes=False if not vacios else None, containsString=False,
                           containsBlank=vacios or None, containsNumber=True, containsInteger=enteros or None,
                           minValue=min(hay), maxValue=max(hay))
    return SharedItems(containsBlank=vacios or None)


def _tabla_dinamica(wb, ws, tabla, filas, semana):
    """Tabla dinámica como la del ingeniero en S5 (filtro ESTATUS en S3): filas cliente › fecha › unidad,
    valores Suma de SUMA DIESEL y Suma de MONTO. Se guarda con su caché completo y las celdas ya
    llenas, así que se ve igual antes de actualizarla. Devuelve el rango que ocupa."""
    from openpyxl.pivot.cache import CacheDefinition, CacheField, CacheSource, SharedItems, WorksheetSource
    from openpyxl.pivot.fields import DateTimeField, Index, Missing, Number, Text
    from openpyxl.pivot.record import Record, RecordList
    from openpyxl.pivot.table import (DataField, FieldItem, Location, PageField, PivotField, PivotTableStyle,
                                      RowColField, RowColItem, TableDefinition)
    from openpyxl.styles import Alignment
    from openpyxl.styles.numbers import BUILTIN_FORMATS_MAX_SIZE

    id_dinero = BUILTIN_FORMATS_MAX_SIZE + wb._number_formats.index(DINERO)
    # Los campos que van en filas usan índices a sus valores (en el orden en que se muestran).
    orden = {FECHA: sorted({f[FECHA] for f in filas}),
             CLIENTE: sorted({f[CLIENTE] for f in filas}, key=str.upper),
             UNIDAD: sorted({f[UNIDAD] for f in filas}, key=str.upper)}
    indice = {col: {v: i for i, v in enumerate(vals)} for col, vals in orden.items()}

    campos = []
    for col, (titulo, *_resto) in enumerate(COLUMNAS):
        if col == FECHA:
            dias = [dt.datetime.combine(d, dt.time()) for d in orden[FECHA]]
            compartidos = SharedItems(
                _fields=[DateTimeField(v=d) for d in dias], count=len(dias), containsSemiMixedTypes=False,
                containsNonDate=False, containsDate=True, containsString=False,
                minDate=dias[0], maxDate=dias[-1] + dt.timedelta(days=1))  # Excel guarda el día siguiente
        elif col in orden:
            compartidos = SharedItems(_fields=[Text(v=v) for v in orden[col]], count=len(orden[col]))
        elif col == ESTATUS:
            compartidos = SharedItems(_fields=[Missing()], count=1, containsNonDate=False, containsString=False, containsBlank=True)
        else:
            compartidos = _compartidos([f[col] for f in filas])
        formato = 14 if col == FECHA else id_dinero if col == MONTO else 0
        campos.append(CacheField(name=titulo, numFmtId=formato, sharedItems=compartidos))

    registros = []
    for f in filas:
        valores = []
        for col, v in enumerate(f):
            if col in indice:
                valores.append(Index(v=indice[col][v]))
            elif col == ESTATUS:
                valores.append(Index(v=0))
            elif v is None:
                valores.append(Missing())
            elif isinstance(v, str):
                valores.append(Text(v=v))
            else:
                valores.append(Number(v=v))
        registros.append(Record(_fields=valores))
    cache = CacheDefinition(
        cacheSource=CacheSource(type='worksheet', worksheetSource=WorksheetSource(name=tabla)),
        cacheFields=campos, recordCount=len(filas), refreshOnLoad=True,
        createdVersion=8, refreshedVersion=8, minRefreshableVersion=3)
    cache.records = RecordList(r=registros)

    def items(col):
        return [FieldItem(x=i) for i in range(len(orden[col]))] + [FieldItem(t='default')]

    campos_tabla = []
    for col in range(len(COLUMNAS)):
        if col in orden:
            campo = PivotField(axis='axisRow', showAll=False, items=items(col), numFmtId=14 if col == FECHA else None)
        elif col == ESTATUS:
            campo = PivotField(axis='axisPage', multipleItemSelectionAllowed=True, showAll=False,
                               items=[FieldItem(x=0), FieldItem(t='default')])
        elif col in (SUMA, MONTO):
            campo = PivotField(dataField=True, showAll=False, numFmtId=id_dinero if col == MONTO else None)
        else:
            campo = PivotField(showAll=False)
        campos_tabla.append(campo)

    # Renglones: cada cliente con su total, sus fechas y en cada fecha sus unidades; al final el total general.
    arbol = {}
    for f in filas:
        nodo = arbol.setdefault(f[CLIENTE], {}).setdefault(f[FECHA], {}).setdefault(f[UNIDAD], [0.0, 0.0])
        nodo[0] += f[SUMA]
        nodo[1] += f[MONTO]

    def suma(nodo):
        if isinstance(nodo, list):
            return nodo
        partes = [suma(n) for n in nodo.values()]
        return [sum(p[0] for p in partes), sum(p[1] for p in partes)]

    renglones = []  # (nivel, columna, valor, litros, monto)
    for cliente in orden[CLIENTE]:
        if cliente not in arbol:
            continue
        renglones.append((0, CLIENTE, cliente, *suma(arbol[cliente])))
        for fecha in sorted(arbol[cliente]):
            renglones.append((1, FECHA, fecha, *suma(arbol[cliente][fecha])))
            for unidad in sorted(arbol[cliente][fecha], key=indice[UNIDAD].get):
                renglones.append((2, UNIDAD, unidad, *arbol[cliente][fecha][unidad]))
    total = suma(arbol)
    fila_items = [RowColItem(r=nivel, x=[Index(v=indice[col][valor])]) for nivel, col, valor, _, _ in renglones]
    fila_items.append(RowColItem(t='grand', x=[Index(v=0)]))

    arriba = 5
    abajo = arriba + len(renglones) + 1
    pivote = TableDefinition(
        name=f'TablaDinamica{tabla[5:]}', cacheId=1, dataCaption='Valores', updatedVersion=8, minRefreshableVersion=3,
        createdVersion=8, useAutoFormatting=True, itemPrintTitles=True, indent=0, outline=True, outlineData=True,
        multipleFieldFilters=False, applyNumberFormats=False, applyBorderFormats=False, applyFontFormats=False,
        applyPatternFormats=False, applyAlignmentFormats=False, applyWidthHeightFormats=True,
        location=Location(ref=f'S{arriba}:U{abajo}', firstHeaderRow=0, firstDataRow=1, firstDataCol=1,
                          rowPageCount=1, colPageCount=1),
        pivotFields=campos_tabla, rowFields=[RowColField(x=CLIENTE), RowColField(x=FECHA), RowColField(x=UNIDAD)],
        rowItems=fila_items, colFields=[RowColField(x=-2)],
        colItems=[RowColItem(x=[Index(v=0)]), RowColItem(i=1, x=[Index(v=1)])],
        pageFields=[PageField(fld=ESTATUS, hier=-1)],
        dataFields=[DataField(name='Suma de SUMA DIESEL', fld=SUMA, baseField=0, baseItem=0),
                    DataField(name='Suma de MONTO', fld=MONTO, baseField=0, baseItem=0, numFmtId=id_dinero)],
        pivotTableStyleInfo=PivotTableStyle(name='PivotStyleLight16', showRowHeaders=True, showColHeaders=True,
                                            showRowStripes=False, showColStripes=False, showLastColumn=True))
    pivote.cache = cache
    ws.add_pivot(pivote)

    # Lo que muestra la tabla dinámica (Excel la vuelve a llenar al actualizarla)
    ws['S2'] = f'SEMANA {semana}'
    ws['S3'], ws['T3'] = 'ESTATUS', '(en blanco)'
    ws['S5'], ws['T5'], ws['U5'] = 'Etiquetas de fila', 'Suma de SUMA DIESEL', 'Suma de MONTO'
    for r, (nivel, col, valor, litros, monto) in enumerate([*renglones, (0, None, 'Total general', *total)], arriba + 1):
        etiqueta = ws.cell(row=r, column=19, value=valor)
        etiqueta.alignment = Alignment(horizontal='left', indent=nivel)
        if col == FECHA:
            etiqueta.number_format = 'mm-dd-yy'
        ws.cell(row=r, column=20, value=litros)
        ws.cell(row=r, column=21, value=monto).number_format = DINERO
    for letra, ancho in (('S', 15.625), ('T', 18.75), ('U', 14)):
        ws.column_dimensions[letra].width = ancho


class CargasSemanaExcelAPIView(APIView):
    """GET ?semana=2026-W43 y los filtros del listado (?patio, ?unidad, ?permisionario, ?auditoria):
    descarga el .xlsx de la semana en el formato del ingeniero."""

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.has_perm('ternium.acceso_diesel')):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter as L
        from openpyxl.worksheet.table import Table, TableStyleInfo

        lunes = semana_de(request.query_params.get('semana'))
        anio, semana, _ = lunes.isocalendar()
        filtros = request.query_params.dict()
        filtros.update(fecha_inicio=lunes.isoformat(), fecha_fin=(lunes + dt.timedelta(days=6)).isoformat())
        cargas = filtrar_cargas(user, filtros).order_by('fecha_carga', 'pk')[:MAX_FILAS]
        filas = [_fila(c, semana) for c in cargas]
        precios = [float(c.precio_litro) for c in cargas]

        clave = f'{semana:02d}{anio % 100:02d}'
        wb = Workbook()
        ws = wb.active
        ws.title = f'S{semana:02d}-{anio % 100:02d}'
        for i, (titulo, ancho, *_resto) in enumerate(COLUMNAS, 1):
            ws.cell(row=1, column=i, value=titulo).alignment = Alignment(horizontal='left')
            ws.column_dimensions[L(i)].width = ancho
        for r, (valores, precio) in enumerate(zip(filas, precios), 2):
            valores = [*valores]
            valores[MONTO] = f'=J{r}*{precio}'
            for i, (v, (_, _, fuente, alineacion, formato)) in enumerate(zip(valores, COLUMNAS), 1):
                celda = ws.cell(row=r, column=i, value=v)
                azul = i - 1 in (MONTO, ESTATUS)
                celda.font = Font(name=fuente, size=11, color=AZUL if azul else None)
                if alineacion:
                    celda.alignment = Alignment(horizontal=alineacion, vertical='center' if i - 1 == 11 else None)
                if formato:
                    celda.number_format = formato
                if i - 1 == ESTATUS:
                    celda.fill = PatternFill('solid', fgColor='FFFF00')

        if filas:
            tabla = Table(displayName=f'Tabla{clave}', ref=f'A1:{L(len(COLUMNAS))}{len(filas) + 1}')
            tabla.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
            ws.add_table(tabla)
            _tabla_dinamica(wb, ws, tabla.displayName, filas, semana)
        else:
            ws['A2'] = f'No hay cargas de diésel en la semana {semana} ({lunes:%d/%m/%Y} al {lunes + dt.timedelta(days=6):%d/%m/%Y}).'

        salida = io.BytesIO()
        wb.save(salida)
        contenido = salida.getvalue()
        if filas:
            contenido = _sin_renglon_valores(contenido)
        respuesta = HttpResponse(contenido, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        respuesta['Content-Disposition'] = f'attachment; filename="SEMANA {semana} DIESEL.xlsx"'
        return respuesta


def _sin_renglon_valores(contenido):
    """openpyxl no escribe la extensión de Excel 2010 que oculta el renglón "Valores"; se le agrega."""
    entrada, salida = zipfile.ZipFile(io.BytesIO(contenido)), io.BytesIO()
    with zipfile.ZipFile(salida, 'w', zipfile.ZIP_DEFLATED) as nuevo:
        for item in entrada.infolist():
            datos = entrada.read(item.filename)
            if item.filename.startswith('xl/pivotTables/pivotTable') and item.filename.endswith('.xml'):
                datos = datos.replace(b'</pivotTableDefinition>', SIN_RENGLON_VALORES.encode() + b'</pivotTableDefinition>')
            nuevo.writestr(item, datos)
    return salida.getvalue()
