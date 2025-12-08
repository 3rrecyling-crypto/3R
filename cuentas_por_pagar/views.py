from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q, Sum
from .models import Factura, Pago
from .forms import FacturaForm, PagoForm
from compras.models import OrdenCompra
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required  # <-- AÑADE ESTE IMPORT
from openpyxl import Workbook  # Para exportar Excel
# cuentas_por_pagar/views.py - AGREGA AL INICIO DEL ARCHIVO
from django import forms  # ← Agrega este import
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.contrib.auth.decorators import permission_required, login_required
from django.contrib.auth.mixins import PermissionRequiredMixin


# ==============================================================================
# === FUNCIONES AUXILIARES PARA GESTIONAR ARCHIVOS EN S3 (COMO EN TERNIUM) ===
# ==============================================================================

def _subir_archivo_a_s3(archivo_obj, s3_ruta_relativa):
    """
    Sube un archivo a S3.
    - `s3_ruta_relativa` es la ruta SIN 'media/' (ej: 'comprobantes_pago/factura123.pdf').
    - Devuelve la misma ruta relativa si tiene éxito, para guardarla en la DB.
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

def _eliminar_archivo_de_s3(ruta_completa_s3):
    """
    Elimina un archivo de S3.
    - `ruta_completa_s3` es la ruta que Django provee (ej: 'media/comprobantes/factura123.pdf'),
      que es lo que Boto3 necesita como 'Key'.
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
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=str(ruta_completa_s3)
        )
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al eliminar archivo antiguo de S3: {e}")

class FacturaListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'cuentas_por_pagar.acceso_cxp'
    model = Factura
    template_name = 'cuentas_por_pagar/factura_list.html'
    context_object_name = 'facturas'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related('orden_compra__proveedor', 'orden_compra__empresa')
        query = self.request.GET.get('q')
        estatus = self.request.GET.get('estatus')
        if query:
            queryset = queryset.filter(
                Q(numero_factura__icontains=query) |
                Q(orden_compra__folio__icontains=query)
            )
        if estatus:
            queryset = queryset.filter(estatus=estatus)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['estatus_choices'] = Factura.ESTATUS_CHOICES
        
        # Agregar estadísticas para los KPIs
        queryset = self.get_queryset()
        context['total_facturas_count'] = Factura.objects.count()  # Total en BD
        context['facturas_filtradas_count'] = queryset.count()     # Total después de filtros
        
        return context

class FacturaCreateView(LoginRequiredMixin, CreateView):
    def get(self, request, *args, **kwargs):
        messages.warning(request, "La creación manual de facturas está deshabilitada. Las facturas se generan automáticamente cuando se aprueban las órdenes de compra.")
        return redirect('lista_facturas')
    
    def post(self, request, *args, **kwargs):
        messages.warning(request, "La creación manual de facturas está deshabilitada.")
        return redirect('lista_facturas')

class FacturaUpdateView(LoginRequiredMixin, UpdateView):
    model = Factura
    form_class = FacturaForm
    template_name = 'cuentas_por_pagar/generic_form.html'
    success_url = reverse_lazy('lista_facturas')
    
    def form_valid(self, form):
        factura_original = self.get_object()
        self.object = form.save(commit=False)
        
        # Lógica para actualizar archivo de factura en S3
        if 'archivo_factura' in self.request.FILES:
            # Eliminar archivo antiguo
            if factura_original.archivo_factura and hasattr(factura_original.archivo_factura, 'name'):
                _eliminar_archivo_de_s3(factura_original.archivo_factura.name)
            
            # Subir nuevo archivo
            archivo = self.request.FILES['archivo_factura']
            factura_num = form.cleaned_data.get('numero_factura', 'sin_numero')
            
            s3_path = f"facturas_cxp/{factura_num}/{archivo.name}"
            
            ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
            if ruta_guardada:
                self.object.archivo_factura = ruta_guardada
            else:
                messages.error(self.request, "No se pudo actualizar la factura en S3.")
                return self.form_invalid(form)
        
        self.object.save()
        messages.success(self.request, "Factura actualizada correctamente.")
        return super().form_valid(form)

class FacturaDetailView(LoginRequiredMixin, DetailView):
    model = Factura
    template_name = 'cuentas_por_pagar/factura_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        factura = self.object
        
        # Información de sincronización con Compras
        context['documentos_sincronizados'] = {
            'factura_compras': factura.orden_compra.factura if factura.orden_compra.factura else None,
            'comprobante_compras': factura.orden_compra.comprobante_pago if factura.orden_compra.comprobante_pago else None,
            'estado_auditoria': factura.orden_compra.get_estatus_display(),
        }
        
        return context

