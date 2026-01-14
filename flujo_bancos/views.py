from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Q
from django.utils import timezone
from io import BytesIO # <--- IMPORTANTE AGREGAR ESTO
import re 
from django.db import transaction
from django.conf import settings
from decimal import Decimal
from django.core.paginator import Paginator
from datetime import datetime, timedelta
import csv
import io
import os
import requests # Necesario para Banxico si no estaba importado explícitamente

# --- IMPORTACIÓN DE SEGURIDAD ---
from django.contrib.auth.decorators import permission_required

# Importaciones de AWS S3
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

# Importaciones de Excel y XML
import openpyxl
import xml.etree.ElementTree as ET
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Importaciones locales (Modelos y Forms)
from .models import (
    Cuenta, Movimiento, SubCategoria, UnidadNegocio, 
    Operacion, Categoria, ComprobanteFiscal, Tercero
)
from .forms import (
    MovimientoForm, 
    TransferenciaForm, 
    CuentaForm, 
    TerceroForm, 
    ImportarTxtForm, 
    ImportarExcelForm, 
    ComprobanteForm,
    CategoriaForm, 
    SubCategoriaForm
)

# ---------------------------------------------------------
# UTILIDADES S3 (No requieren decorador, son internas)
# ---------------------------------------------------------
def _subir_archivo_a_s3(archivo_obj, s3_ruta_relativa):
    """
    Sube un archivo a S3.
    - `s3_ruta_relativa` es la ruta SIN 'media/' (ej: 'xmls/2024/archivo.xml').
    - Devuelve la misma ruta relativa si tiene éxito, para guardarla en la DB.
    """
    try:
        # Asegurar que el puntero esté al inicio
        archivo_obj.seek(0)
        
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

def _eliminar_archivo_de_s3(ruta_completa_s3):
    """
    Elimina un archivo de S3.
    - `ruta_completa_s3` es el nombre del campo FileField (ej: 'xmls/2024/foto.jpg').
    """
    if not ruta_completa_s3:
        return
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # Construimos la Key completa incluyendo la carpeta media
        full_key = f"{settings.AWS_MEDIA_LOCATION}/{str(ruta_completa_s3)}"
        
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=full_key
        )
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al eliminar archivo antiguo de S3: {e}")
        
def procesar_datos_xml(archivo_obj):
    """
    Lee un archivo, crea una copia en memoria (BytesIO) para no cerrar el original,
    extrae UUID, IVA y Retenciones.
    """
    datos = {
        'uuid': None, 
        'iva': Decimal('0.00'), 
        'ret_iva': Decimal('0.00'), 
        'ret_isr': Decimal('0.00')
    }
    
    try:
        # 1. Asegurar lectura desde inicio
        archivo_obj.seek(0)
        
        # 2. COPIA SEGURA EN MEMORIA
        contenido = archivo_obj.read()
        archivo_obj.seek(0) # Resetear archivo original para que Django/S3 lo pueda leer después
        
        # Stream en memoria independiente
        xml_buffer = BytesIO(contenido)
        
        # 3. Parsear
        tree = ET.parse(xml_buffer)
        root = tree.getroot()
        
        # 4. Namespaces
        ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4', 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
        if 'cfdi' not in root.tag:
            ns['cfdi'] = 'http://www.sat.gob.mx/cfd/3'

        # 5. UUID
        tfd = root.find('.//tfd:TimbreFiscalDigital', ns)
        if tfd is not None:
            datos['uuid'] = tfd.get('UUID')

        # 6. Impuestos
        impuestos_node = root.find('cfdi:Impuestos', ns)
        encontrado_global = False
        
        if impuestos_node is not None:
            total_traslados = impuestos_node.get('TotalImpuestosTrasladados')
            if total_traslados:
                datos['iva'] = Decimal(total_traslados)
                encontrado_global = True
            
            retenciones = impuestos_node.findall('cfdi:Retenciones/cfdi:Retencion', ns)
            if retenciones:
                for ret in retenciones:
                    imp = ret.get('Impuesto')
                    importe = Decimal(ret.get('Importe') or 0)
                    if imp == '002': datos['ret_iva'] += importe
                    if imp == '001': datos['ret_isr'] += importe
                encontrado_global = True

        if not encontrado_global or (datos['iva'] == 0 and datos['ret_iva'] == 0):
            conceptos = root.findall('cfdi:Conceptos/cfdi:Concepto', ns)
            for c in conceptos:
                for t in c.findall('.//cfdi:Traslado', ns):
                    if t.get('Impuesto') == '002':
                        datos['iva'] += Decimal(t.get('Importe') or 0)
                for r in c.findall('.//cfdi:Retencion', ns):
                    imp = r.get('Impuesto')
                    val = Decimal(r.get('Importe') or 0)
                    if imp == '002': datos['ret_iva'] += val
                    if imp == '001': datos['ret_isr'] += val

    except Exception as e:
        print(f"Error procesando estructura XML: {e}")
    
    return datos

