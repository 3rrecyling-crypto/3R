from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Q
from django.utils import timezone
from io import BytesIO 
import re 
from django.db import transaction
from django.conf import settings
from decimal import Decimal
from django.core.paginator import Paginator
from datetime import datetime, timedelta
import csv
import io
import os
import requests 

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
    SubCategoriaForm,
    ActualizarSaldoForm
)

# ---------------------------------------------------------
# UTILIDADES S3 (Internas)
# ---------------------------------------------------------
def _subir_archivo_a_s3(archivo_obj, s3_ruta_relativa):
    """ Sube un archivo a S3 manualmente. """
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
    """ Elimina un archivo de S3 usando la ruta relativa. """
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
# PROCESAMIENTO XML (Lógica Fiscal)
# ---------------------------------------------------------
def procesar_datos_xml(archivo_obj):
    """
    Lee un archivo XML y retorna un diccionario con UUID, IVA, Ret IVA y Ret ISR.
    Maneja CFDI 3.3 y 4.0 correctamente.
    """
    datos = {
        'uuid': None, 
        'iva': Decimal('0.00'), 
        'ret_iva': Decimal('0.00'), 
        'ret_isr': Decimal('0.00')
    }
    
    try:
        # Importante: Regresar el puntero al inicio
        archivo_obj.seek(0)
        
        tree = ET.parse(archivo_obj)
        root = tree.getroot()
        
        # Namespaces del SAT (CFDI 4.0 por defecto)
        ns = {
            'cfdi': 'http://www.sat.gob.mx/cfd/4', 
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
        }
        
        # Detección automática de CFDI 3.3
        # Buscamos la URL del namespace 3.3 dentro de la etiqueta raíz
        if 'http://www.sat.gob.mx/cfd/3' in root.tag: 
            ns['cfdi'] = 'http://www.sat.gob.mx/cfd/3'

        # A) Extraer UUID
        tfd = root.find('.//tfd:TimbreFiscalDigital', ns)
        if tfd is not None:
            datos['uuid'] = tfd.get('UUID')

        # B) Extraer Impuestos (Globales)
        impuestos_node = root.find('cfdi:Impuestos', ns)
        encontrado_global = False
        
        if impuestos_node is not None:
            # IVA Trasladado Total
            traslados_totales = impuestos_node.get('TotalImpuestosTrasladados')
            if traslados_totales:
                datos['iva'] = Decimal(traslados_totales)
                encontrado_global = True
            
            # Retenciones Globales
            retenciones = impuestos_node.findall('cfdi:Retenciones/cfdi:Retencion', ns)
            if retenciones:
                for ret in retenciones:
                    imp = ret.get('Impuesto')
                    importe = Decimal(ret.get('Importe') or 0)
                    if imp == '002': datos['ret_iva'] += importe # 002 = IVA
                    if imp == '001': datos['ret_isr'] += importe # 001 = ISR
                encontrado_global = True

        # C) Fallback: Si no hay globales, sumar concepto por concepto
        if not encontrado_global or (datos['iva'] == 0 and datos['ret_iva'] == 0):
            conceptos = root.findall('cfdi:Conceptos/cfdi:Concepto', ns)
            for c in conceptos:
                # Traslados (IVA)
                for t in c.findall('.//cfdi:Traslado', ns):
                    if t.get('Impuesto') == '002':
                        datos['iva'] += Decimal(t.get('Importe') or 0)
                
                # Retenciones
                for r in c.findall('.//cfdi:Retencion', ns):
                    imp = r.get('Impuesto')
                    val = Decimal(r.get('Importe') or 0)
                    if imp == '002': datos['ret_iva'] += val
                    if imp == '001': datos['ret_isr'] += val
                    
    except Exception as e:
        print(f"Error procesando estructura XML: {e}")
    
    return datos

