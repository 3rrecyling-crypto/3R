"""
Excel del listado de cargas (Next: /diesel/cargas, botón "Exportar Excel").

Una tabla de Excel (con filtros y renglones alternados), todo centrado, con
hipervínculos "Ver foto" a cada foto de la carga y una fila de totales.
Usa los mismos filtros que el listado. El rendimiento solo aplica a 3R
RECYCLING: los permisionarios son unidades ajenas.
"""
import io

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import es_3r_nombre
from .views import SIN_PERMISIONARIO, filtrar_cargas

MAX_FILAS = 20000
FOTOS = [('foto_bomba', 'Foto bomba'), ('foto_odometro', 'Foto odómetro'), ('foto_thermo', 'Foto bomba thermo'),
         ('foto_horas_thermo', 'Foto horas thermo'), ('foto_sticker', 'Foto sticker'), ('foto_motor', 'Foto motor')]
COMPLEMENTARIAS = 3  # columnas para las fotos complementarias (las demás se ven en la app)


def _url(request, archivo):
    if not archivo:
        return None
    try:
        url = archivo.url
    except Exception:
        return None
    return url if url.startswith('http') else request.build_absolute_uri(url)


class CargasExcelAPIView(APIView):
    """GET con los filtros del listado (?patio, ?unidad, ?permisionario, ?fecha_inicio, ?fecha_fin): descarga .xlsx."""

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.has_perm('ternium.acceso_diesel')):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter as L
        from openpyxl.worksheet.table import Table, TableStyleInfo

        cargas = list(filtrar_cargas(user, request.query_params).order_by('-fecha_carga', '-pk')[:MAX_FILAS])
        # (título, ancho, formato numérico o None)
        columnas = [
            ('#', 6, '0'), ('Fecha', 12, None), ('Hora', 8, None), ('Tipo', 9, None), ('Unidad / Thermo', 16, None),
            ('Permisionario', 26, None), ('Operador', 24, None), ('Patio', 20, None), ('Odómetro (km)', 15, '#,##0'), ('Horas thermo', 13, '#,##0.0'),
            ('Litros diésel', 13, '#,##0.00'), ('Litros thermo', 13, '#,##0.00'), ('Total litros', 13, '#,##0.00'),
            ('Precio/L', 12, '"$"#,##0.00'), ('Costo', 15, '"$"#,##0.00'), ('Rendimiento (km/L)', 17, '0.00'),
            ('Cinchos anteriores', 18, None), ('Cinchos actuales', 18, None), ('Despachador', 22, None),
            *[(nombre, 16, None) for _, nombre in FOTOS],
            *[(f'Foto complementaria {n}', 16, None) for n in range(1, COMPLEMENTARIAS + 1)],
        ]
        wb = Workbook()
        ws = wb.active
        ws.title = 'Cargas'
        ws.sheet_view.showGridLines = False
        centro = Alignment(horizontal='center', vertical='center', wrap_text=True)
        fino = Side(style='thin', color='D7DEE8')

        # Título y filtros
        ultima_col = L(len(columnas))
        ws.merge_cells(f'A1:{ultima_col}1')
        ws['A1'] = 'Listado de cargas de diésel · 3R Recycling'
        ws['A1'].font = Font(bold=True, size=15, color='FFFFFF')
        ws['A1'].fill = PatternFill('solid', fgColor='0B1730')
        ws['A1'].alignment = centro
        ws.row_dimensions[1].height = 30
        p = request.query_params
        perm = (p.get('permisionario') or '').strip()
        filtros = [f'Desde {p["fecha_inicio"]}' if p.get('fecha_inicio') else '', f'hasta {p["fecha_fin"]}' if p.get('fecha_fin') else '',
                   f'Unidad/thermo: {p["unidad"]}' if p.get('unidad') else '',
                   ('Sin permisionario' if perm == SIN_PERMISIONARIO else f'Permisionario: {perm}') if perm else '']
        ws.merge_cells(f'A2:{ultima_col}2')
        ws['A2'] = (' · '.join(f for f in filtros if f) or 'Todas las cargas') + \
            f' · {len(cargas)} cargas · generado por {user.get_full_name() or user.username} el {timezone.localtime():%d/%m/%Y %H:%M}'
        ws['A2'].font = Font(italic=True, size=10, color='475569')
        ws['A2'].alignment = centro

        enc = 4
        for i, (titulo, ancho, _) in enumerate(columnas, 1):
            celda = ws.cell(row=enc, column=i, value=titulo)
            celda.font = Font(bold=True, color='FFFFFF')
            celda.fill = PatternFill('solid', fgColor='1D4ED8')
            celda.alignment = centro
            ws.column_dimensions[L(i)].width = ancho
        ws.row_dimensions[enc].height = 30

        primera_foto = len(columnas) - len(FOTOS) - COMPLEMENTARIAS + 1
        for n, c in enumerate(cargas, 1):
            r = enc + n
            local = timezone.localtime(c.fecha_carga)
            es3r = es_3r_nombre(c.permisionario_nombre)
            thermo = c.tipo_carga == 'thermo'
            valores = [
                n, local.strftime('%d/%m/%Y'), local.strftime('%H:%M'), 'Thermo' if thermo else 'Unidad', c.equipo,
                c.permisionario_nombre or 'Sin permisionario', c.operador_nombre or None, c.patio.nombre,
                float(c.odometro) if c.odometro is not None and not thermo else None,
                float(c.hrs_thermo) if thermo and c.hrs_thermo else None,
                float(c.litros_diesel), float(c.litros_thermo), float(c.litros_diesel + c.litros_thermo),
                float(c.precio_litro) or None, float(c.costo_total),
                float(c.rendimiento) if es3r and c.rendimiento is not None else None,
                c.cinchos_anteriores or None, c.cinchos_actuales or None,
                c.usuario.get_full_name() or c.usuario.username,
            ]
            for i, v in enumerate(valores, 1):
                celda = ws.cell(row=r, column=i, value=v if v is not None else '—')
                if columnas[i - 1][2] and v is not None:
                    celda.number_format = columnas[i - 1][2]
            archivos = [getattr(c, campo) for campo, _ in FOTOS]
            extras = [f.foto for f in c.fotos_complementarias.all()][:COMPLEMENTARIAS]
            archivos += extras + [None] * (COMPLEMENTARIAS - len(extras))
            for k, archivo in enumerate(archivos):
                celda = ws.cell(row=r, column=primera_foto + k)
                url = _url(request, archivo)
                if url:
                    celda.value = 'Ver foto'
                    celda.hyperlink = url
                    celda.font = Font(color='1D4ED8', underline='single', bold=True)
                else:
                    celda.value = '—'
            for i in range(1, len(columnas) + 1):
                ws.cell(row=r, column=i).alignment = centro

        ultima = enc + len(cargas)
        if cargas:
            # Tabla de Excel: filtros en el encabezado y renglones alternados
            tabla = Table(displayName='Cargas', ref=f'A{enc}:{ultima_col}{ultima}')
            tabla.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
            ws.add_table(tabla)
            t = ultima + 1
            ws.cell(row=t, column=5, value='Totales')
            for i, (titulo, _, fmt) in enumerate(columnas, 1):
                if titulo in ('Litros diésel', 'Litros thermo', 'Total litros', 'Costo'):
                    ws.cell(row=t, column=i, value=f'=SUBTOTAL(109,{L(i)}{enc + 1}:{L(i)}{ultima})').number_format = fmt
                celda = ws.cell(row=t, column=i)
                celda.font = Font(bold=True)
                celda.alignment = centro
                celda.fill = PatternFill('solid', fgColor='EEF2F7')
                celda.border = Border(top=Side(style='medium', color='1D4ED8'), bottom=fino)
            ws.row_dimensions[t].height = 22
        else:
            ws.cell(row=enc + 1, column=1, value='No hay cargas con esos filtros.')
        ws.freeze_panes = ws.cell(row=enc + 1, column=6)

        salida = io.BytesIO()
        wb.save(salida)
        nombre = f'Cargas de diesel {timezone.localdate():%Y-%m-%d}.xlsx'
        respuesta = HttpResponse(salida.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return respuesta