class FacturaDeleteView(LoginRequiredMixin, DeleteView):
    model = Factura
    template_name = 'compras/_confirm_delete.html'  # Reusa template de compras
    success_url = reverse_lazy('lista_facturas')

# Vistas para Pagos
class PagoListView(LoginRequiredMixin, ListView):
    model = Pago
    template_name = 'cuentas_por_pagar/pago_list.html'
    context_object_name = 'pagos'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related('factura__orden_compra__proveedor')
        query = self.request.GET.get('q')
        comprobante = self.request.GET.get('comprobante')
        
        if query:
            queryset = queryset.filter(
                Q(factura__numero_factura__icontains=query) |
                Q(referencia__icontains=query)
            )
        
        # Filtro por comprobante
        if comprobante == 'con_comprobante':
            queryset = queryset.filter(archivo_comprobante__isnull=False)
        elif comprobante == 'sin_comprobante':
            queryset = queryset.filter(archivo_comprobante__isnull=True)
            
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pagos = self.get_queryset()
        
        # Obtener el queryset SIN paginación para las estadísticas
        pagos_sin_paginacion = self.get_queryset()
        
        # Estadísticas CORREGIDAS
        total_pagado = sum(float(pago.monto_pagado) for pago in pagos_sin_paginacion if pago.monto_pagado)
        
        context['total_pagado'] = total_pagado
        context['pagos_con_comprobante'] = pagos_sin_paginacion.filter(archivo_comprobante__isnull=False).count()
        context['metodos_count'] = pagos_sin_paginacion.values('metodo_pago').distinct().count()
        context['total_pagos_count'] = pagos_sin_paginacion.count()  # ¡ESTA ES LA CLAVE!
        
        # Debug
        print(f"DEBUG - Total pagos (sin paginación): {pagos_sin_paginacion.count()}")
        print(f"DEBUG - Total pagos (con paginación): {pagos.count()}")
        print(f"DEBUG - Paginator count: {pagos.paginator.count if hasattr(pagos, 'paginator') else 'N/A'}")
        
        return context

class PagoCreateView(LoginRequiredMixin, CreateView):
    model = Pago
    form_class = PagoForm
    template_name = 'cuentas_por_pagar/generic_form.html'
    success_url = reverse_lazy('lista_pagos')
    
    def form_valid(self, form):
        form.instance.registrado_por = self.request.user
        
        # Guardar primero para obtener el ID
        self.object = form.save(commit=False)
        
        # Lógica para subir comprobante a S3
        if 'archivo_comprobante' in self.request.FILES:
            archivo = self.request.FILES['archivo_comprobante']
            factura_num = form.cleaned_data.get('factura').numero_factura
            plazo_num = form.cleaned_data.get('numero_plazo', 1)
            
            # Crear ruta organizada: comprobantes_pago/{factura}/{plazo}-comprobante.pdf
            nombre_archivo = archivo.name
            s3_path = f"comprobantes_pago/{factura_num}/plazo-{plazo_num}-{nombre_archivo}"
            
            ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
            if ruta_guardada:
                self.object.archivo_comprobante = ruta_guardada
            else:
                messages.error(self.request, "No se pudo subir el comprobante a S3.")
                return self.form_invalid(form)
        
        self.object.save()
        
        # Actualizar la factura después del pago
        factura = self.object.factura
        factura.save()  # Esto dispara el save de Factura para recalcular estatus
        
        messages.success(self.request, f"Pago del plazo #{self.object.numero_plazo} registrado correctamente.")
        return super().form_valid(form)

class PagoUpdateView(LoginRequiredMixin, UpdateView):
    model = Pago
    form_class = PagoForm
    template_name = 'cuentas_por_pagar/generic_form.html'
    success_url = reverse_lazy('lista_pagos')
    
    def form_valid(self, form):
        pago_original = self.get_object()
        self.object = form.save(commit=False)
        
        # Lógica para actualizar comprobante en S3
        if 'archivo_comprobante' in self.request.FILES:
            # Eliminar archivo antiguo
            if pago_original.archivo_comprobante and hasattr(pago_original.archivo_comprobante, 'name'):
                _eliminar_archivo_de_s3(pago_original.archivo_comprobante.name)
            
            # Subir nuevo archivo
            archivo = self.request.FILES['archivo_comprobante']
            factura_num = self.object.factura.numero_factura
            plazo_num = form.cleaned_data.get('numero_plazo', 1)
            
            nombre_archivo = archivo.name
            s3_path = f"comprobantes_pago/{factura_num}/plazo-{plazo_num}-{nombre_archivo}"
            
            ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
            if ruta_guardada:
                self.object.archivo_comprobante = ruta_guardada
            else:
                messages.error(self.request, "No se pudo actualizar el comprobante en S3.")
                return self.form_invalid(form)
        
        self.object.save()
        messages.success(self.request, "Pago actualizado correctamente.")
        return super().form_valid(form)