def recalcular_iva_movimiento(movimiento):
    """
    Suma los impuestos de TODOS los comprobantes hijos y actualiza
    los campos totales en el modelo Movimiento.
    """
    comps = movimiento.comprobantes.all()
    
    # Sumar campos individuales de los comprobantes
    total_iva = sum(c.monto_iva for c in comps)
    total_ret_iva = sum(c.monto_ret_iva for c in comps)
    total_ret_isr = sum(c.monto_ret_isr for c in comps)
    
    # Actualizar Movimiento
    movimiento.iva = total_iva
    movimiento.ret_iva = total_ret_iva
    movimiento.ret_isr = total_ret_isr
    
    # Campo extra si lo usas para visualización rápida
    movimiento.iva_total_xml = total_iva
    
    movimiento.save()

# ---------------------------------------------------------
# UTILIDADES BANXICO
# ---------------------------------------------------------
def obtener_tipo_cambio_banxico():
    token = getattr(settings, 'BANXICO_API_TOKEN', None)
    
    if not token:
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
        return 20.50

# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def dashboard(request):
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

    movs_rango = Movimiento.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
    
    ingresos_periodo = movs_rango.aggregate(Sum('abono'))['abono__sum'] or 0
    egresos_periodo = movs_rango.aggregate(Sum('cargo'))['cargo__sum'] or 0
    balance_periodo = ingresos_periodo - egresos_periodo
    
    movimientos_ingresos_count = movs_rango.filter(abono__gt=0).count()
    movimientos_egresos_count = movs_rango.filter(cargo__gt=0).count()

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

    movimientos_recientes = Movimiento.objects.select_related('cuenta').order_by('-fecha', '-id')[:5]

    importar_form = ImportarTxtForm()

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
# IMPORTAR MOVIMIENTOS
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def importar_movimientos(request):
    if request.method == 'POST':
        form = ImportarExcelForm(request.POST, request.FILES)
        if form.is_valid():
            cuenta = form.cleaned_data['cuenta_destino']
            archivo = request.FILES['archivo_excel']
            
            try:
                wb = openpyxl.load_workbook(archivo)
                ws = wb.active 
                count_creados = 0
                
                for row in ws.iter_rows(min_row=2, values_only=True):
                    fecha_raw = row[0]
                    concepto = row[1]
                    cargo_raw = row[2]
                    abono_raw = row[3]
                    
                    if not fecha_raw:
                        continue

                    str_cargo = str(cargo_raw) if cargo_raw is not None else '0'
                    str_abono = str(abono_raw) if abono_raw is not None else '0'

                    cargo_decimal = Decimal(str_cargo)
                    abono_decimal = Decimal(str_abono)

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
                
                messages.success(request, f"Se cargaron {count_creados} movimientos.")
                return redirect('lista_movimientos')
                
            except Exception as e:
                messages.error(request, f"Error crítico al importar: {str(e)}")
    else:
        form = ImportarExcelForm()
    
    return render(request, 'flujo_bancos/importar_movimientos.html', {'form': form})

