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

class FacturaListView(LoginRequiredMixin, ListView):
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
    model = Factura
    form_class = FacturaForm
    template_name = 'cuentas_por_pagar/generic_form.html'
    success_url = reverse_lazy('lista_facturas')
    
    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Crear Nueva Factura"
        return context

class FacturaUpdateView(LoginRequiredMixin, UpdateView):
    model = Factura
    form_class = FacturaForm
    template_name = 'cuentas_por_pagar/generic_form.html'
    success_url = reverse_lazy('lista_facturas')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f"Editar Factura {self.object.numero_factura}"
        return context

class FacturaDetailView(LoginRequiredMixin, DetailView):
    model = Factura
    template_name = 'cuentas_por_pagar/factura_detail.html'

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
        queryset = super().get_queryset().select_related('factura__orden_compra')
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(factura__numero_factura__icontains=query) |
                Q(referencia__icontains=query)
            )
        return queryset

class PagoCreateView(LoginRequiredMixin, CreateView):
    model = Pago
    form_class = PagoForm
    template_name = 'cuentas_por_pagar/generic_form.html'
    success_url = reverse_lazy('lista_pagos')
    
    def form_valid(self, form):
        form.instance.registrado_por = self.request.user
        # Actualiza la factura después del pago
        factura = form.instance.factura
        factura.save()  # Esto dispara el save de Factura para recalcular estatus
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Registrar Nuevo Pago"
        return context

class PagoUpdateView(LoginRequiredMixin, UpdateView):
    model = Pago
    form_class = PagoForm
    template_name = 'cuentas_por_pagar/generic_form.html'
    success_url = reverse_lazy('lista_pagos')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f"Editar Pago para Factura {self.object.factura.numero_factura}"
        return context

class PagoDeleteView(LoginRequiredMixin, DeleteView):
    model = Pago
    template_name = 'compras/_confirm_delete.html'
    success_url = reverse_lazy('lista_pagos')

# Nuevas vistas funcionales
@login_required
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
                'facturas_vencidas': 0
            }
        
        estadisticas_proveedor[proveedor_nombre]['total_deuda'] += float(factura.monto_pendiente)
        estadisticas_proveedor[proveedor_nombre]['cantidad_facturas'] += 1
        
        if factura.esta_por_vencer:
            estadisticas_proveedor[proveedor_nombre]['facturas_por_vencer'] += 1
        elif factura.esta_vencida:
            estadisticas_proveedor[proveedor_nombre]['facturas_vencidas'] += 1
    
    # Convertir a lista ordenada por deuda
    estadisticas = [
        {
            'proveedor': proveedor,
            'total_deuda': data['total_deuda'],
            'cantidad_facturas': data['cantidad_facturas'],
            'facturas_por_vencer': data['facturas_por_vencer'],
            'facturas_vencidas': data['facturas_vencidas']
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