def obtener_tipo_cambio_banxico():
    token = getattr(settings, 'BANXICO_API_TOKEN', None)
    
    if not token:
        # Si no hay token configurado, retornamos un valor default seguro
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
        print(f"Error consultando Banxico: {e}")
        # En caso de error de conexión o API, retornamos fallback
        return 20.50

# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
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

    importar_form = ImportarTxtForm()

    # 5. CONTEXTO
    context = {
        'filtro_actual': filtro_tiempo,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        
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
# IMPORTAR MOVIMIENTOS (EXCEL)
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def importar_movimientos(request):
    if request.method == 'POST':
        form = ImportarExcelForm(request.POST, request.FILES)
        if form.is_valid():
            cuenta = form.cleaned_data['cuenta_destino']
            archivo = request.FILES['archivo_excel']
            
            try:
                # Cargar el libro de trabajo (workbook)
                wb = openpyxl.load_workbook(archivo)
                ws = wb.active # Toma la primera hoja activa
                
                count_creados = 0
                
                # Leemos fila por fila desde la 2 (saltando encabezados)
                for row in ws.iter_rows(min_row=2, values_only=True):
                    # Asumiendo orden: FECHA | CONCEPTO | CARGO | ABONO
                    
                    fecha_raw = row[0]
                    concepto = row[1]
                    cargo_raw = row[2]
                    abono_raw = row[3]
                    
                    # Si la fila no tiene fecha, la saltamos (fila vacía)
                    if not fecha_raw:
                        continue

                    # 1. Convertimos a string primero para evitar error de float
                    # 2. Si viene vacío (None), ponemos '0'
                    str_cargo = str(cargo_raw) if cargo_raw is not None else '0'
                    str_abono = str(abono_raw) if abono_raw is not None else '0'

                    # 3. Convertimos a Decimal de Django/Python
                    cargo_decimal = Decimal(str_cargo)
                    abono_decimal = Decimal(str_abono)

                    # Evitar duplicados exactos
                    existe = Movimiento.objects.filter(
                        cuenta=cuenta,
                        fecha=fecha_raw,
                        concepto=concepto,
                        cargo=cargo_decimal,
                        abono=abono_decimal
                    ).exists()
                    
                    if not existe:
                        Movimiento.objects.create(
                            cuenta=cuenta,
                            fecha=fecha_raw,
                            concepto=concepto or "Sin concepto",
                            cargo=cargo_decimal,
                            abono=abono_decimal,
                            estatus='PENDIENTE'
                        )
                        count_creados += 1
                
                messages.success(request, f"Se cargaron {count_creados} movimientos. Orden respetado tal cual el Excel.")
                return redirect('lista_movimientos')
                
            except Exception as e:
                # Muestra el error específico si vuelve a fallar
                messages.error(request, f"Error crítico al importar: {str(e)}")
    else:
        form = ImportarExcelForm()
    
    return render(request, 'flujo_bancos/importar_movimientos.html', {'form': form})

# ---------------------------------------------------------
# CANCELAR TRANSFERENCIA
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
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
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def lista_movimientos(request):
    q = request.GET.get('q', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin = request.GET.get('fecha_fin', '')
    estatus_filtro = request.GET.get('estatus', '')
    auditado_filtro = request.GET.get('auditado', '') 

    # Consulta base
    qs = Movimiento.objects.all().select_related('cuenta', 'subcategoria', 'categoria')

    # Filtros
    if q:
        qs = qs.filter(Q(concepto__icontains=q) | Q(cuenta__nombre__icontains=q) | Q(tercero__icontains=q))
    if fecha_inicio:
        qs = qs.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__lte=fecha_fin)
    if estatus_filtro:
        qs = qs.filter(estatus=estatus_filtro)
    if auditado_filtro == '1':
        qs = qs.filter(auditado=True)
    elif auditado_filtro == '0':
        qs = qs.filter(auditado=False)

    # --- CAMBIO AQUÍ: Ordenar por fecha descendente (Mayor a Menor) ---
    qs = qs.order_by('-fecha', '-id')

    # --- PAGINACIÓN (27 FILAS) ---
    paginator = Paginator(qs, 27) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'movimientos': page_obj, 
        'importar_form': ImportarTxtForm(),
        'estatus_filtro': estatus_filtro
    }
    
    return render(request, 'flujo_bancos/lista_movimientos.html', context)

