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
from django.contrib.auth.decorators import login_required
from openpyxl import Workbook
from django import forms
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from compras.models import OrdenCompra, Proveedor
from .forms import CXPManualForm

# ==============================================================================
# === FUNCIONES AUXILIARES PARA GESTIONAR ARCHIVOS EN S3 ===
# ==============================================================================

def _subir_archivo_a_s3(archivo_obj, s3_ruta_relativa):
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        full_s3_path = f"{settings.AWS_MEDIA_LOCATION}/{s3_ruta_relativa}"
        s3_client.upload_fileobj(archivo_obj, settings.AWS_STORAGE_BUCKET_NAME, full_s3_path)
        return s3_ruta_relativa
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al subir el archivo a S3: {e}")
        return None

def _eliminar_archivo_de_s3(ruta_completa_s3):
    if not ruta_completa_s3:
        return
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=str(ruta_completa_s3))
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al eliminar archivo antiguo de S3: {e}")

# ==============================================================================
# === VISTAS DE FACTURAS ===
# ==============================================================================

class FacturaListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'cuentas_por_pagar.acceso_cxp'
    model = Factura
    template_name = 'cuentas_por_pagar/factura_list.html'
    context_object_name = 'facturas'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'orden_compra__proveedor', 
            'orden_compra__empresa',
            'proveedor'
        )
        query = self.request.GET.get('q')
        estatus = self.request.GET.get('estatus')
        proveedor_id = self.request.GET.get('proveedor')
        
        if query:
            queryset = queryset.filter(
                Q(numero_factura__icontains=query) |
                Q(orden_compra__folio__icontains=query) |
                Q(folio_cxp__icontains=query)
            )
        if estatus:
            queryset = queryset.filter(estatus=estatus)
        if proveedor_id:
            queryset = queryset.filter(proveedor_id=proveedor_id)
            
        return queryset.order_by('-fecha_emision')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['estatus_choices'] = Factura.ESTATUS_CHOICES
        context['proveedores'] = Proveedor.objects.all().order_by('razon_social')
        
        proveedor_id = self.request.GET.get('proveedor')
        if proveedor_id:
            context['proveedor_seleccionado'] = Proveedor.objects.filter(pk=proveedor_id).first()
        
        queryset = self.get_queryset()
        total_objects = Factura.objects.all()
        
        context['total_facturas_count'] = total_objects.count()
        context['facturas_filtradas_count'] = queryset.count()
        context['facturas_vencidas_count'] = total_objects.filter(estatus='VENCIDA').count()
        context['facturas_por_vencer_count'] = total_objects.filter(estatus='POR_VENCER').count()
        
        deuda_total = sum(f.monto_pendiente for f in total_objects.filter(pagada=False))
        context['total_deuda_general'] = deuda_total
        return context

class FacturaCreateView(LoginRequiredMixin, CreateView):
    def get(self, request, *args, **kwargs):
        messages.warning(request, "La creación manual está deshabilitada. Use Órdenes de Compra.")
        return redirect('lista_facturas')
    
    def post(self, request, *args, **kwargs):
        messages.warning(request, "La creación manual está deshabilitada.")
        return redirect('lista_facturas')

class FacturaUpdateView(LoginRequiredMixin, UpdateView):
    model = Factura
    form_class = FacturaForm
    # SE ELIMINÓ template_name = 'generic_form.html'
    # Ahora buscará por defecto: cuentas_por_pagar/factura_form.html
    success_url = reverse_lazy('lista_facturas')
    
    def form_valid(self, form):
        factura_original = self.get_object()
        self.object = form.save(commit=False)
        
        if 'archivo_factura' in self.request.FILES:
            if factura_original.archivo_factura and hasattr(factura_original.archivo_factura, 'name'):
                _eliminar_archivo_de_s3(factura_original.archivo_factura.name)
            
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
        
        # 1. Enviar el Formulario de Pago pre-configurado
        # Calculamos el siguiente plazo sugerido
        if factura.es_pago_plazos:
            max_plazo = factura.pagos.aggregate(m=Max('numero_plazo'))['m'] or 0
            siguiente_plazo = min(max_plazo + 1, factura.cantidad_plazos)
            initial_data = {
                'factura': factura,
                'numero_plazo': siguiente_plazo,
                'monto_pagado': round(factura.monto_por_plazo, 2),
                'fecha_pago': timezone.now().date()
            }
        else:
            initial_data = {'factura': factura, 'fecha_pago': timezone.now().date()}
            
        context['form_pago'] = PagoForm(initial=initial_data)
        
        # 2. Enviar la lista de plazos programados (La lógica que tenías en gestionar_plazos)
        if factura.es_pago_plazos:
            context['plazos_programados'] = factura.plazos_programados
            
        return context
    
