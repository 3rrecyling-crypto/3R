from django.shortcuts import render, redirect
from .models import Cuenta, Movimiento, SubCategoria
from .forms import MovimientoForm, TransferenciaForm, CuentaForm, TerceroForm # <--- IMPORTAR
from django.http import JsonResponse
from .models import Movimiento, UnidadNegocio, Operacion, Categoria, SubCategoria
from django.db.models import Sum
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .forms import CuentaForm # Importar el nuevo form
from .models import Movimiento
# Importa librerías para manejar archivos (necesitarás instalar una como openpyxl o usar csv)
from django.http import HttpResponse 
import csv,decimal
from datetime import datetime, timedelta, date
from django.utils import timezone
from django.db.models import Sum, Q # Asegura Q y Sum estén aquí
import requests  # <--- NECESARIO PARA BANXICO
import os # <--- ASEGÚRATE DE TENER ESTEe
import boto3 # <--- NECESARIO
from botocore.exceptions import BotoCoreError, NoCredentialsError # <--- NECESARIO
from django.conf import settings # <--- NECESARIO
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
import openpyxl

def _subir_archivo_a_s3(archivo_obj, s3_ruta_relativa):
    """
    Sube un archivo a S3 manualmente.
    """
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # Boto3 necesita la ruta completa (Key) dentro del bucket
        full_s3_path = f"{settings.AWS_MEDIA_LOCATION}/{s3_ruta_relativa}"

        s3_client.upload_fileobj(
            archivo_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            full_s3_path
        )
        return s3_ruta_relativa
        
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al subir el archivo a S3: {e}")
        return None