# ---------------------------------------------------------
# CREAR MOVIMIENTO
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def crear_movimiento(request):
    if request.method == 'POST':
        form = MovimientoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Guardar Movimiento Base
                    movimiento = form.save()

                    # 2. Procesar Archivos
                    archivos = request.FILES.getlist('archivos_comprobantes')
                    if archivos:
                        for archivo in archivos:
                            # Leer contenido en memoria
                            contenido_bytes = archivo.read()
                            
                            ext = os.path.splitext(archivo.name)[1].lower()
                            fecha_hoy = timezone.now()
                            # Ruta relativa sin 'media/'
                            s3_path = f"{'xmls' if ext == '.xml' else 'pdfs'}/{fecha_hoy.year}/{fecha_hoy.month}/{archivo.name}"
                            
                            nuevo_comp = ComprobanteFiscal(movimiento=movimiento)

                            # Procesar XML para obtener datos fiscales
                            if ext == '.xml':
                                datos_xml = procesar_datos_xml_desde_bytes(contenido_bytes)
                                nuevo_comp.uuid = datos_xml['uuid']
                                nuevo_comp.monto_iva = datos_xml['iva']
                                nuevo_comp.monto_ret_iva = datos_xml['ret_iva']
                                nuevo_comp.monto_ret_isr = datos_xml['ret_isr']

                            # Subir a S3 usando la función proporcionada
                            archivo_memoria = BytesIO(contenido_bytes)
                            ruta_guardada = _subir_archivo_a_s3(archivo_memoria, s3_path)
                            
                            if ruta_guardada:
                                if ext == '.xml':
                                    nuevo_comp.archivo_xml.name = ruta_guardada
                                else:
                                    nuevo_comp.archivo_pdf.name = ruta_guardada
                                
                                nuevo_comp.save()

                        # 3. Recalcular totales sumando lo que acabamos de guardar
                        recalcular_iva_movimiento(movimiento)

                    messages.success(request, "Movimiento registrado correctamente.")
                    return redirect('detalle_movimiento', pk=movimiento.pk)

            except Exception as e:
                print(f"Error al crear: {e}")
                messages.error(request, f"Error: {e}")
                return render(request, 'flujo_bancos/crear_movimiento.html', {'form': form})
    else:
        form = MovimientoForm(initial={'fecha': timezone.now().date()})

    return render(request, 'flujo_bancos/crear_movimiento.html', {'form': form})
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
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
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def editar_movimiento(request, pk):
    movimiento_original = get_object_or_404(Movimiento, pk=pk)
    
    if request.method == 'POST':
        form = MovimientoForm(request.POST, request.FILES, instance=movimiento_original)
        if form.is_valid():
            try:
                with transaction.atomic():
                    movimiento = form.save()

                    # A. Eliminar archivos
                    ids_eliminar = request.POST.get('ids_eliminar', '')
                    if ids_eliminar:
                        for comp_id in ids_eliminar.split(','):
                            if comp_id:
                                comp = ComprobanteFiscal.objects.filter(id=comp_id, movimiento=movimiento).first()
                                if comp:
                                    # Usar la función de borrado de S3
                                    if comp.archivo_xml: _eliminar_archivo_de_s3(comp.archivo_xml.name)
                                    if comp.archivo_pdf: _eliminar_archivo_de_s3(comp.archivo_pdf.name)
                                    comp.delete()

                    # B. Subir nuevos archivos
                    archivos = request.FILES.getlist('archivos_comprobantes')
                    if archivos:
                        for archivo in archivos:
                            contenido_bytes = archivo.read()
                            ext = os.path.splitext(archivo.name)[1].lower()
                            fecha_hoy = timezone.now()
                            s3_path = f"{'xmls' if ext == '.xml' else 'pdfs'}/{fecha_hoy.year}/{fecha_hoy.month}/{archivo.name}"
                            
                            nuevo_comp = ComprobanteFiscal(movimiento=movimiento)

                            if ext == '.xml':
                                datos_xml = procesar_datos_xml_desde_bytes(contenido_bytes)
                                nuevo_comp.uuid = datos_xml['uuid']
                                nuevo_comp.monto_iva = datos_xml['iva']
                                nuevo_comp.monto_ret_iva = datos_xml['ret_iva']
                                nuevo_comp.monto_ret_isr = datos_xml['ret_isr']

                            archivo_memoria = BytesIO(contenido_bytes)
                            ruta_guardada = _subir_archivo_a_s3(archivo_memoria, s3_path)
                            
                            if ruta_guardada:
                                if ext == '.xml':
                                    nuevo_comp.archivo_xml.name = ruta_guardada
                                else:
                                    nuevo_comp.archivo_pdf.name = ruta_guardada
                                nuevo_comp.save()

                    # C. Recalcular totales
                    recalcular_iva_movimiento(movimiento)

                messages.success(request, 'Movimiento actualizado correctamente.')
                return redirect('detalle_movimiento', pk=movimiento.pk)

            except Exception as e:
                messages.error(request, f"Error al editar: {e}")
                return render(request, 'flujo_bancos/crear_movimiento.html', {
                    'form': form, 'movimiento': movimiento_original
                })
    else:
        form = MovimientoForm(instance=movimiento_original)

    context = {
        'form': form,
        'movimiento': movimiento_original,
        'lista_conceptos': Movimiento.objects.values_list('concepto', flat=True).distinct()
    }
    return render(request, 'flujo_bancos/crear_movimiento.html', context)
