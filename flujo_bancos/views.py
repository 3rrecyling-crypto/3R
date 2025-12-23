from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Q
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from datetime import datetime, timedelta
import csv
import io
from .models import Categoria, SubCategoria
from .forms import CategoriaForm, SubCategoriaForm
import os
import re
from decimal import Decimal # <--- IMPORTANTE: AGREGAR ESTO AL INICIO

# Importaciones de AWS S3
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
from .models import Movimiento, Cuenta # Solo deja los modelos reales# Importaciones de Excel
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Importaciones locales (Modelos y Forms)
from .models import Cuenta, Movimiento, SubCategoria, UnidadNegocio, Operacion, Categoria
from .forms import (
    MovimientoForm, 
    TransferenciaForm, 
    CuentaForm, 
    TerceroForm, 
    ImportarTxtForm  # <--- Asegúrate que esto esté importado
)

# ---------------------------------------------------------
# UTILIDADES S3
# ---------------------------------------------------------
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
        full_s3_path = f"{settings.AWS_MEDIA_LOCATION}/{ruta_relativa}"
        
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=full_s3_path
        )
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al eliminar archivo de S3: {e}")

# ---------------------------------------------------------
# UTILIDADES BANXICO
# ---------------------------------------------------------
def obtener_tipo_cambio_banxico():
    token = getattr(settings, 'BANXICO_API_TOKEN', None)
    
    if not token:
        # print("Advertencia: BANXICO_API_TOKEN no está configurado.")
        return 20.50 

    series = "SF43718" # Serie FIX
    url = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{series}/datos/oportuno"
    
    headers = {
        'Bmx-Token': token,
        'Accept': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        dato_str = data['bmx']['series'][0]['datos'][0]['dato']
        return float(dato_str)
        
    except Exception as e:
        # print(f"Error procesando datos de Banxico: {e}")
        return 20.50

# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
def dashboard(request):
    # 1. FILTROS DE FECHA
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

    # 2. CÁLCULO DE KPIs
    movs_rango = Movimiento.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
    
    ingresos_periodo = movs_rango.aggregate(Sum('abono'))['abono__sum'] or 0
    egresos_periodo = movs_rango.aggregate(Sum('cargo'))['cargo__sum'] or 0
    balance_periodo = ingresos_periodo - egresos_periodo
    
    movimientos_ingresos_count = movs_rango.filter(abono__gt=0).count()
    movimientos_egresos_count = movs_rango.filter(cargo__gt=0).count()

    # 3. CUENTAS Y TIPO DE CAMBIO
    todas_cuentas = Cuenta.objects.all()
    
    raw_tc = obtener_tipo_cambio_banxico()
    try:
        tipo_cambio_actual = Decimal(str(raw_tc)) if raw_tc else Decimal('20.00')
    except Exception:
        tipo_cambio_actual = Decimal('20.00')

    total_mxn = sum(c.saldo_actual for c in todas_cuentas if c.moneda == 'MXN')
    total_usd = sum(c.saldo_actual for c in todas_cuentas if c.moneda == 'USD')
    total_usd_convertido = total_usd * tipo_cambio_actual
    saldo_total_consolidado = total_mxn + total_usd_convertido

    cuentas_ordenadas = sorted(todas_cuentas, key=lambda c: c.saldo_actual, reverse=True)
    
    for cuenta in cuentas_ordenadas:
        if cuenta.moneda == 'USD':
            cuenta.saldo_convertido_temp = cuenta.saldo_actual * tipo_cambio_actual
        else:
            cuenta.saldo_convertido_temp = 0
    
    cuentas_mxn = [c for c in todas_cuentas if c.moneda == 'MXN']
    cuentas_usd = [c for c in todas_cuentas if c.moneda == 'USD']

    # 4. MOVIMIENTOS RECIENTES
    movimientos_recientes = Movimiento.objects.select_related('cuenta').order_by('-fecha', '-id')[:5]

    # --- AQUÍ ESTABA EL ERROR: DEBES CREAR EL FORMULARIO ---
    importar_form = ImportarTxtForm()
    # -------------------------------------------------------

    # 5. CONTEXTO
    context = {
        'filtro_actual': filtro_tiempo,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        
        # Ahora sí existe la variable importar_form
        'importar_form': importar_form,
        
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
        'tipo_cambio': tipo_cambio_actual,
        'total_usd_convertido': total_usd_convertido, 
        'movimientos_recientes': movimientos_recientes,
    }
    return render(request, 'flujo_bancos/dashboard.html', context)

# ---------------------------------------------------------
# IMPORTAR MOVIMIENTOS (TXT)
# ---------------------------------------------------------
def importar_movimientos(request):
    if request.method == 'POST':
        form = ImportarTxtForm(request.POST, request.FILES)
        if form.is_valid():
            cuenta = form.cleaned_data['cuenta_destino']
            archivo = request.FILES['archivo_txt']
            
            # 1. Leer archivo
            try:
                decoded_file = archivo.read().decode('utf-8')
            except UnicodeDecodeError:
                archivo.seek(0)
                decoded_file = archivo.read().decode('latin-1')

            lineas = decoded_file.splitlines()
            contador_exito = 0
            errores = []

            for i, linea in enumerate(lineas, start=1):
                if not linea.strip(): continue 
                
                # Ignorar encabezados
                if "Concepto" in linea and ("Fecha" in linea or "Día" in linea):
                    continue

                # 2. Detectar separador
                if '\t' in linea:
                    datos = linea.split('\t')
                elif '|' in linea:
                    datos = linea.split('|')
                else:
                    errores.append(f"Línea {i}: Separador no detectado.")
                    continue

                if len(datos) < 4:
                    errores.append(f"Línea {i}: Faltan columnas.")
                    continue

                # 3. Extraer datos
                fecha_str = datos[0].strip()
                concepto = datos[1].strip()
                cargo_str = datos[2].strip()
                abono_str = datos[3].strip()
                
                # 4. LIMPIEZA DE NÚMEROS (USANDO DECIMAL)
                try:
                    # CORRECCIÓN AQUÍ: Usamos Decimal en lugar de float
                    cargo = Decimal(cargo_str.replace(',', '') or 0)
                    abono = Decimal(abono_str.replace(',', '') or 0)
                except Exception:
                    errores.append(f"Línea {i}: Monto inválido.")
                    continue

                # 5. Parseo de Fecha
                fecha = None
                formatos_fecha = ['%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y/%m/%d']
                
                for fmt in formatos_fecha:
                    try:
                        fecha = datetime.strptime(fecha_str, fmt).date()
                        break
                    except ValueError:
                        continue
                
                if not fecha:
                    errores.append(f"Línea {i}: Fecha inválida ({fecha_str})")
                    continue

                # 6. Guardar
                try:
                    Movimiento.objects.create(
                        cuenta=cuenta,
                        fecha=fecha,
                        concepto=concepto,
                        cargo=cargo,
                        abono=abono,
                        subcategoria=None, 
                        estatus='PENDIENTE'
                    )
                    contador_exito += 1
                except Exception as e:
                    errores.append(f"Línea {i}: Error DB ({str(e)})")

            if contador_exito > 0:
                messages.success(request, f"✅ Éxito: Se cargaron {contador_exito} movimientos.")
            
            if errores:
                msg = f"⚠️ Hubo problemas con {len(errores)} líneas. (Ej: {errores[0]})"
                messages.warning(request, msg)

            return redirect('lista_movimientos')
    
    return redirect('dashboard_bancos')

# ---------------------------------------------------------
# LISTAR TRANSFERENCIAS
# ---------------------------------------------------------
def lista_transferencias(request):
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
# CANCELAR TRANSFERENCIA
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

    if entrada:
        if entrada.comprobante:
            _eliminar_archivo_de_s3(str(entrada.comprobante))
        entrada.delete()
    
    if salida.comprobante:
        _eliminar_archivo_de_s3(str(salida.comprobante))

    salida.delete()
    
    messages.success(request, "Transferencia cancelada y archivos eliminados.")
    return redirect('lista_transferencias')

# ---------------------------------------------------------
# LISTAR MOVIMIENTOS
# ---------------------------------------------------------
def lista_movimientos(request):
    q = request.GET.get('q', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin = request.GET.get('fecha_fin', '')
    estatus_filtro = request.GET.get('estatus', '')
    
    # --- NUEVO: Obtener el filtro de auditado ---
    auditado_filtro = request.GET.get('auditado', '') 

    movimientos = Movimiento.objects.all().select_related('cuenta', 'subcategoria', 'categoria')

    if q:
        movimientos = movimientos.filter(Q(concepto__icontains=q) | Q(cuenta__nombre__icontains=q))
    if fecha_inicio:
        movimientos = movimientos.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        movimientos = movimientos.filter(fecha__lte=fecha_fin)
    if estatus_filtro:
        movimientos = movimientos.filter(estatus=estatus_filtro)
    
    # --- NUEVO: Aplicar el filtro de auditado ---
    if auditado_filtro == '1':
        movimientos = movimientos.filter(auditado=True)
    elif auditado_filtro == '0':
        movimientos = movimientos.filter(auditado=False)

    context = {
        'movimientos': movimientos,
        'importar_form': ImportarTxtForm(),
        'estatus_filtro': estatus_filtro
    }
    
    return render(request, 'flujo_bancos/lista_movimientos.html', context)
# ---------------------------------------------------------
# CREAR MOVIMIENTO
# ---------------------------------------------------------
def crear_movimiento(request):
    if request.method == 'POST':
        form = MovimientoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # DATOS DEL FORMULARIO
                    operacion = form.cleaned_data.get('operacion')
                    cuenta_destino = form.cleaned_data.get('cuenta_destino_transfer')
                    monto = form.cleaned_data.get('monto_total')
                    cuenta_origen = form.cleaned_data.get('cuenta')
                    fecha = form.cleaned_data.get('fecha')
                    concepto = form.cleaned_data.get('concepto')

                    # LÓGICA ESPECIAL: SI ES BANCO/DIVISA Y TIENE DESTINO -> ES TRANSFERENCIA
                    es_operacion_especial = operacion and ("BANCO" in operacion.nombre.upper() or "DIVISA" in operacion.nombre.upper())
                    
                    if es_operacion_especial and cuenta_destino:
                        # --- GUARDAR COMO TRANSFERENCIA ---
                        # Creamos la transferencia (Ajusta esto a tu modelo real de Transferencia)
                        # Esto normalmente crea 2 movimientos: Cargo en Origen y Abono en Destino
                        Transferencia.objects.create(
                            cuenta_origen=cuenta_origen,
                            cuenta_destino=cuenta_destino,
                            monto=monto,
                            fecha=fecha,
                            concepto=f"{concepto} ({operacion.nombre})",
                            tipo_cambio=1.0 # O lógica de TC si aplica
                        )
                        messages.success(request, f"Se registró la Transferencia por Operación: {operacion.nombre}")
                    else:
                        # --- GUARDAR COMO MOVIMIENTO NORMAL ---
                        form.save()
                        messages.success(request, "Movimiento registrado correctamente.")

                return redirect('lista_movimientos')
            except Exception as e:
                messages.error(request, f"Error al procesar: {e}")
    else:
        form = MovimientoForm(initial={'fecha': datetime.now().date()})

    return render(request, 'flujo_bancos/crear_movimiento.html', {'form': form})

# VISTA PARA EDICIÓN RÁPIDA DE SALDO (AJAX O POST NORMAL)
def actualizar_saldo_cuenta(request, pk):
    cuenta = get_object_or_404(Cuenta, pk=pk)
    if request.method == 'POST':
        nuevo_saldo = request.POST.get('saldo_inicial')
        try:
            cuenta.saldo_inicial = float(nuevo_saldo)
            cuenta.save()
            messages.success(request, f"Saldo inicial de {cuenta.nombre} actualizado.")
        except ValueError:
            messages.error(request, "Valor inválido.")
    return redirect('dashboard_bancos')

# ---------------------------------------------------------
# EDITAR MOVIMIENTO
# ---------------------------------------------------------
def editar_movimiento(request, pk):
    movimiento_original = get_object_or_404(Movimiento, pk=pk)
    
    if request.method == 'POST':
        form = MovimientoForm(request.POST, request.FILES, instance=movimiento_original)
        if form.is_valid():
            movimiento = form.save(commit=False)
            
            if 'comprobante' in request.FILES:
                if movimiento_original.comprobante:
                    _eliminar_archivo_de_s3(str(movimiento_original.comprobante))
                
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

# ---------------------------------------------------------
# CREAR TRANSFERENCIA
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

            monto_destino = monto_origen * tc

            saldo_previo_origen = origen.saldo_actual
            saldo_previo_destino = destino.saldo_actual
            
            saldo_final_origen = saldo_previo_origen - monto_origen
            saldo_final_destino = saldo_previo_destino + monto_destino

            Movimiento.objects.create(
                cuenta=origen,
                fecha=fecha,
                concepto=f"{concepto_base} (Envío a {destino.nombre})",
                cargo=monto_origen,
                abono=0,
                saldo_banco=saldo_final_origen,
                comentarios=f"Salida de fondos. TC aplicado: {tc}"
            )

            Movimiento.objects.create(
                cuenta=destino,
                fecha=fecha,
                concepto=f"{concepto_base} (Recepción de {origen.nombre})",
                cargo=0,
                abono=monto_destino,
                saldo_banco=saldo_final_destino,
                comentarios=f"Entrada de fondos. Monto original: {monto_origen} {origen.moneda}. TC: {tc}"
            )

            return redirect('dashboard_bancos')
    else:
        form = TransferenciaForm()
    
    return render(request, 'flujo_bancos/form_transferencia.html', {'form': form})

# ---------------------------------------------------------
# AJAX y OTROS
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

def ajax_obtener_tc(request):
    tc = obtener_tipo_cambio_banxico()
    return JsonResponse({'tc': tc})

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
            form.save()
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
            key = f"{settings.AWS_MEDIA_LOCATION}/{mov.comprobante}"
            s3_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': key},
                ExpiresIn=3600
            )
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

# ---------------------------------------------------------
# REPORTES EXCEL
# ---------------------------------------------------------
def exportar_movimientos_excel(request):
    # 1. CONSULTA DE DATOS (Con filtros aplicados)
    # Usamos select_related para optimizar la consulta y evitar lentitud
    movimientos = Movimiento.objects.all().select_related(
        'cuenta', 
        'unidad_negocio', 
        'operacion', 
        'categoria', 
        'subcategoria'
    ).order_by('-fecha', '-id')
    
    # --- APLICAR FILTROS (Igual que en tu lista de pantalla) ---
    q = request.GET.get('q')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    tipo = request.GET.get('tipo')
    estatus = request.GET.get('estatus') # Filtro de estatus si lo usas

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
    if estatus:
        movimientos = movimientos.filter(estatus=estatus)
    
    # 2. CREACIÓN DEL ARCHIVO EXCEL
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Reporte_Movimientos_Completo.xlsx"'
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    
    # --- ESTILOS PROFESIONALES ---
    # Encabezado azul oscuro con letras blancas
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    
    # Bordes finos para todas las celdas
    thin_border = Border(
        left=Side(style='thin'), 
        right=Side(style='thin'), 
        top=Side(style='thin'), 
        bottom=Side(style='thin')
    )
    
    center_aligned = Alignment(horizontal="center", vertical="center")
    left_aligned = Alignment(horizontal="left", vertical="center")
    
    # Formatos de número
    currency_format = '"$"#,##0.00'
    date_format = 'DD/MM/YYYY'

    # 3. DEFINICIÓN DE COLUMNAS (ORDEN EXACTO SOLICITADO)
    headers = [
        "Día",                  # Col 1
        "CUENTA",               # Col 2
        "Concepto / Referencia",# Col 3
        "Cargo",                # Col 4
        "Abono",                # Col 5
        "Saldo",                # Col 6
        "UNIDAD DE NEGOCIO",    # Col 7
        "OPERACIÓN",            # Col 8
        "CATEGORIA",            # Col 9
        "SUBCATEGORIA",         # Col 10
        "Tercero",              # Col 11
        "IVA",                  # Col 12
        "RET IVA",              # Col 13
        "RET ISR",              # Col 14
        "COMENTARIO",           # Col 15
        "ESTATUS",              # Col 16
        "AUDITADO"              # Col 17
    ]
    ws.append(headers)
    
    # Aplicar estilos a la fila de encabezados
    for col_idx, cell in enumerate(ws[1], start=1):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_aligned
        cell.border = thin_border
        # Ancho inicial sugerido (luego se ajusta)
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 15

    # 4. LLENADO DE DATOS FILA POR FILA
    row_num = 2
    for mov in movimientos:
        # Obtener valores seguros (evitar None)
        saldo_banco = mov.saldo_banco if mov.saldo_banco is not None else 0
        unidad = mov.unidad_negocio.nombre if mov.unidad_negocio else ""
        operacion = mov.operacion.nombre if mov.operacion else ""
        categoria = mov.categoria.nombre if mov.categoria else ""
        subcategoria = mov.subcategoria.nombre if mov.subcategoria else ""
        tercero = mov.tercero if mov.tercero else ""
        comentario = mov.comentarios if mov.comentarios else ""
        
        # Mapeo de la fila según el orden de encabezados
        row = [
            mov.fecha,                  # 1. Día
            mov.cuenta.nombre,          # 2. CUENTA
            mov.concepto,               # 3. Concepto
            mov.cargo,                  # 4. Cargo
            mov.abono,                  # 5. Abono
            saldo_banco,                # 6. Saldo
            unidad,                     # 7. UNIDAD
            operacion,                  # 8. OPERACIÓN
            categoria,                  # 9. CATEGORIA
            subcategoria,               # 10. SUBCATEGORIA
            tercero,                    # 11. Tercero
            mov.iva,                    # 12. IVA
            mov.ret_iva,                # 13. RET IVA
            mov.ret_isr,                # 14. RET ISR
            comentario,                 # 15. COMENTARIO
            mov.get_estatus_display(),  # 16. ESTATUS (Muestra "Pendiente" o "Terminado")
            'SI' if mov.auditado else 'NO' # 17. AUDITADO
        ]
        ws.append(row)

        # Aplicar formato a cada celda de la fila actual
        for col_idx, cell in enumerate(ws[row_num], start=1):
            cell.border = thin_border
            
            # Formato Fecha (Columna 1)
            if col_idx == 1:
                cell.number_format = date_format
                cell.alignment = center_aligned
            
            # Alineación Concepto (Columna 3) a la izquierda
            elif col_idx == 3:
                cell.alignment = left_aligned
            
            # Formato Moneda (Columnas 4, 5, 6, 12, 13, 14)
            elif col_idx in [4, 5, 6, 12, 13, 14]: 
                cell.number_format = currency_format
                cell.alignment = center_aligned # O right si prefieres
            
            # El resto centrado
            else:
                cell.alignment = center_aligned

        row_num += 1

    # 5. AJUSTE AUTOMÁTICO DE ANCHO DE COLUMNAS
    # Recorremos las columnas y ajustamos el ancho según el contenido
    for column_cells in ws.columns:
        length = max(len(str(cell.value) if cell.value else "") for cell in column_cells)
        # Un pequeño margen extra
        adjusted_width = (length + 2) * 1.1
        # Tope máximo para que no queden columnas gigantes (ej. Comentarios largos)
        if adjusted_width > 50:
            adjusted_width = 50
        ws.column_dimensions[column_cells[0].column_letter].width = adjusted_width
        
    wb.save(response)
    return response

def exportar_transferencias_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Transferencias"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    center_aligned = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    currency_format = '"$"#,##0.00_-'

    headers = [
        "Fecha", "Concepto Base", 
        "Cuenta Origen", "Saldo Inicial (Origen)", "Salida ($)", "Saldo Final (Origen)",
        "Cuenta Destino", "Saldo Inicial (Destino)", "Entrada ($)", "Saldo Final (Destino)",
        "Comentarios"
    ]
    ws.append(headers)

    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_aligned
        cell.border = thin_border

    salidas = Movimiento.objects.filter(cargo__gt=0).filter(
        Q(concepto__icontains='(Envío a') | Q(concepto__icontains='Transferencia')
    ).select_related('cuenta').order_by('-fecha', '-id')

    row_num = 2

    for salida in salidas:
        saldo_final_org = salida.saldo_banco if salida.saldo_banco is not None else 0
        saldo_inicial_org = saldo_final_org + salida.cargo

        concepto_full = salida.concepto
        concepto_base = concepto_full
        nombre_destino = "---"
        monto_entrada = 0
        saldo_final_dest = 0
        saldo_inicial_dest = 0

        match = re.search(r'\(Envío a (.*?)\)', concepto_full)
        if match:
            base_search = concepto_full.split(' (Envío a')[0]
            concepto_base = base_search
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

        row = [
            salida.fecha,
            concepto_base,
            salida.cuenta.nombre,
            saldo_inicial_org,
            salida.cargo,
            saldo_final_org,
            nombre_destino,
            saldo_inicial_dest,
            monto_entrada,
            saldo_final_dest,
            salida.comentarios
        ]
        ws.append(row)

        for col_idx, cell in enumerate(ws[row_num], start=1):
            cell.alignment = center_aligned
            cell.border = thin_border
            if col_idx in [4, 5, 6, 8, 9, 10]:
                cell.number_format = currency_format
            if col_idx == 1:
                cell.number_format = 'DD/MM/YYYY'

        row_num += 1

    for column_cells in ws.columns:
        length = max(len(str(cell.value) if cell.value else "") for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = length + 4

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Reporte_Transferencias_Pro.xlsx"'
    wb.save(response)
    return response


def gestion_categorias_view(request):
    # 1. Obtener las categorías de la base de datos
    categorias = Categoria.objects.prefetch_related('subcategorias').all().order_by('nombre')
    
    # 2. Crear los formularios vacíos
    cat_form = CategoriaForm()
    sub_form = SubCategoriaForm()
    
    # 3. DEFINIR LA VARIABLE CONTEXT (Esto es lo que faltaba)
    context = {
        'categorias': categorias,
        'cat_form': cat_form,
        'sub_form': sub_form
    }
    
    # 4. Renderizar usando el contexto
    return render(request, 'flujo_bancos/gestion_categorias.html', context)
# 2. FUNCIONES PARA CATEGORÍAS
def crear_categoria(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría creada.")
    # Asegúrate que esta línea diga 'bancos_categorias_lista'
    return redirect('bancos_categorias_lista')

def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría actualizada.")
    return redirect('bancos_categorias_lista') # <--- CAMBIO AQUÍ

def eliminar_categoria(request, pk):
    try:
        categoria = get_object_or_404(Categoria, pk=pk)
        categoria.delete()
        messages.success(request, "Categoría eliminada.")
    except Exception as e:
        messages.error(request, "No se puede eliminar porque tiene movimientos asociados.")
    return redirect('bancos_categorias_lista') # <--- CAMBIO AQUÍ

# 3. FUNCIONES PARA SUBCATEGORÍAS
def crear_subcategoria(request):
    if request.method == 'POST':
        form = SubCategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Subcategoría creada correctamente.")
    return redirect('bancos_categorias_lista')

def editar_subcategoria(request, pk):
    sub = get_object_or_404(SubCategoria, pk=pk)
    if request.method == 'POST':
        # Permitimos cambiar nombre pero preservamos la categoría si no se envía
        form = SubCategoriaForm(request.POST, instance=sub)
        if form.is_valid():
            form.save()
            messages.success(request, "Subcategoría actualizada.")
    return redirect('bancos_categorias_lista')

def eliminar_subcategoria(request, pk):
    sub = get_object_or_404(SubCategoria, pk=pk)
    sub.delete()
    messages.success(request, "Subcategoría eliminada.")
    return redirect('bancos_categorias_lista')