# ---------------------------------------------------------
# TRANSFERENCIAS
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
    messages.success(request, "Transferencia cancelada.")
    return redirect('lista_transferencias')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def lista_movimientos(request):
    q = request.GET.get('q', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin = request.GET.get('fecha_fin', '')
    estatus_filtro = request.GET.get('estatus', '')
    auditado_filtro = request.GET.get('auditado', '') 

    qs = Movimiento.objects.all().select_related('cuenta', 'subcategoria', 'categoria')

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

    # Orden descendente
    qs = qs.order_by('-fecha', '-id')

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
# CREAR MOVIMIENTO (CRUD)
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def crear_movimiento(request):
    if request.method == 'POST':
        form = MovimientoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    movimiento = form.save(commit=False)
                    
                    operacion = form.cleaned_data.get('operacion')
                    cuenta_destino = form.cleaned_data.get('cuenta_destino_transfer')
                    es_operacion_especial = operacion and ("BANCO" in operacion.nombre.upper() or "DIVISA" in operacion.nombre.upper())
                    
                    if es_operacion_especial and cuenta_destino:
                        pass # Tu lógica de transferencia especial aquí
                    
                    movimiento.save()

                    archivos = request.FILES.getlist('archivos_comprobantes')
                    if archivos:
                        for archivo in archivos:
                            ext = os.path.splitext(archivo.name)[1].lower()
                            fecha_hoy = timezone.now()
                            tipo_carpeta = 'xmls' if ext == '.xml' else 'pdfs'
                            s3_path = f"{tipo_carpeta}/{fecha_hoy.year}/{fecha_hoy.month}/{archivo.name}"
                            
                            ruta_s3 = _subir_archivo_a_s3(archivo, s3_path)
                            
                            if ruta_s3:
                                nuevo_comp = ComprobanteFiscal(movimiento=movimiento)
                                if ext == '.xml':
                                    nuevo_comp.archivo_xml.name = ruta_s3
                                    # Procesar y guardar datos
                                    datos_xml = procesar_datos_xml(archivo)
                                    nuevo_comp.uuid = datos_xml['uuid']
                                    nuevo_comp.monto_iva = datos_xml['iva']
                                    nuevo_comp.monto_ret_iva = datos_xml['ret_iva']
                                    nuevo_comp.monto_ret_isr = datos_xml['ret_isr']
                                elif ext == '.pdf':
                                    nuevo_comp.archivo_pdf.name = ruta_s3
                                
                                nuevo_comp.save()

                        recalcular_iva_movimiento(movimiento)

                    messages.success(request, "Movimiento registrado.")
                    return redirect('detalle_movimiento', pk=movimiento.pk)

            except Exception as e:
                messages.error(request, f"Error: {e}")
                return render(request, 'flujo_bancos/crear_movimiento.html', {'form': form})
    else:
        form = MovimientoForm(initial={'fecha': datetime.now().date()})

    return render(request, 'flujo_bancos/crear_movimiento.html', {'form': form})

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def actualizar_saldo_cuenta(request, pk):
    cuenta = get_object_or_404(Cuenta, pk=pk)
    if request.method == 'POST':
        nuevo_saldo = request.POST.get('saldo_inicial')
        try:
            cuenta.saldo_inicial = float(nuevo_saldo)
            cuenta.save()
            messages.success(request, f"Saldo inicial actualizado.")
        except ValueError:
            messages.error(request, "Valor inválido.")
    return redirect('dashboard_bancos')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def editar_movimiento(request, pk):
    movimiento_original = get_object_or_404(Movimiento, pk=pk)
    
    if request.method == 'POST':
        form = MovimientoForm(request.POST, request.FILES, instance=movimiento_original)
        if form.is_valid():
            movimiento = form.save(commit=False)
            movimiento.save() 

            # A. Eliminar archivos
            ids_eliminar = request.POST.get('ids_eliminar', '')
            if ids_eliminar:
                for comp_id in ids_eliminar.split(','):
                    if comp_id:
                        comp = ComprobanteFiscal.objects.filter(id=comp_id, movimiento=movimiento).first()
                        if comp:
                            if comp.archivo_xml: _eliminar_archivo_de_s3(comp.archivo_xml.name)
                            if comp.archivo_pdf: _eliminar_archivo_de_s3(comp.archivo_pdf.name)
                            comp.delete()

            # B. Subir nuevos
            archivos = request.FILES.getlist('archivos_comprobantes')
            if archivos:
                for archivo in archivos:
                    ext = os.path.splitext(archivo.name)[1].lower()
                    fecha_hoy = timezone.now()
                    tipo_carpeta = 'xmls' if ext == '.xml' else 'pdfs'
                    s3_path = f"{tipo_carpeta}/{fecha_hoy.year}/{fecha_hoy.month}/{archivo.name}"
                    
                    ruta_s3 = _subir_archivo_a_s3(archivo, s3_path)
                    
                    if ruta_s3:
                        nuevo_comp = ComprobanteFiscal(movimiento=movimiento)
                        if ext == '.xml':
                            nuevo_comp.archivo_xml.name = ruta_s3
                            # Procesar datos
                            datos_xml = procesar_datos_xml(archivo)
                            nuevo_comp.uuid = datos_xml['uuid']
                            nuevo_comp.monto_iva = datos_xml['iva']
                            nuevo_comp.monto_ret_iva = datos_xml['ret_iva']
                            nuevo_comp.monto_ret_isr = datos_xml['ret_isr']
                        elif ext == '.pdf':
                            nuevo_comp.archivo_pdf.name = ruta_s3
                        
                        nuevo_comp.save()

            recalcular_iva_movimiento(movimiento)
            messages.success(request, 'Movimiento actualizado correctamente.')
            return redirect('detalle_movimiento', pk=movimiento.pk)
    else:
        form = MovimientoForm(instance=movimiento_original)

    context = {
        'form': form,
        'movimiento': movimiento_original,
        'lista_conceptos': Movimiento.objects.values_list('concepto', flat=True).distinct()
    }
    return render(request, 'flujo_bancos/crear_movimiento.html', context)

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
                comentarios=f"Salida. TC: {tc}"
            )

            Movimiento.objects.create(
                cuenta=destino,
                fecha=fecha,
                concepto=f"{concepto_base} (Recepción de {origen.nombre})",
                cargo=0,
                abono=monto_destino,
                saldo_banco=saldo_final_destino,
                comentarios=f"Entrada. Origen: {monto_origen} {origen.moneda}. TC: {tc}"
            )

            return redirect('dashboard_bancos')
    else:
        form = TransferenciaForm()
    
    return render(request, 'flujo_bancos/form_transferencia.html', {'form': form})