# ---------------------------------------------------------
# CREAR TRANSFERENCIA
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
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
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def cargar_subcategorias(request):
    categoria_id = request.GET.get('categoria_id')
    subcategorias = SubCategoria.objects.filter(categoria_id=categoria_id).order_by('nombre').values('id', 'nombre')
    return JsonResponse(list(subcategorias), safe=False)

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def obtener_saldo_cuenta(request):
    cuenta_id = request.GET.get('cuenta_id')
    if cuenta_id:
        cuenta = get_object_or_404(Cuenta, id=cuenta_id)
        return JsonResponse({'saldo': cuenta.saldo_actual})
    return JsonResponse({'saldo': 0})

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def ajax_obtener_tc(request):
    tc = obtener_tipo_cambio_banxico()
    return JsonResponse({'tc': tc})

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
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
    
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def crear_tercero(request):
    if request.method == 'POST':
        form = TerceroForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'flujo_bancos/close_popup.html') 
    else:
        form = TerceroForm()
    
    return render(request, 'flujo_bancos/crear_tercero.html', {'form': form})

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def auditar_movimiento(request, pk):
    mov = get_object_or_404(Movimiento, pk=pk)
    mov.auditado = True
    mov.save()
    messages.success(request, 'Movimiento auditado y bloqueado correctamente.')
    return redirect('lista_movimientos')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def detalle_movimiento(request, pk):
    mov = get_object_or_404(Movimiento, pk=pk)
    
    # IMPORTANTE: Ya no leemos S3 aquí para evitar "Access Denied" y lentitud.
    # Confiamos en los datos guardados en la BD (ComprobanteFiscal)
    
    comprobantes = mov.comprobantes.all()
    lista_xmls = []
    
    for comp in comprobantes:
        datos = {
            'obj': comp,
            'uuid': comp.uuid or '---',
            'iva': comp.monto_iva,
            'ret_iva': comp.monto_ret_iva,
            'ret_isr': comp.monto_ret_isr,
            'es_xml': bool(comp.archivo_xml)
        }
        lista_xmls.append(datos)
        
    totales = {
        'iva': mov.iva,
        'ret_iva': mov.ret_iva,
        'ret_isr': mov.ret_isr
    }

    context = {
        'mov': mov,
        'lista_xmls': lista_xmls,
        'totales_xml': totales
    }
    return render(request, 'flujo_bancos/detalle_movimiento.html', context)