class PagoDetailView(LoginRequiredMixin, DetailView):
    model = Pago
    template_name = 'cuentas_por_pagar/pago_detail.html'
    context_object_name = 'pago'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pago = self.object
        
        # Información adicional para el template
        context['factura'] = pago.factura
        context['orden_compra'] = pago.factura.orden_compra
        
        return context
    
class PagoDeleteView(LoginRequiredMixin, DeleteView):
    model = Pago
    template_name = 'compras/_confirm_delete.html'
    success_url = reverse_lazy('lista_pagos')
    
    def delete(self, request, *args, **kwargs):
        pago = self.get_object()
        
        # Eliminar archivo de S3 antes de borrar el registro
        if pago.archivo_comprobante and hasattr(pago.archivo_comprobante, 'name'):
            _eliminar_archivo_de_s3(pago.archivo_comprobante.name)
        
        return super().delete(request, *args, **kwargs)

@login_required
@permission_required('cuentas_por_pagar.acceso_cxp', raise_exception=True)
def dashboard_cuentas_por_pagar(request):
    # Obtener todas las facturas pendientes
    facturas_pendientes = Factura.objects.filter(pagada=False).select_related(
        'orden_compra__proveedor'
    )
    
    # Calcular estadísticas por proveedor
    estadisticas_proveedor = {}
    for factura in facturas_pendientes:
        proveedor_nombre = factura.orden_compra.proveedor.razon_social
        if proveedor_nombre not in estadisticas_proveedor:
            estadisticas_proveedor[proveedor_nombre] = {
                'total_deuda': 0,
                'cantidad_facturas': 0,
                'facturas_por_vencer': 0,
                'facturas_vencidas': 0,
                'facturas_sincronizadas': 0
            }
        
        estadisticas_proveedor[proveedor_nombre]['total_deuda'] += float(factura.monto_pendiente)
        estadisticas_proveedor[proveedor_nombre]['cantidad_facturas'] += 1
        
        if factura.esta_por_vencer:
            estadisticas_proveedor[proveedor_nombre]['facturas_por_vencer'] += 1
        elif factura.esta_vencida:
            estadisticas_proveedor[proveedor_nombre]['facturas_vencidas'] += 1
            
        # Contar facturas sincronizadas (con archivo)
        if factura.archivo_factura:
            estadisticas_proveedor[proveedor_nombre]['facturas_sincronizadas'] += 1

    # Convertir a lista ordenada por deuda
    estadisticas = [
        {
            'proveedor': proveedor,
            'total_deuda': data['total_deuda'],
            'cantidad_facturas': data['cantidad_facturas'],
            'facturas_por_vencer': data['facturas_por_vencer'],
            'facturas_vencidas': data['facturas_vencidas'],
            'facturas_sincronizadas': data['facturas_sincronizadas']
        }
        for proveedor, data in estadisticas_proveedor.items()
    ]
    estadisticas.sort(key=lambda x: x['total_deuda'], reverse=True)
    
    # Estadísticas generales
    total_facturas = Factura.objects.count()
    facturas_pendientes_count = facturas_pendientes.count()
    facturas_vencidas_count = Factura.objects.filter(estatus='VENCIDA').count()
    facturas_por_vencer_count = Factura.objects.filter(estatus='POR_VENCER').count()
    total_deuda_general = sum(float(factura.monto_pendiente) for factura in facturas_pendientes)
    
    # NUEVAS MÉTRICAS DE SINCRONIZACIÓN
    facturas_con_archivo = Factura.objects.filter(archivo_factura__isnull=False).count()
    pagos_con_comprobante = Pago.objects.filter(archivo_comprobante__isnull=False).count()
    
    # Métricas de Órdenes de Compra (desde Compras)
    try:
        from compras.models import OrdenCompra
        ocs_listas_auditoria = OrdenCompra.objects.filter(lista_para_auditar=True).count()
        total_ocs_activas = OrdenCompra.objects.filter(estatus__in=['APROBADA', 'LISTA_PARA_AUDITAR']).count()
        ocs_en_proceso = OrdenCompra.objects.filter(estatus='APROBADA').count()
        ocs_auditadas = OrdenCompra.objects.filter(estatus='AUDITADA').count()
        total_ocs_sincronizadas = OrdenCompra.objects.filter(factura_subida=True).count()
    except ImportError:
        ocs_listas_auditoria = 0
        total_ocs_activas = 0
        ocs_en_proceso = 0
        ocs_auditadas = 0
        total_ocs_sincronizadas = 0
    
    # Porcentajes de sincronización
    porcentaje_facturas_sincronizadas = round((facturas_con_archivo / total_facturas * 100), 2) if total_facturas > 0 else 0
    total_pagos = Pago.objects.count()
    porcentaje_pagos_sincronizados = round((pagos_con_comprobante / total_pagos * 100), 2) if total_pagos > 0 else 0
    
    # Alertas recientes
    alertas_recientes = Factura.objects.filter(
        ultima_alerta_enviada__isnull=False
    ).order_by('-ultima_alerta_enviada')[:5]
    
    context = {
        'estadisticas': estadisticas,
        'total_facturas': total_facturas,
        'facturas_pendientes_count': facturas_pendientes_count,
        'facturas_vencidas_count': facturas_vencidas_count,
        'facturas_por_vencer_count': facturas_por_vencer_count,
        'total_deuda_general': total_deuda_general,
        'alertas_recientes': alertas_recientes,
        
        # Nuevas métricas de sincronización
        'facturas_con_archivo': facturas_con_archivo,
        'pagos_con_comprobante': pagos_con_comprobante,
        'ocs_listas_auditoria': ocs_listas_auditoria,
        'total_ocs_activas': total_ocs_activas,
        'ocs_en_proceso': ocs_en_proceso,
        'ocs_auditadas': ocs_auditadas,
        'total_ocs_sincronizadas': total_ocs_sincronizadas,
        'porcentaje_facturas_sincronizadas': porcentaje_facturas_sincronizadas,
        'porcentaje_pagos_sincronizados': porcentaje_pagos_sincronizados,
    }
    return render(request, 'cuentas_por_pagar/dashboard.html', context)