def _eliminar_archivo_de_s3(ruta_relativa):
    """
    Elimina un archivo de S3 usando la ruta relativa almacenada en BD.
    """
    if not ruta_relativa:
        return
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        # Reconstruimos la Key completa
        full_s3_path = f"{settings.AWS_MEDIA_LOCATION}/{ruta_relativa}"
        
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=full_s3_path
        )
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al eliminar archivo de S3: {e}")
# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
def obtener_tipo_cambio_banxico():
    # 1. Obtener el token de las configuraciones de Django
    # Asume que tienes BANXICO_API_TOKEN definido en settings.py (que lo obtendrá del entorno)
    token = settings.BANXICO_API_TOKEN 
    
    # Si el token no está configurado, no hacemos la llamada
    if not token:
        print("Advertencia: BANXICO_API_TOKEN no está configurado.")
        return 20.50 # Valor de referencia/fallback

    series = "SF43718" # Serie FIX (Dólar para solventar obligaciones)
    url = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{series}/datos/oportuno"
    
    headers = {
        'Bmx-Token': token,
        'Accept': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status() # Lanza un error para códigos 4xx/5xx
        
        data = response.json()
        # Navegamos el JSON de Banxico para sacar el dato
        dato_str = data['bmx']['series'][0]['datos'][0]['dato']
        return float(dato_str)
        
    except requests.exceptions.RequestException as e:
        print(f"Error en la solicitud a Banxico: {e}")
    except Exception as e:
        print(f"Error procesando datos de Banxico: {e}")
    
    # Si falla la conexión o el procesamiento, regresamos un valor de referencia
    return 20.50

# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
def dashboard(request):
    # ---------------------------------------------------------
    # 1. FILTROS DE FECHA
    # ---------------------------------------------------------
    filtro_tiempo = request.GET.get('filtro', 'hoy')
    hoy = timezone.now().date()
    fecha_inicio = hoy
    fecha_fin = hoy

    if filtro_tiempo == 'semana':
        fecha_inicio = hoy - timedelta(days=7)
    elif filtro_tiempo == 'mes':
        fecha_inicio = hoy.replace(day=1)
    elif filtro_tiempo == 'custom':
        f_ini = request.GET.get('fecha_inicio')
        f_fin = request.GET.get('fecha_fin')
        if f_ini and f_fin:
            try:
                fecha_inicio = datetime.strptime(f_ini, '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(f_fin, '%Y-%m-%d').date()
            except ValueError:
                pass

    # ---------------------------------------------------------
    # 2. CÁLCULO DE KPIs
    # ---------------------------------------------------------
    movs_rango = Movimiento.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
    
    # Usamos Coalesce o "or 0" para evitar None
    ingresos_periodo = movs_rango.aggregate(Sum('abono'))['abono__sum'] or 0
    egresos_periodo = movs_rango.aggregate(Sum('cargo'))['cargo__sum'] or 0
    balance_periodo = ingresos_periodo - egresos_periodo
    
    movimientos_ingresos_count = movs_rango.filter(abono__gt=0).count()
    movimientos_egresos_count = movs_rango.filter(cargo__gt=0).count()

    # ---------------------------------------------------------
    # 3. CUENTAS Y TIPO DE CAMBIO (CORREGIDO)
    # ---------------------------------------------------------
    todas_cuentas = Cuenta.objects.all()
    
    # A) Primero obtenemos el Tipo de Cambio REAL
    raw_tc = obtener_tipo_cambio_banxico()
    
    try:
        if raw_tc:
            tipo_cambio_actual = Decimal(str(raw_tc))
        else:
            # Fallback de seguridad (mejor 20 que 1)
            tipo_cambio_actual = Decimal('20.00')
    except Exception:
        tipo_cambio_actual = Decimal('20.00')

    # B) Calculamos los totales por moneda
    total_mxn = sum(c.saldo_actual for c in todas_cuentas if c.moneda == 'MXN')
    total_usd = sum(c.saldo_actual for c in todas_cuentas if c.moneda == 'USD')
    
    # C) Calculamos la conversión AQUÍ (en Python, con precisión)
    total_usd_convertido = total_usd * tipo_cambio_actual
    
    # D) Gran Total Consolidado
    saldo_total_consolidado = total_mxn + total_usd_convertido

    # E) Ordenamos cuentas para la vista
    cuentas_ordenadas = sorted(
        todas_cuentas, 
        key=lambda c: c.saldo_actual, 
        reverse=True
    )
    
    cuentas_mxn = [c for c in todas_cuentas if c.moneda == 'MXN']
    cuentas_usd = [c for c in todas_cuentas if c.moneda == 'USD']

    # ---------------------------------------------------------
    # 4. MOVIMIENTOS RECIENTES
    # ---------------------------------------------------------
    movimientos_recientes = Movimiento.objects.select_related('cuenta').order_by('-fecha', '-id')[:5]

    # ---------------------------------------------------------
    # 5. CONTEXTO
    # ---------------------------------------------------------
    context = {
        'filtro_actual': filtro_tiempo,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        
        'ingresos_periodo': ingresos_periodo,
        'egresos_periodo': egresos_periodo,
        'balance_periodo': balance_periodo,
        'movimientos_ingresos_count': movimientos_ingresos_count,
        'movimientos_egresos_count': movimientos_egresos_count,
        
        'cuentas': cuentas_ordenadas, 
        'cuentas_mxn': cuentas_mxn, 
        'cuentas_usd': cuentas_usd, 
        
        'total_mxn': total_mxn,
        'total_usd': total_usd,
        'saldo_total': saldo_total_consolidado, 
        
        # DATOS DE CONVERSIÓN CORREGIDOS
        'tipo_cambio': tipo_cambio_actual,
        'total_usd_convertido': total_usd_convertido, # <--- ¡IMPORTANTE!
        
        'movimientos_recientes': movimientos_recientes,
    }
    return render(request, 'flujo_bancos/dashboard.html', context)
def lista_transferencias(request):
    # Buscamos movimientos que parecen transferencias (Salidas)
    # y tratamos de buscar su par.
    transferencias = Movimiento.objects.filter(
        cargo__gt=0
    ).filter(
        Q(concepto__icontains='(Envío a') | 
        Q(concepto__icontains='Transferencia')
    ).select_related('cuenta').order_by('-fecha')

    return render(request, 'flujo_bancos/lista_transferencias.html', {
        'transferencias': transferencias
    })

# ---------------------------------------------------------
# CANCELAR TRANSFERENCIA (Elimina salida y entrada)
# ---------------------------------------------------------
def cancelar_transferencia(request, pk):
    salida = get_object_or_404(Movimiento, pk=pk)
    
    if salida.auditado:
        messages.error(request, "No se puede cancelar una transferencia auditada.")
        return redirect('lista_transferencias')

    concepto_base = salida.concepto.split(' (Envío a')[0]
    entrada = Movimiento.objects.filter(
        fecha=salida.fecha,
        abono__gt=0,
        concepto__icontains=concepto_base
    ).exclude(id=salida.id).first()

    # --- BORRADO DE S3 ---
    if entrada:
        if entrada.comprobante:
            _eliminar_archivo_de_s3(str(entrada.comprobante))
        entrada.delete()
    
    if salida.comprobante:
        _eliminar_archivo_de_s3(str(salida.comprobante))
    # ---------------------

    salida.delete()
    
    messages.success(request, "Transferencia cancelada y archivos eliminados.")
    return redirect('lista_transferencias')

# ---------------------------------------------------------
# LISTAR MOVIMIENTOS
# ---------------------------------------------------------
def lista_movimientos(request):
    # 1. QuerySet Base (CORREGIDO: Se eliminó 'tercero' de select_related)
    movimientos = Movimiento.objects.all().select_related(
        'cuenta', 
        'unidad_negocio', 
        'operacion', 
        'categoria', 
        'subcategoria'
    ).order_by('-fecha')
    
    # 2. Obtener parámetros de filtros del GET
    q = request.GET.get('q')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    tipo = request.GET.get('tipo')
    unidad_id = request.GET.get('unidad')
    operacion_id = request.GET.get('operacion')
    categoria_id = request.GET.get('categoria')
    subcategoria_id = request.GET.get('subcategoria')

    # 3. Aplicar Filtros Dinámicos
    if q:
        # Filtra por concepto O por nombre del tercero (que es texto)
        movimientos = movimientos.filter(
            Q(concepto__icontains=q) | 
            Q(tercero__icontains=q)
        )
    
    if fecha_inicio:
        movimientos = movimientos.filter(fecha__gte=fecha_inicio)
        
    if fecha_fin:
        movimientos = movimientos.filter(fecha__lte=fecha_fin)
        
    if tipo == 'ingreso':
        movimientos = movimientos.filter(abono__gt=0)
    elif tipo == 'egreso':
        movimientos = movimientos.filter(cargo__gt=0)
        
    if unidad_id:
        movimientos = movimientos.filter(unidad_negocio_id=unidad_id)

    if operacion_id:
        movimientos = movimientos.filter(operacion_id=operacion_id)

    if categoria_id:
        movimientos = movimientos.filter(categoria_id=categoria_id)

    if subcategoria_id:
        movimientos = movimientos.filter(subcategoria_id=subcategoria_id)

    # 4. Obtener catálogos para llenar los <select> del HTML
    unidades = UnidadNegocio.objects.all().order_by('nombre')
    operaciones = Operacion.objects.all().order_by('nombre')
    categorias = Categoria.objects.all().order_by('nombre')
    subcategorias = SubCategoria.objects.all().order_by('nombre')

    context = {
        'movimientos': movimientos,
        'unidades_negocio': unidades,
        'operaciones': operaciones,
        'categorias': categorias,
        'subcategorias': subcategorias,
    }
        
    return render(request, 'flujo_bancos/lista_movimientos.html', context)

# ---------------------------------------------------------
# CREAR MOVIMIENTO
# ---------------------------------------------------------
def crear_movimiento(request):
    lista_conceptos = Movimiento.objects.values_list('concepto', flat=True).distinct().exclude(concepto__exact='')

    if request.method == 'POST':
        # IMPORTANTE: Agregar request.FILES para procesar archivos
        form = MovimientoForm(request.POST, request.FILES) 
        
        if form.is_valid():
            # 1. Guardamos el objeto primero para obtener su ID (pk)
            movimiento = form.save(commit=False)
            movimiento.save() # Guardado inicial
            
            # 2. Lógica de subida a S3 si hay comprobante
            if 'comprobante' in request.FILES:
                archivo = request.FILES['comprobante']
                _nombre_base, extension = os.path.splitext(archivo.name)
                
                # Creamos una ruta organizada: movimientos/[ID]/comprobante.[ext]
                s3_path = f"movimientos/{movimiento.pk}/comprobante{extension}"
                
                ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
                
                if ruta_guardada:
                    movimiento.comprobante = ruta_guardada
                    movimiento.save() # Guardamos de nuevo con la ruta
                else:
                    # Opcional: Manejar error con messages.error
                    pass
            
            return redirect('lista_movimientos')
    else:
        form = MovimientoForm()
    
    context = {
        'form': form,
        'lista_conceptos': lista_conceptos,
    }
    return render(request, 'flujo_bancos/crear_movimiento.html', context)
# ---------------------------------------------------------
# CREAR TRANSFERENCIA ENTRE CUENTAS
# ---------------------------------------------------------
def crear_transferencia(request):
    if request.method == 'POST':
        form = TransferenciaForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            origen = data['cuenta_origen']
            destino = data['cuenta_destino']
            monto_origen = data['monto']
            tc = data['tipo_cambio'] or 1.0
            fecha = data['fecha']
            concepto_base = data['concepto']

            # Calcular el monto que entra a la cuenta destino
            monto_destino = monto_origen * tc

            # 1. Crear CARGO (Salida) en la cuenta Origen
            Movimiento.objects.create(
                cuenta=origen,
                fecha=fecha,
                concepto=f"{concepto_base} (Envío a {destino.nombre})",
                cargo=monto_origen,
                abono=0,
                comentarios=f"Salida de fondos. TC aplicado: {tc}"
            )

            # 2. Crear ABONO (Entrada) en la cuenta Destino
            Movimiento.objects.create(
                cuenta=destino,
                fecha=fecha,
                concepto=f"{concepto_base} (Recepción de {origen.nombre})",
                cargo=0,
                abono=monto_destino,
                comentarios=f"Entrada de fondos. Monto original: {monto_origen} {origen.moneda}. TC: {tc}"
            )

            # --- CORRECCIÓN AQUÍ ---
            # Antes decía: return redirect('dashboard')
            return redirect('dashboard_bancos') 
            # -----------------------

    else:
        form = TransferenciaForm()
    
    return render(request, 'flujo_bancos/form_transferencia.html', {'form': form})

# ---------------------------------------------------------
# AJAX: CARGAR SUBCATEGORÍAS
# ---------------------------------------------------------
def cargar_subcategorias(request):
    categoria_id = request.GET.get('categoria_id')
    subcategorias = SubCategoria.objects.filter(categoria_id=categoria_id).order_by('nombre').values('id', 'nombre')
    return JsonResponse(list(subcategorias), safe=False)


def obtener_saldo_cuenta(request):
    cuenta_id = request.GET.get('cuenta_id')
    if cuenta_id:
        cuenta = get_object_or_404(Cuenta, id=cuenta_id)
        return JsonResponse({'saldo': cuenta.saldo_actual})
    return JsonResponse({'saldo': 0})


def editar_cuenta(request, cuenta_id):
    cuenta = get_object_or_404(Cuenta, id=cuenta_id)
    
    if request.method == 'POST':
        form = CuentaForm(request.POST, instance=cuenta)
        if form.is_valid():
            form.save()
            return redirect('dashboard_bancos')
    else:
        form = CuentaForm(instance=cuenta)
    
    return render(request, 'flujo_bancos/editar_cuenta.html', {
        'form': form, 
        'cuenta': cuenta
    })
    
def crear_tercero(request):
    if request.method == 'POST':
        form = TerceroForm(request.POST)
        if form.is_valid():
            tercero = form.save()
            # Retornamos un script simple para cerrar el popup y recargar la página padre
            # O mejor, redirigir a 'crear_movimiento' si no es popup.
            return render(request, 'flujo_bancos/close_popup.html') 
    else:
        form = TerceroForm()
    
    return render(request, 'flujo_bancos/crear_tercero.html', {'form': form})


def auditar_movimiento(request, pk):
    mov = get_object_or_404(Movimiento, pk=pk)
    mov.auditado = True
    mov.save()
    messages.success(request, 'Movimiento auditado y bloqueado correctamente.')
    return redirect('lista_movimientos')


def exportar_movimientos_excel(request):
    # 1. QuerySet Base con select_related para cargar todos los objetos relacionados
    movimientos = Movimiento.objects.all().select_related(
        'cuenta', 
        'unidad_negocio', 
        'operacion', 
        'categoria', 
        'subcategoria'
    ).order_by('-fecha')
    
    # 2. Aplicar la lógica de filtrado (Mantenemos la lógica de filtrado intacta)
    q = request.GET.get('q')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    tipo = request.GET.get('tipo')
    unidad_id = request.GET.get('unidad')
    operacion_id = request.GET.get('operacion')
    categoria_id = request.GET.get('categoria')
    subcategoria_id = request.GET.get('subcategoria')

    if q:
        movimientos = movimientos.filter(Q(concepto__icontains=q) | Q(tercero__icontains=q))
    if fecha_inicio:
        movimientos = movimientos.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        movimientos = movimientos.filter(fecha__lte=fecha_fin)
    if tipo == 'ingreso':
        movimientos = movimientos.filter(abono__gt=0)
    elif tipo == 'egreso':
        movimientos = movimientos.filter(cargo__gt=0)
    if unidad_id:
        movimientos = movimientos.filter(unidad_negocio_id=unidad_id)
    if operacion_id:
        movimientos = movimientos.filter(operacion_id=operacion_id)
    if categoria_id:
        movimientos = movimientos.filter(categoria_id=categoria_id)
    if subcategoria_id:
        movimientos = movimientos.filter(subcategoria_id=subcategoria_id)
    
    # 3. Generar el Excel
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Reporte_Movimientos.xlsx"'
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    
    # Estilos básicos
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    center_aligned = Alignment(horizontal="center", vertical="center")
    currency_format = '"$"#,##0.00'

    # Cabeceras (NUEVAS: Saldo Inicial y Saldo Final)
    headers = [
        "Fecha", "Cuenta", "Concepto", "Tercero", 
        "Saldo Inicial", "Cargo", "Abono", "Saldo Final", 
        "U. Negocio", "Operación", "Categoría", "Subcategoría", 
        "IVA", "Ret. IVA", "Ret. ISR", "Auditado"
    ]
    ws.append(headers)
    
    # Aplicar estilos a las cabeceras
    for col_idx, cell in enumerate(ws[1]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_aligned
        cell.border = thin_border
        
    row_num = 2
    
    # 4. Llenar filas
    for mov in movimientos:
        
        # Lógica para calcular el SALDO INICIAL
        if mov.abono and mov.abono > 0:
            # Si es Ingreso: Saldo Final - Abono = Saldo Inicial
            saldo_inicial_mov = mov.saldo_banco - mov.abono
        elif mov.cargo and mov.cargo > 0:
            # Si es Egreso: Saldo Final + Cargo = Saldo Inicial
            saldo_inicial_mov = mov.saldo_banco + mov.cargo
        else:
            # Caso raro o movimiento 0, asumimos saldo es el mismo
            saldo_inicial_mov = mov.saldo_banco
            
        # Manejo seguro de campos relacionales (para evitar errores si son None)
        unidad_negocio_nombre = mov.unidad_negocio.nombre if mov.unidad_negocio else ""
        operacion_nombre = mov.operacion.nombre if mov.operacion else ""
        categoria_nombre = mov.categoria.nombre if mov.categoria else ""
        subcategoria_nombre = mov.subcategoria.nombre if mov.subcategoria else ""
        
        row = [
            mov.fecha,
            mov.cuenta.nombre,
            mov.concepto,
            mov.tercero if mov.tercero else "",
            
            saldo_inicial_mov,     # Nuevo Saldo Inicial
            mov.cargo,
            mov.abono,
            mov.saldo_banco,       # Saldo Final
            
            unidad_negocio_nombre, 
            operacion_nombre,      
            categoria_nombre,      
            subcategoria_nombre,   
            mov.iva,
            mov.ret_iva,
            mov.ret_isr,
            'Si' if mov.auditado else 'No'
        ]
        ws.append(row)

        # 5. Estilizar y formatear celdas
        for col_idx, cell in enumerate(ws[row_num], start=1):
            cell.border = thin_border
            
            # Formato de moneda (Columnas: 5, 6, 7, 8, 13, 14, 15)
            # Saldo Inicial (5), Cargo (6), Abono (7), Saldo Final (8), IVA (13), Ret. IVA (14), Ret. ISR (15)
            if col_idx in [5, 6, 7, 8, 13, 14, 15]: 
                cell.number_format = currency_format
            
            # Formato de fecha (Columna 1)
            if col_idx == 1:
                cell.number_format = 'DD/MM/YYYY'
                cell.alignment = center_aligned

        row_num += 1

    # 6. Auto-ajustar ancho de columnas
    for column_cells in ws.columns:
        max_length = 0
        column = column_cells[0].column_letter
        for cell in column_cells:
            try:
                # El ancho máximo debe considerar el header si es más largo que el valor
                header_length = len(headers[column_cells[0].col_idx - 1]) 
                cell_value_length = len(str(cell.value) if cell.value else "")
                
                if cell_value_length > max_length:
                    max_length = cell_value_length
                
                # Ajustar max_length para que sea el mayor entre el valor y el header
                if header_length > max_length:
                    max_length = header_length

            except:
                pass
        
        # Agregamos un poco de espacio extra
        ws.column_dimensions[column].width = (max_length + 2)
        
    wb.save(response)
    return response


def detalle_movimiento(request, pk):
    mov = get_object_or_404(Movimiento, pk=pk)
    
    s3_url = None
    es_imagen = False
    es_pdf = False

    if mov.comprobante:
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
            
            # Construir la llave completa (Igual que en _subir_archivo)
            key = f"{settings.AWS_MEDIA_LOCATION}/{mov.comprobante}"
            
            # Generar URL temporal (válida por 1 hora)
            s3_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': key},
                ExpiresIn=3600
            )

            # Determinar tipo de archivo para la vista HTML
            ext = str(mov.comprobante).lower()
            if ext.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                es_imagen = True
            elif ext.endswith('.pdf'):
                es_pdf = True
                
        except Exception as e:
            print(f"Error generando URL de S3: {e}")

    return render(request, 'flujo_bancos/detalle_movimiento.html', {
        'mov': mov,
        's3_url': s3_url,
        'es_imagen': es_imagen,
        'es_pdf': es_pdf
    })
# flujo_bancos/views.py

from django.shortcuts import render, redirect, get_object_or_404
from .models import Movimiento
from .forms import MovimientoForm # Asegúrate de importar el Formulario
# Importa messages si lo usas


def editar_movimiento(request, pk):
    # Recuperamos el objeto original
    movimiento_original = get_object_or_404(Movimiento, pk=pk)
    
    if request.method == 'POST':
        # IMPORTANTE: Agregar request.FILES
        form = MovimientoForm(request.POST, request.FILES, instance=movimiento_original)
        
        if form.is_valid():
            # Guardamos sin commit para manipular el archivo
            movimiento = form.save(commit=False)
            
            # --- LÓGICA S3 TIPO views t.py ---
            if 'comprobante' in request.FILES:
                # 1. Eliminar archivo anterior si existe
                if movimiento_original.comprobante:
                    # Asumiendo que guardas la ruta relativa en el campo
                    _eliminar_archivo_de_s3(str(movimiento_original.comprobante))
                
                # 2. Subir nuevo archivo
                archivo = request.FILES['comprobante']
                _nombre_base, extension = os.path.splitext(archivo.name)
                s3_path = f"movimientos/{movimiento.pk}/comprobante{extension}"
                
                ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
                
                if ruta_guardada:
                    movimiento.comprobante = ruta_guardada
            
            movimiento.save()
            messages.success(request, 'Movimiento actualizado correctamente.')
            return redirect('lista_movimientos')
    else:
        form = MovimientoForm(instance=movimiento_original)

    context = {
        'form': form,
        'movimiento': movimiento_original,
    }
    return render(request, 'flujo_bancos/crear_movimiento.html', context)


def crear_transferencia(request):
    if request.method == 'POST':
        form = TransferenciaForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            origen = data['cuenta_origen']
            destino = data['cuenta_destino']
            monto_origen = data['monto']
            tc = data['tipo_cambio'] or 1.0
            fecha = data['fecha']
            concepto_base = data['concepto']

            monto_destino = monto_origen * tc

            # --- CORRECCIÓN IMPORTANTE: Calcular Saldos ---
            # Nota: saldo_actual calcula el saldo con los movimientos YA guardados.
            saldo_previo_origen = origen.saldo_actual
            saldo_previo_destino = destino.saldo_actual
            
            saldo_final_origen = saldo_previo_origen - monto_origen
            saldo_final_destino = saldo_previo_destino + monto_destino

            # 1. Crear CARGO (Salida) con Saldo calculado
            Movimiento.objects.create(
                cuenta=origen,
                fecha=fecha,
                concepto=f"{concepto_base} (Envío a {destino.nombre})",
                cargo=monto_origen,
                abono=0,
                saldo_banco=saldo_final_origen, # <--- GUARDAMOS EL SALDO FINAL
                comentarios=f"Salida de fondos. TC aplicado: {tc}"
            )

            # 2. Crear ABONO (Entrada) con Saldo calculado
            Movimiento.objects.create(
                cuenta=destino,
                fecha=fecha,
                concepto=f"{concepto_base} (Recepción de {origen.nombre})",
                cargo=0,
                abono=monto_destino,
                saldo_banco=saldo_final_destino, # <--- GUARDAMOS EL SALDO FINAL
                comentarios=f"Entrada de fondos. Monto original: {monto_origen} {origen.moneda}. TC: {tc}"
            )

            return redirect('dashboard_bancos')
    else:
        form = TransferenciaForm()
    
    return render(request, 'flujo_bancos/form_transferencia.html', {'form': form})

import csv,openpyxl
import re
from .models import Movimiento
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from django.http import HttpResponse
from django.db.models import Q
import re
from .models import Movimiento

def exportar_transferencias_excel(request):
    """
    Genera un Excel (.xlsx) nativo con formato de tabla, estilos y fórmulas.
    Requiere: pip install openpyxl
    """
    # 1. Configuración del Libro y Hoja
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Transferencias"

    # 2. Definir Estilos
    # Encabezado: Negrita, Blanco, Fondo Azul, Centrado
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    center_aligned = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    # Bordes finos
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'), 
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    
    # Formato de Moneda
    currency_format = '"$"#,##0.00_-'

    # 3. Encabezados
    headers = [
        "Fecha", "Concepto Base", 
        "Cuenta Origen", "Saldo Inicial (Origen)", "Salida ($)", "Saldo Final (Origen)",
        "Cuenta Destino", "Saldo Inicial (Destino)", "Entrada ($)", "Saldo Final (Destino)",
        "Comentarios"
    ]

    ws.append(headers)

    # Aplicar estilo a la fila de encabezados (Fila 1)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_aligned
        cell.border = thin_border

    # 4. Obtener Datos (Lógica de emparejamiento)
    salidas = Movimiento.objects.filter(
        cargo__gt=0
    ).filter(
        Q(concepto__icontains='(Envío a') | 
        Q(concepto__icontains='Transferencia')
    ).select_related('cuenta').order_by('-fecha', '-id')

    row_num = 2 # Empezamos en la fila 2

    for salida in salidas:
        # A. CALCULAR DATOS ORIGEN
        # Retroactivo: Si SaldoFinal=800 y Salida=200, entonces Inicial=1000
        saldo_final_org = salida.saldo_banco if salida.saldo_banco is not None else 0
        saldo_inicial_org = saldo_final_org + salida.cargo

        # B. BUSCAR DESTINO (MATCHING)
        concepto_full = salida.concepto
        concepto_base = concepto_full
        nombre_destino = "---"
        monto_entrada = 0
        saldo_final_dest = 0
        saldo_inicial_dest = 0

        # Intentar extraer nombre del destino del texto "(Envío a ...)"
        match = re.search(r'\(Envío a (.*?)\)', concepto_full)
        if match:
            nombre_destino_txt = match.group(1)
            nombre_destino = nombre_destino_txt
            
            # Limpiamos el concepto base para buscar
            base_search = concepto_full.split(' (Envío a')[0]
            concepto_base = base_search

            # Buscamos la contraparte (Entrada en el mismo día con concepto similar)
            posible_entrada = Movimiento.objects.filter(
                fecha=salida.fecha,
                abono__gt=0,
                concepto__icontains=base_search
            ).exclude(id=salida.id).first()

            if posible_entrada:
                nombre_destino = posible_entrada.cuenta.nombre
                monto_entrada = posible_entrada.abono
                saldo_final_dest = posible_entrada.saldo_banco if posible_entrada.saldo_banco is not None else 0
                saldo_inicial_dest = saldo_final_dest - monto_entrada

        # C. ESCRIBIR FILA
        row = [
            salida.fecha,           # Col 1
            concepto_base,          # Col 2
            salida.cuenta.nombre,   # Col 3
            saldo_inicial_org,      # Col 4 (Num)
            salida.cargo,           # Col 5 (Num)
            saldo_final_org,        # Col 6 (Num)
            nombre_destino,         # Col 7
            saldo_inicial_dest,     # Col 8 (Num)
            monto_entrada,          # Col 9 (Num)
            saldo_final_dest,       # Col 10 (Num)
            salida.comentarios      # Col 11
        ]
        ws.append(row)

        # D. ESTILIZAR CELDAS DE LA FILA ACTUAL
        for col_idx, cell in enumerate(ws[row_num], start=1):
            cell.alignment = center_aligned
            cell.border = thin_border
            
            # Columnas de Moneda (4, 5, 6, 8, 9, 10)
            if col_idx in [4, 5, 6, 8, 9, 10]:
                cell.number_format = currency_format
            
            # Columna Fecha (1)
            if col_idx == 1:
                cell.number_format = 'DD/MM/YYYY'

        row_num += 1

    # 5. AUTO-AJUSTAR ANCHO DE COLUMNAS
    # Recorremos todas las columnas y ajustamos al contenido más ancho
    for column_cells in ws.columns:
        length = max(len(str(cell.value) if cell.value else "") for cell in column_cells)
        # Agregamos un poco de espacio extra
        ws.column_dimensions[column_cells[0].column_letter].width = length + 4

    # 6. Generar Respuesta HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Reporte_Transferencias_Pro.xlsx"'
    
    wb.save(response)
    return response

def ajax_obtener_tc(request):
    """Devuelve el Tipo de Cambio actual en formato JSON"""
    tc = obtener_tipo_cambio_banxico() # Usamos tu función existente
    return JsonResponse({'tc': tc})