# ---------------------------------------------------------
# REPORTES EXCEL
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def exportar_movimientos_excel(request):
    # 1. CONSULTA DE DATOS (Con filtros aplicados)
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
    estatus = request.GET.get('estatus')

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
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin'), 
        right=Side(style='thin'), 
        top=Side(style='thin'), 
        bottom=Side(style='thin')
    )
    
    center_aligned = Alignment(horizontal="center", vertical="center")
    left_aligned = Alignment(horizontal="left", vertical="center")
    
    currency_format = '"$"#,##0.00'
    date_format = 'DD/MM/YYYY'

    # 3. DEFINICIÓN DE COLUMNAS
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
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 15

    # 4. LLENADO DE DATOS FILA POR FILA
    row_num = 2
    for mov in movimientos:
        saldo_banco = mov.saldo_banco if mov.saldo_banco is not None else 0
        unidad = mov.unidad_negocio.nombre if mov.unidad_negocio else ""
        operacion = mov.operacion.nombre if mov.operacion else ""
        categoria = mov.categoria.nombre if mov.categoria else ""
        subcategoria = mov.subcategoria.nombre if mov.subcategoria else ""
        tercero = mov.tercero if mov.tercero else ""
        comentario = mov.comentarios if mov.comentarios else ""
        
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
            mov.get_estatus_display(),  # 16. ESTATUS
            'SI' if mov.auditado else 'NO' # 17. AUDITADO
        ]
        ws.append(row)

        for col_idx, cell in enumerate(ws[row_num], start=1):
            cell.border = thin_border
            
            if col_idx == 1:
                cell.number_format = date_format
                cell.alignment = center_aligned
            elif col_idx == 3:
                cell.alignment = left_aligned
            elif col_idx in [4, 5, 6, 12, 13, 14]: 
                cell.number_format = currency_format
                cell.alignment = center_aligned
            else:
                cell.alignment = center_aligned

        row_num += 1

    # 5. AJUSTE AUTOMÁTICO DE ANCHO
    for column_cells in ws.columns:
        length = max(len(str(cell.value) if cell.value else "") for cell in column_cells)
        adjusted_width = (length + 2) * 1.1
        if adjusted_width > 50:
            adjusted_width = 50
        ws.column_dimensions[column_cells[0].column_letter].width = adjusted_width
        
    wb.save(response)
    return response

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
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
    ).select_related('cuenta').order_by('fecha', 'id')

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

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def gestion_categorias_view(request):
    # 1. Obtener las categorías de la base de datos
    categorias = Categoria.objects.prefetch_related('subcategorias').all().order_by('nombre')
    
    # 2. Crear los formularios vacíos
    cat_form = CategoriaForm()
    sub_form = SubCategoriaForm()
    
    # 3. DEFINIR LA VARIABLE CONTEXT
    context = {
        'categorias': categorias,
        'cat_form': cat_form,
        'sub_form': sub_form
    }
    
    # 4. Renderizar usando el contexto
    return render(request, 'flujo_bancos/gestion_categorias.html', context)