@login_required
def api_estadisticas_proveedor(request):
    """API para gráficas detalladas por proveedor"""
    facturas_pendientes = Factura.objects.filter(pagada=False).select_related(
        'orden_compra__proveedor'
    )
    
    estadisticas_proveedor = {}
    for factura in facturas_pendientes:
        proveedor_nombre = factura.orden_compra.proveedor.razon_social
        if proveedor_nombre not in estadisticas_proveedor:
            estadisticas_proveedor[proveedor_nombre] = {
                'total_deuda': 0,
                'cantidad_facturas': 0,
                'facturas_por_vencer': 0,
                'facturas_vencidas': 0
            }
        
        estadisticas_proveedor[proveedor_nombre]['total_deuda'] += float(factura.monto_pendiente)
        estadisticas_proveedor[proveedor_nombre]['cantidad_facturas'] += 1
        
        if factura.esta_por_vencer:
            estadisticas_proveedor[proveedor_nombre]['facturas_por_vencer'] += 1
        elif factura.esta_vencida:
            estadisticas_proveedor[proveedor_nombre]['facturas_vencidas'] += 1
    
    data = {
        'labels': list(estadisticas_proveedor.keys()),
        'deudas': [data['total_deuda'] for data in estadisticas_proveedor.values()],
        'facturas_totales': [data['cantidad_facturas'] for data in estadisticas_proveedor.values()],
        'facturas_por_vencer': [data['facturas_por_vencer'] for data in estadisticas_proveedor.values()],
        'facturas_vencidas': [data['facturas_vencidas'] for data in estadisticas_proveedor.values()],
    }
    return JsonResponse(data)

@login_required
def api_deudas_proveedor(request):
    """API para gráficas - versión corregida"""
    try:
        facturas_pendientes = Factura.objects.filter(pagada=False).select_related(
            'orden_compra__proveedor'
        )
        
        deudas_por_proveedor = {}
        for factura in facturas_pendientes:
            proveedor_nombre = factura.orden_compra.proveedor.razon_social
            if proveedor_nombre not in deudas_por_proveedor:
                deudas_por_proveedor[proveedor_nombre] = 0
            deudas_por_proveedor[proveedor_nombre] += float(factura.monto_pendiente)
        
        # Ordenar por deuda (mayor a menor) y tomar los primeros 10
        deudas_ordenadas = dict(sorted(
            deudas_por_proveedor.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10])
        
        data = {
            'labels': list(deudas_ordenadas.keys()),
            'data': list(deudas_ordenadas.values()),
        }
        return JsonResponse(data)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def exportar_facturas_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Facturas Cuentas por Pagar"
    
    # Encabezados
    ws.append(['Número Factura', 'Proveedor', 'Monto', 'Pendiente', 'Estatus', 'Fecha Vencimiento'])
    
    # Datos
    facturas = Factura.objects.select_related('orden_compra__proveedor')
    for f in facturas:
        ws.append([
            f.numero_factura,
            f.orden_compra.proveedor.razon_social,
            f.monto,
            f.monto_pendiente,
            f.get_estatus_display(),
            f.fecha_vencimiento,
        ])
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=facturas_cuentas_por_pagar.xlsx'
    wb.save(response)
    return response