class FacturaDeleteView(LoginRequiredMixin, DeleteView):
    model = Factura
    template_name = 'compras/_confirm_delete.html'
    success_url = reverse_lazy('lista_facturas')

# ==============================================================================
# === VISTAS DE PAGOS ===
# ==============================================================================

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
        if comprobante == 'con_comprobante':
            queryset = queryset.filter(archivo_comprobante__isnull=False)
        elif comprobante == 'sin_comprobante':
            queryset = queryset.filter(archivo_comprobante__isnull=True)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pagos_sin_paginacion = self.get_queryset()
        total_pagado = sum(float(pago.monto_pagado) for pago in pagos_sin_paginacion if pago.monto_pagado)
        
        context['total_pagado'] = total_pagado
        context['pagos_con_comprobante'] = pagos_sin_paginacion.filter(archivo_comprobante__isnull=False).count()
        context['metodos_count'] = pagos_sin_paginacion.values('metodo_pago').distinct().count()
        context['total_pagos_count'] = pagos_sin_paginacion.count()
        return context

class PagoCreateView(LoginRequiredMixin, CreateView):
    model = Pago
    form_class = PagoForm
    # SE ELIMINÓ template_name = 'generic_form.html'
    # Ahora buscará por defecto: cuentas_por_pagar/pago_form.html
    success_url = reverse_lazy('lista_pagos')
    
    def form_valid(self, form):
        form.instance.registrado_por = self.request.user
        self.object = form.save(commit=False)
        
        if 'archivo_comprobante' in self.request.FILES:
            archivo = self.request.FILES['archivo_comprobante']
            factura_num = form.cleaned_data.get('factura').numero_factura
            plazo_num = form.cleaned_data.get('numero_plazo', 1)
            
            nombre_archivo = archivo.name
            s3_path = f"comprobantes_pago/{factura_num}/plazo-{plazo_num}-{nombre_archivo}"
            
            ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
            if ruta_guardada:
                self.object.archivo_comprobante = ruta_guardada
            else:
                messages.error(self.request, "No se pudo subir el comprobante a S3.")
                return self.form_invalid(form)
        
        self.object.save()
        factura = self.object.factura
        factura.save()
        messages.success(self.request, f"Pago del plazo #{self.object.numero_plazo} registrado correctamente.")
        return super().form_valid(form)

class PagoUpdateView(LoginRequiredMixin, UpdateView):
    model = Pago
    form_class = PagoForm
    # SE ELIMINÓ template_name = 'generic_form.html'
    # Ahora buscará por defecto: cuentas_por_pagar/pago_form.html
    success_url = reverse_lazy('lista_pagos')
    
    def form_valid(self, form):
        pago_original = self.get_object()
        self.object = form.save(commit=False)
        
        if 'archivo_comprobante' in self.request.FILES:
            if pago_original.archivo_comprobante and hasattr(pago_original.archivo_comprobante, 'name'):
                _eliminar_archivo_de_s3(pago_original.archivo_comprobante.name)
            
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
        context['factura'] = pago.factura
        context['orden_compra'] = pago.factura.orden_compra
        return context
    
class PagoDeleteView(LoginRequiredMixin, DeleteView):
    model = Pago
    template_name = 'compras/_confirm_delete.html'
    success_url = reverse_lazy('lista_pagos')
    
    def delete(self, request, *args, **kwargs):
        pago = self.get_object()
        if pago.archivo_comprobante and hasattr(pago.archivo_comprobante, 'name'):
            _eliminar_archivo_de_s3(pago.archivo_comprobante.name)
        return super().delete(request, *args, **kwargs)

# ==============================================================================
# === DASHBOARD Y APIS ===
# ==============================================================================