# 2. FUNCIONES PARA CATEGORÍAS
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def crear_categoria(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría creada.")
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría actualizada.")
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_categoria(request, pk):
    try:
        categoria = get_object_or_404(Categoria, pk=pk)
        categoria.delete()
        messages.success(request, "Categoría eliminada.")
    except Exception as e:
        messages.error(request, "No se puede eliminar porque tiene movimientos asociados.")
    return redirect('bancos_categorias_lista')

# 3. FUNCIONES PARA SUBCATEGORÍAS
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def crear_subcategoria(request):
    if request.method == 'POST':
        form = SubCategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Subcategoría creada correctamente.")
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def editar_subcategoria(request, pk):
    sub = get_object_or_404(SubCategoria, pk=pk)
    if request.method == 'POST':
        # Permitimos cambiar nombre pero preservamos la categoría si no se envía
        form = SubCategoriaForm(request.POST, instance=sub)
        if form.is_valid():
            form.save()
            messages.success(request, "Subcategoría actualizada.")
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_subcategoria(request, pk):
    sub = get_object_or_404(SubCategoria, pk=pk)
    sub.delete()
    messages.success(request, "Subcategoría eliminada.")
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_movimiento(request, pk):
    mov = get_object_or_404(Movimiento, pk=pk)

    # 1. Seguridad: No borrar si ya está auditado
    if mov.auditado:
        messages.error(request, "No es posible eliminar un movimiento que ya ha sido auditado.")
        return redirect('lista_movimientos')

    # 2. Limpieza S3: Borrar archivo adjunto si existe
    if mov.comprobante:
        try:
            _eliminar_archivo_de_s3(str(mov.comprobante))
        except Exception as e:
            print(f"Advertencia: No se pudo borrar archivo S3: {e}")

    # 3. Borrar registro
    mov.delete()
    messages.success(request, "El movimiento ha sido eliminado correctamente.")
    return redirect('lista_movimientos')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def lista_transferencias(request):
    transferencias = Movimiento.objects.filter(
        cargo__gt=0
    ).filter(
        Q(concepto__icontains='(Envío a') | Q(concepto__icontains='Transferencia')
    ).select_related('cuenta').order_by('-fecha', '-id') # <--- CAMBIO AQUÍ: '-fecha'

    paginator = Paginator(transferencias, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'transferencias': page_obj,
    }
    return render(request, 'flujo_bancos/lista_transferencias.html', context)

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def subir_comprobante(request, movimiento_id):
    movimiento = get_object_or_404(Movimiento, pk=movimiento_id)
    
    if request.method == 'POST':
        form = ComprobanteForm(request.POST, request.FILES)
        if form.is_valid():
            comprobante = form.save(commit=False)
            comprobante.movimiento = movimiento
            
            # Procesar XML
            if 'archivo_xml' in request.FILES:
                f = request.FILES['archivo_xml']
                contenido_bytes = f.read()
                
                fecha_hoy = timezone.now()
                path = f"xmls/{fecha_hoy.year}/{fecha_hoy.month}/{f.name}"
                
                # Datos fiscales
                datos = procesar_datos_xml_desde_bytes(contenido_bytes)
                comprobante.uuid = datos['uuid']
                comprobante.monto_iva = datos['iva']
                comprobante.monto_ret_iva = datos['ret_iva']
                comprobante.monto_ret_isr = datos['ret_isr']
                
                # Subir S3
                memoria = BytesIO(contenido_bytes)
                ruta = _subir_archivo_a_s3(memoria, path)
                if ruta: comprobante.archivo_xml.name = ruta

            # Procesar PDF
            if 'archivo_pdf' in request.FILES:
                f = request.FILES['archivo_pdf']
                contenido_bytes = f.read()
                fecha_hoy = timezone.now()
                path = f"pdfs/{fecha_hoy.year}/{fecha_hoy.month}/{f.name}"
                
                memoria = BytesIO(contenido_bytes)
                ruta = _subir_archivo_a_s3(memoria, path)
                if ruta: comprobante.archivo_pdf.name = ruta

            comprobante.save()
            recalcular_iva_movimiento(movimiento)
            
            messages.success(request, "Comprobante subido y procesado.")
            return redirect('detalle_movimiento', pk=movimiento.pk)
    return redirect('detalle_movimiento', pk=movimiento.pk)
    
def recalcular_iva_movimiento(movimiento):
    """ Suma impuestos de TODOS los comprobantes y actualiza el Movimiento """
    comps = movimiento.comprobantes.all()
    
    total_iva = sum(c.monto_iva for c in comps)
    total_ret_iva = sum(c.monto_ret_iva for c in comps)
    total_ret_isr = sum(c.monto_ret_isr for c in comps)
    
    movimiento.iva = total_iva
    movimiento.ret_iva = total_ret_iva
    movimiento.ret_isr = total_ret_isr
    movimiento.iva_total_xml = total_iva
    
    movimiento.save()
    movimiento.save()

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_comprobante(request, comprobante_id):
    comp = get_object_or_404(ComprobanteFiscal, pk=comprobante_id)
    mov_id = comp.movimiento.pk
    
    # Eliminar de S3 usando la función segura
    if comp.archivo_xml: _eliminar_archivo_de_s3(comp.archivo_xml.name)
    if comp.archivo_pdf: _eliminar_archivo_de_s3(comp.archivo_pdf.name)
    
    comp.delete()
    
    # Recalcular movimiento padre
    recalcular_iva_movimiento(Movimiento.objects.get(pk=mov_id))
    
    messages.success(request, "Comprobante eliminado.")
    return redirect('detalle_movimiento', pk=mov_id)


def procesar_datos_xml_desde_bytes(contenido_bytes):
    """
    Recibe el contenido RAW (bytes) del archivo.
    Extrae UUID, IVA y Retenciones buscando en Globales y Conceptos.
    """
    datos = {
        'uuid': None, 
        'iva': Decimal('0.00'), 
        'ret_iva': Decimal('0.00'), 
        'ret_isr': Decimal('0.00')
    }
    
    try:
        # Crear un stream en memoria exclusivo para el parser XML
        xml_buffer = BytesIO(contenido_bytes)
        
        tree = ET.parse(xml_buffer)
        root = tree.getroot()
        
        # Namespaces
        ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4', 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
        if 'cfdi' not in root.tag: ns['cfdi'] = 'http://www.sat.gob.mx/cfd/3'

        # 1. UUID
        tfd = root.find('.//tfd:TimbreFiscalDigital', ns)
        if tfd is not None:
            datos['uuid'] = tfd.get('UUID')

        # 2. Impuestos Globales (Prioridad 1)
        impuestos_node = root.find('cfdi:Impuestos', ns)
        encontrado_global = False
        
        if impuestos_node is not None:
            total_traslados = impuestos_node.get('TotalImpuestosTrasladados')
            if total_traslados:
                datos['iva'] = Decimal(total_traslados)
                encontrado_global = True
            
            retenciones = impuestos_node.findall('cfdi:Retenciones/cfdi:Retencion', ns)
            if retenciones:
                for ret in retenciones:
                    imp = ret.get('Impuesto')
                    importe = Decimal(ret.get('Importe') or 0)
                    if imp == '002': datos['ret_iva'] += importe
                    if imp == '001': datos['ret_isr'] += importe
                encontrado_global = True

        # 3. Fallback Conceptos (Si no hay globales o faltan datos)
        # Buscar IVA si es 0
        if datos['iva'] == 0:
            conceptos = root.findall('cfdi:Conceptos/cfdi:Concepto', ns)
            for c in conceptos:
                for t in c.findall('.//cfdi:Traslado', ns):
                    if t.get('Impuesto') == '002':
                        datos['iva'] += Decimal(t.get('Importe') or 0)
        
        # Buscar Retenciones si son 0
        if datos['ret_iva'] == 0 and datos['ret_isr'] == 0:
            conceptos = root.findall('cfdi:Conceptos/cfdi:Concepto', ns)
            for c in conceptos:
                for r in c.findall('.//cfdi:Retencion', ns):
                    imp = r.get('Impuesto')
                    val = Decimal(r.get('Importe') or 0)
                    if imp == '002': datos['ret_iva'] += val
                    if imp == '001': datos['ret_isr'] += val

    except Exception as e:
        print(f"Error procesando XML bytes: {e}")
    
    return datos