# En views.py de CXP - Mejorar la vista existente
@login_required
def gestionar_plazos_factura(request, pk):
    """Vista principal para gestionar plazos de una factura"""
    factura = get_object_or_404(Factura, pk=pk)
    
    # Solo permitir para facturas con OC a plazos
    if not factura.es_pago_plazos:
        messages.info(request, "Esta factura es de pago único. Use el formulario regular de pagos.")
        return redirect('detalle_factura', pk=pk)
    
    # Formulario para agregar pagos
    if request.method == 'POST':
        form = PagoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    pago = form.save(commit=False)
                    pago.registrado_por = request.user
                    pago.factura = factura  # Asignar la factura automáticamente
                    
                    # Validar que el número de plazo no esté ya pagado
                    if factura.pagos.filter(numero_plazo=pago.numero_plazo).exists():
                        messages.error(request, f"El plazo #{pago.numero_plazo} ya fue registrado.")
                        return redirect('gestionar_plazos_factura', pk=pk)
                    
                    pago.save()
                    
                    # Sincronizar comprobante con Compras si existe
                    if pago.archivo_comprobante and factura.orden_compra:
                        factura.orden_compra.comprobante_pago = pago.archivo_comprobante
                        factura.orden_compra.comprobante_pago_subido = True
                        factura.orden_compra.comprobante_subido_por = request.user
                        factura.orden_compra.fecha_comprobante_subido = timezone.now()
                        if hasattr(factura.orden_compra, 'actualizar_estado_auditoria'):
                            factura.orden_compra.actualizar_estado_auditoria()
                        factura.orden_compra.save()
                    
                    messages.success(request, f"Pago del plazo #{pago.numero_plazo} registrado correctamente.")
                    return redirect('gestionar_plazos_factura', pk=pk)
                    
            except Exception as e:
                messages.error(request, f"Error al registrar el pago: {e}")
    else:
        # Sugerir el siguiente plazo pendiente
        ultimo_plazo_pagado = factura.pagos.aggregate(max_plazo=Max('numero_plazo'))['max_plazo'] or 0
        siguiente_plazo = ultimo_plazo_pagado + 1
        
        form = PagoForm(initial={
            'factura': factura,
            'numero_plazo': siguiente_plazo,
            'fecha_pago': timezone.now().date()
        })
    
    # Ocultar el campo factura en el formulario ya que es automático
    form.fields['factura'].widget = forms.HiddenInput()
    
    # Calcular estadísticas para las tarjetas
    plazos_pagados_count = factura.pagos.count()
    plazos_pendientes_count = factura.cantidad_plazos - plazos_pagados_count
    
    # AGREGAR ESTOS CÁLCULOS EXPLÍCITOS
    total_plazos = factura.cantidad_plazos or 0
    plazos_pagados = factura.pagos.count()
    plazos_pendientes = max(0, total_plazos - plazos_pagados)
    
    context = {
        'factura': factura,
        'form': form,
        'plazos_programados': factura.plazos_programados,
        'plazos_pagados': factura.pagos.all().order_by('numero_plazo'),
        'resumen_plazos': factura._generar_resumen_plazos(),
        'plazos_pagados_count': plazos_pagados_count,
        'plazos_pendientes_count': plazos_pendientes_count,
        # AGREGAR ESTAS VARIABLES NUEVAS
        'total_plazos': total_plazos,
        'plazos_pendientes_calculado': plazos_pendientes,
    }
    
    return render(request, 'cuentas_por_pagar/gestionar_plazos.html', context)

@login_required
def gestionar_plazos_oc_redirect(request, pk):
    """Redirige desde la OC en Compras a la factura correspondiente en CXP"""
    orden_compra = get_object_or_404(OrdenCompra, pk=pk)
    
    if not hasattr(orden_compra, 'factura_cxp'):
        messages.error(request, "No se encontró la factura asociada a esta orden de compra.")
        return redirect('detalle_orden_compra', pk=pk)
    
    # Redirige a la gestión de plazos de la factura
    return redirect('gestionar_plazos_factura', pk=orden_compra.factura_cxp.pk)