@login_required
@permission_required('cuentas_por_pagar.acceso_cxp', raise_exception=True)
def dashboard_cuentas_por_pagar(request):
    facturas_pendientes = Factura.objects.filter(pagada=False).select_related('proveedor')
    estadisticas_proveedor = {}
    
    for factura in facturas_pendientes:
        if factura.proveedor:
            proveedor_nombre = factura.proveedor.razon_social
        elif factura.orden_compra and factura.orden_compra.proveedor:
            proveedor_nombre = factura.orden_compra.proveedor.razon_social
        else:
            proveedor_nombre = "Sin Proveedor Asignado"

        if proveedor_nombre not in estadisticas_proveedor:
            estadisticas_proveedor[proveedor_nombre] = {
                'total_deuda': 0, 'cantidad_facturas': 0, 'facturas_por_vencer': 0,
                'facturas_vencidas': 0, 'facturas_sincronizadas': 0
            }
        
        estadisticas_proveedor[proveedor_nombre]['total_deuda'] += float(factura.monto_pendiente)
        estadisticas_proveedor[proveedor_nombre]['cantidad_facturas'] += 1
        
        if factura.esta_por_vencer:
            estadisticas_proveedor[proveedor_nombre]['facturas_por_vencer'] += 1
        elif factura.esta_vencida:
            estadisticas_proveedor[proveedor_nombre]['facturas_vencidas'] += 1
        if factura.archivo_factura:
            estadisticas_proveedor[proveedor_nombre]['facturas_sincronizadas'] += 1

    estadisticas = [
        {'proveedor': k, **v} for k, v in estadisticas_proveedor.items()
    ]
    estadisticas.sort(key=lambda x: x['total_deuda'], reverse=True)
    
    total_facturas = Factura.objects.count()
    facturas_con_archivo = Factura.objects.filter(archivo_factura__isnull=False).count()
    total_pagos = Pago.objects.count()
    pagos_con_comprobante = Pago.objects.filter(archivo_comprobante__isnull=False).count()
    
    # Cálculos seguros de OCs
    try:
        from compras.models import OrdenCompra
        ocs_listas_auditoria = OrdenCompra.objects.filter(lista_para_auditar=True).count()
        total_ocs_activas = OrdenCompra.objects.filter(estatus__in=['APROBADA', 'LISTA_PARA_AUDITAR']).count()
        ocs_en_proceso = OrdenCompra.objects.filter(estatus='APROBADA').count()
        ocs_auditadas = OrdenCompra.objects.filter(estatus='AUDITADA').count()
        total_ocs_sincronizadas = OrdenCompra.objects.filter(factura_subida=True).count()
    except ImportError:
        ocs_listas_auditoria = 0; total_ocs_activas = 0; ocs_en_proceso = 0; ocs_auditadas = 0; total_ocs_sincronizadas = 0

    porcentaje_facturas_sincronizadas = round((facturas_con_archivo / total_facturas * 100), 2) if total_facturas > 0 else 0
    porcentaje_pagos_sincronizados = round((pagos_con_comprobante / total_pagos * 100), 2) if total_pagos > 0 else 0
    
    alertas_recientes = Factura.objects.filter(ultima_alerta_enviada__isnull=False).select_related('proveedor').order_by('-ultima_alerta_enviada')[:5]
    
    context = {
        'estadisticas': estadisticas,
        'total_facturas': total_facturas,
        'facturas_pendientes_count': facturas_pendientes.count(),
        'facturas_vencidas_count': Factura.objects.filter(estatus='VENCIDA').count(),
        'facturas_por_vencer_count': Factura.objects.filter(estatus='POR_VENCER').count(),
        'total_deuda_general': sum(float(f.monto_pendiente) for f in facturas_pendientes),
        'alertas_recientes': alertas_recientes,
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
    facturas_pendientes = Factura.objects.filter(pagada=False).select_related('orden_compra__proveedor')
    estadisticas_proveedor = {}
    for factura in facturas_pendientes:
        proveedor_nombre = factura.orden_compra.proveedor.razon_social
        if proveedor_nombre not in estadisticas_proveedor:
            estadisticas_proveedor[proveedor_nombre] = {'total_deuda': 0, 'cantidad_facturas': 0, 'facturas_por_vencer': 0, 'facturas_vencidas': 0}
        
        estadisticas_proveedor[proveedor_nombre]['total_deuda'] += float(factura.monto_pendiente)
        estadisticas_proveedor[proveedor_nombre]['cantidad_facturas'] += 1
        if factura.esta_por_vencer: estadisticas_proveedor[proveedor_nombre]['facturas_por_vencer'] += 1
        elif factura.esta_vencida: estadisticas_proveedor[proveedor_nombre]['facturas_vencidas'] += 1
    
    data = {
        'labels': list(estadisticas_proveedor.keys()),
        'deudas': [d['total_deuda'] for d in estadisticas_proveedor.values()],
        'facturas_totales': [d['cantidad_facturas'] for d in estadisticas_proveedor.values()],
        'facturas_por_vencer': [d['facturas_por_vencer'] for d in estadisticas_proveedor.values()],
        'facturas_vencidas': [d['facturas_vencidas'] for d in estadisticas_proveedor.values()],
    }
    return JsonResponse(data)

@login_required
def api_deudas_proveedor(request):
    try:
        facturas_pendientes = Factura.objects.filter(pagada=False).select_related('orden_compra__proveedor')
        deudas_por_proveedor = {}
        for factura in facturas_pendientes:
            proveedor_nombre = factura.orden_compra.proveedor.razon_social
            deudas_por_proveedor[proveedor_nombre] = deudas_por_proveedor.get(proveedor_nombre, 0) + float(factura.monto_pendiente)
        
        deudas_ordenadas = dict(sorted(deudas_por_proveedor.items(), key=lambda x: x[1], reverse=True)[:10])
        return JsonResponse({'labels': list(deudas_ordenadas.keys()), 'data': list(deudas_ordenadas.values())})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def exportar_facturas_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Facturas Cuentas por Pagar"
    ws.append(['Número Factura', 'Proveedor', 'Monto', 'Pendiente', 'Estatus', 'Fecha Vencimiento'])
    for f in Factura.objects.select_related('orden_compra__proveedor'):
        ws.append([f.numero_factura, f.orden_compra.proveedor.razon_social, f.monto, f.monto_pendiente, f.get_estatus_display(), f.fecha_vencimiento])
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=facturas_cuentas_por_pagar.xlsx'
    wb.save(response)
    return response

@login_required
def gestionar_plazos_factura(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    
    # NOTA: Si usas esta vista para pagos únicos también, deberías comentar o ajustar esta validación:
    if not factura.es_pago_plazos:
        # Si es pago único, redirigimos (o podrías permitirlo quitando este bloque)
        # messages.info(request, "Esta factura es de pago único.")
        # return redirect('detalle_factura', pk=pk)
        pass # Permitimos que continúe para que funcione el Modal de tu detalle

    if request.method == 'POST':
        # 1. Instanciamos el form con los datos recibidos
        form = PagoForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                # 2. Preparamos el objeto sin guardar todavía
                pago = form.save(commit=False)
                pago.registrado_por = request.user
                pago.factura = factura  # Asignación forzosa por seguridad
                
                # 3. Lógica de subida a S3 (Reutilizando tu función auxiliar)
                if 'archivo_comprobante' in request.FILES:
                    archivo = request.FILES['archivo_comprobante']
                    factura_num = factura.numero_factura
                    # Obtenemos el número de plazo del form o asumimos 1
                    plazo_num = form.cleaned_data.get('numero_plazo') or 1
                    
                    nombre_archivo = archivo.name
                    # Ruta organizada en S3
                    s3_path = f"comprobantes_pago/{factura_num}/plazo-{plazo_num}-{nombre_archivo}"
                    
                    ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
                    
                    if ruta_guardada:
                        pago.archivo_comprobante = ruta_guardada
                    else:
                        messages.warning(request, "El pago se registró, pero hubo un error subiendo el comprobante a S3.")
                
                # 4. Guardamos
                pago.save()
                messages.success(request, f"Pago registrado correctamente.")
                return redirect('detalle_factura', pk=pk)
                
            except Exception as e:
                messages.error(request, f"Ocurrió un error al guardar: {e}")
        else:
            messages.error(request, "El formulario contiene errores. Revise los datos.")
            
    else:
        # Lógica GET original
        max_plazo = factura.pagos.aggregate(m=Max('numero_plazo'))['m'] or 0
        siguiente_plazo = min(max_plazo + 1, factura.cantidad_plazos)
        
        initial_data = {
            'factura': factura,
            'numero_plazo': siguiente_plazo,
            'monto_pagado': round(factura.monto_por_plazo, 2),
            'fecha_pago': timezone.now().date()
        }
        form = PagoForm(initial=initial_data)
    
    # 5. Configuración común del widget (Ahora 'form' siempre existe)
    form.fields['factura'].widget = forms.HiddenInput()
    
    return render(request, 'cuentas_por_pagar/gestionar_plazos.html', {
        'factura': factura, 
        'form': form, 
        'plazos_programados': factura.plazos_programados
    })
@login_required
def gestionar_plazos_oc_redirect(request, pk):
    orden_compra = get_object_or_404(OrdenCompra, pk=pk)
    if not hasattr(orden_compra, 'factura_cxp'):
        messages.error(request, "No se encontró la factura asociada a esta orden de compra.")
        return redirect('detalle_orden_compra', pk=pk)
    return redirect('gestionar_plazos_factura', pk=orden_compra.factura_cxp.pk)

@login_required
@permission_required('cuentas_por_pagar.acceso_cxp', raise_exception=True)
def nueva_cuenta_por_pagar(request):
    if request.method == 'POST':
        form = CXPManualForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    factura = form.save(commit=False)
                    factura.creado_por = request.user
                    if factura.fecha_emision:
                        factura.fecha_vencimiento = factura.fecha_emision + timezone.timedelta(days=30)
                    else:
                        factura.fecha_vencimiento = timezone.now().date() + timezone.timedelta(days=30)
                    if 'archivo_factura' in request.FILES:
                        pass # S3 lógica aquí
                    factura.save()
                    messages.success(request, f"CXP {factura.folio_cxp} registrada correctamente.")
                    return redirect('lista_facturas')
            except Exception as e:
                messages.error(request, f"Error: {e}")
    else:
        form = CXPManualForm()
    return render(request, 'cuentas_por_pagar/nueva_cuenta_por_pagar.html', {'form': form})