# ---------------------------------------------------------
# AJAX
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
        return JsonResponse({'saldo': cuenta.saldo_actual, 'saldo_inicial': cuenta.saldo_inicial})
    return JsonResponse({'saldo': 0, 'saldo_inicial': 0})

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def ajax_obtener_tc(request):
    tc = obtener_tipo_cambio_banxico()
    return JsonResponse({'tc': tc})

# ---------------------------------------------------------
# OTROS CRUDs
# ---------------------------------------------------------
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
    messages.success(request, 'Movimiento auditado.')
    return redirect('lista_movimientos')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def detalle_movimiento(request, pk):
    mov = get_object_or_404(Movimiento, pk=pk)
    comprobantes = mov.comprobantes.all()

    # Optimizado: Leer directo de BD en lugar de S3
    lista_xmls = []
    
    for comp in comprobantes:
        datos = {
            'obj': comp,
            'uuid': comp.uuid or '---',
            'iva': comp.monto_iva,
            'ret_iva': comp.monto_ret_iva, # Leemos de la BD
            'ret_isr': comp.monto_ret_isr, # Leemos de la BD
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

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_comprobante(request, comprobante_id):
    comp = get_object_or_404(ComprobanteFiscal, pk=comprobante_id)
    mov_id = comp.movimiento.pk
    
    if comp.archivo_xml: _eliminar_archivo_de_s3(comp.archivo_xml.name)
    if comp.archivo_pdf: _eliminar_archivo_de_s3(comp.archivo_pdf.name)
    
    comp.delete()
    recalcular_iva_movimiento(Movimiento.objects.get(pk=mov_id))
    
    messages.success(request, "Comprobante eliminado.")
    return redirect('detalle_movimiento', pk=mov_id)

# ---------------------------------------------------------
# EXPORTACIÓN EXCEL
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def exportar_movimientos_excel(request):
    movimientos = Movimiento.objects.all().select_related(
        'cuenta', 'unidad_negocio', 'operacion', 
        'categoria', 'subcategoria'
   ).order_by('-fecha', '-id')
    
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
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Reporte_Movimientos.xlsx"'
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    center_aligned = Alignment(horizontal="center", vertical="center")
    
    headers = [
        "Día", "CUENTA", "Concepto", "Cargo", "Abono", "Saldo",
        "UNIDAD", "OPERACIÓN", "CATEGORIA", "SUBCATEGORIA", 
        "Tercero", "IVA", "RET IVA", "RET ISR", "COMENTARIO", "ESTATUS", "AUDITADO"
    ]
    ws.append(headers)
    
    for col_idx, cell in enumerate(ws[1], start=1):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_aligned
    
    for mov in movimientos:
        saldo = mov.saldo_banco if mov.saldo_banco else 0
        row = [
            mov.fecha, mov.cuenta.nombre, mov.concepto, mov.cargo, mov.abono, saldo,
            str(mov.unidad_negocio or ""), str(mov.operacion or ""), 
            str(mov.categoria or ""), str(mov.subcategoria or ""), 
            mov.tercero, mov.iva, mov.ret_iva, mov.ret_isr,
            mov.comentarios, mov.estatus, 'SI' if mov.auditado else 'NO'
        ]
        ws.append(row)
        
    wb.save(response)
    return response

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def exportar_transferencias_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transferencias"
    
    # (Lógica simplificada para exportar transferencias igual que antes)
    headers = ["Fecha", "Concepto", "Origen", "Destino", "Monto"]
    ws.append(headers)
    
    salidas = Movimiento.objects.filter(cargo__gt=0).filter(Q(concepto__icontains='Transferencia')).order_by('-fecha')
    for s in salidas:
        ws.append([s.fecha, s.concepto, s.cuenta.nombre, "", s.cargo])
        
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Transferencias.xlsx"'
    wb.save(response)
    return response

# ---------------------------------------------------------
# CATEGORÍAS (CRUD Simple)
# ---------------------------------------------------------
@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def gestion_categorias_view(request):
    categorias = Categoria.objects.prefetch_related('subcategorias').all().order_by('nombre')
    context = {'categorias': categorias, 'cat_form': CategoriaForm(), 'sub_form': SubCategoriaForm()}
    return render(request, 'flujo_bancos/gestion_categorias.html', context)

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def crear_categoria(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def editar_categoria(request, pk):
    cat = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        form = CategoriaForm(request.POST, instance=cat)
        if form.is_valid(): form.save()
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_categoria(request, pk):
    cat = get_object_or_404(Categoria, pk=pk)
    cat.delete()
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def crear_subcategoria(request):
    if request.method == 'POST':
        form = SubCategoriaForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def editar_subcategoria(request, pk):
    sub = get_object_or_404(SubCategoria, pk=pk)
    if request.method == 'POST':
        form = SubCategoriaForm(request.POST, instance=sub)
        if form.is_valid(): form.save()
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_subcategoria(request, pk):
    sub = get_object_or_404(SubCategoria, pk=pk)
    sub.delete()
    return redirect('bancos_categorias_lista')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def eliminar_movimiento(request, pk):
    mov = get_object_or_404(Movimiento, pk=pk)
    if mov.auditado:
        messages.error(request, "Movimiento auditado no se puede borrar.")
        return redirect('lista_movimientos')
    
    if mov.comprobante: _eliminar_archivo_de_s3(str(mov.comprobante))
    mov.delete()
    messages.success(request, "Movimiento eliminado.")
    return redirect('lista_movimientos')

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def lista_transferencias(request):
    transferencias = Movimiento.objects.filter(cargo__gt=0).filter(
        Q(concepto__icontains='(Envío a') | Q(concepto__icontains='Transferencia')
    ).select_related('cuenta').order_by('-fecha', '-id')

    paginator = Paginator(transferencias, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'flujo_bancos/lista_transferencias.html', {'transferencias': page_obj})

@permission_required('flujo_bancos.acceso_flujo_bancos', raise_exception=True)
def subir_comprobante(request, movimiento_id):
    movimiento = get_object_or_404(Movimiento, pk=movimiento_id)
    if request.method == 'POST':
        form = ComprobanteForm(request.POST, request.FILES)
        if form.is_valid():
            comp = form.save(commit=False)
            comp.movimiento = movimiento
            
            if 'archivo_xml' in request.FILES:
                f = request.FILES['archivo_xml']
                path = f"xmls/{timezone.now().year}/{timezone.now().month}/{f.name}"
                ruta = _subir_archivo_a_s3(f, path)
                if ruta:
                    comp.archivo_xml.name = ruta
                    datos = procesar_datos_xml(f)
                    comp.uuid = datos['uuid']
                    comp.monto_iva = datos['iva']
                    comp.monto_ret_iva = datos['ret_iva']
                    comp.monto_ret_isr = datos['ret_isr']

            if 'archivo_pdf' in request.FILES:
                f = request.FILES['archivo_pdf']
                path = f"pdfs/{timezone.now().year}/{timezone.now().month}/{f.name}"
                ruta = _subir_archivo_a_s3(f, path)
                if ruta: comp.archivo_pdf.name = ruta

            comp.save()
            recalcular_iva_movimiento(movimiento)
            messages.success(request, "Comprobante subido.")
            return redirect('detalle_movimiento', pk=movimiento.pk)
    return redirect('detalle_movimiento', pk=movimiento.pk)