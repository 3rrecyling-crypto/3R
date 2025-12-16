# compras/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.forms import inlineformset_factory
from django.db.models import Count, Q
import csv
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.contrib.auth.models import User
from django.forms import formset_factory # <-- AÑADE ESTE IMPORT AL INICIO DEL ARCHIVO
from .models import Articulo
from django.db.models import F
from num2words import num2words # <--- AÑADE ESTE IMPORT
from decimal import Decimal # <--- Asegúrate que este import esté presente
from django.urls import reverse_lazy
# Modelos de esta app
from .models import (
    Proveedor, Articulo, ArticuloProveedor, Categoria, UnidadMedida,
    SolicitudCompra, DetalleSolicitud, OrdenCompra, DetalleOrdenCompra
)
# Formularios de esta app
from .forms import (
    ProveedorForm, ArticuloForm, ArticuloProveedorFormSet, SolicitudCompraForm, 
    DetalleSolicitudForm, OrdenCompraForm, DetalleOrdenCompraForm, CategoriaForm,
    OrdenCompraArchivosForm
)
# Modelos de la app ternium
from ternium.models import Empresa
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from ternium.models import Empresa, Origen # Asegúrate que Origen esté importado
from django.contrib.auth.decorators import permission_required, login_required
from django.contrib.auth.mixins import PermissionRequiredMixin

# --- DASHBOARD ---

@login_required
@permission_required('compras.acceso_compras', raise_exception=True)
def dashboard_compras(request):
    """
    Dashboard principal mejorado con KPIs, tablas de resumen y gráficos.
    """
    
    # --- 1. KPIs GLOBALES (Indicadores Clave) ---
    # Usamos diccionarios para pasar el valor y también metadatos de color/icono si quisieramos
    kpis = {
        'pendientes': SolicitudCompra.objects.filter(estatus='PENDIENTE_APROBACION').count(),
        'urgentes': SolicitudCompra.objects.filter(estatus='PENDIENTE_APROBACION', prioridad='URGENTE').count(),
        'ordenes_activas': OrdenCompra.objects.exclude(estatus__in=['CANCELADA', 'CERRADA', 'BORRADOR']).count(),
        'proveedores_activos': Proveedor.objects.filter(activo=True).count(),
        'articulos_totales': Articulo.objects.filter(activo=True).count(),
    }
    
    # --- 2. TABLAS DE RESUMEN ---
    
    # Últimas solicitudes pendientes de aprobación (Acción inmediata)
    ultimas_solicitudes = SolicitudCompra.objects.filter(
        estatus='PENDIENTE_APROBACION'
    ).select_related('solicitante', 'empresa').order_by('-creado_en')[:5]

    # Últimas órdenes de compra generadas (Visibilidad de flujo)
    ultimas_ordenes = OrdenCompra.objects.select_related(
        'proveedor'
    ).order_by('-fecha_emision')[:5]

    # --- 3. DATOS PARA GRÁFICO (Chart.js) ---
    # Estado de las Órdenes de Compra (excluyendo cerradas para ver carga actual)
    ordenes_por_estatus = OrdenCompra.objects.exclude(
        estatus__in=['CERRADA', 'RECIBIDA_TOTAL']
    ).values('estatus').annotate(total=Count('id'))
    
    labels_grafico = []
    data_grafico = []
    colores_grafico = []
    
    mapa_colores = {
        'BORRADOR': '#6c757d',          # Gris
        'APROBADA': '#0d6efd',          # Azul Primary
        'EN_AUDITORIA': '#fd7e14',      # Naranja
        'LISTA_PARA_AUDITAR': '#ffc107',# Amarillo
        'CANCELADA': '#dc3545',         # Rojo
        'RECIBIDA_PARCIAL': '#20c997',  # Verde azulado
    }

    for item in ordenes_por_estatus:
        estatus_readable = dict(OrdenCompra.ESTATUS_CHOICES).get(item['estatus'], item['estatus'])
        labels_grafico.append(estatus_readable)
        data_grafico.append(item['total'])
        colores_grafico.append(mapa_colores.get(item['estatus'], '#adb5bd'))

    context = {
        'kpis': kpis,
        'ultimas_solicitudes': ultimas_solicitudes,
        'ultimas_ordenes': ultimas_ordenes,
        # Datos para JS
        'chart_labels': json.dumps(labels_grafico),
        'chart_data': json.dumps(data_grafico),
        'chart_colors': json.dumps(colores_grafico),
    }
    return render(request, 'compras/dashboard.html', context)

class ProveedorListView(LoginRequiredMixin, ListView):
    model = Proveedor
    template_name = 'compras/proveedor_list.html'
    context_object_name = 'proveedores'
    paginate_by = 10

    def get_queryset(self):
        # --- MODIFICACIÓN: Optimizar consulta ---
        queryset = super().get_queryset().select_related('empresa', 'lugar')
        
        query = self.request.GET.get('q')
        operador_id = self.request.GET.get('operador') # <-- Nuevo
        lugar_id = self.request.GET.get('lugar')       # <-- Nuevo
        
        if query:
            queryset = queryset.filter(
                Q(razon_social__icontains=query) |
                Q(rfc__icontains=query) |
                Q(contacto_principal__icontains=query)
            )
        
        # --- NUEVOS FILTROS ---
        if operador_id:
            queryset = queryset.filter(empresa_id=operador_id)
        if lugar_id:
            queryset = queryset.filter(lugar_id=lugar_id)
        # --- FIN NUEVOS FILTROS ---
            
        return queryset.order_by('razon_social')

    # --- MÉTODO MODIFICADO/AÑADIDO ---
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Datos para los dropdowns de filtros
        context['operadores'] = Empresa.objects.all().order_by('nombre')
        context['lugares'] = Lugar.objects.filter(tipo='ORIGEN').order_by('nombre')
        
        # Pasar filtros aplicados de vuelta al template
        context['filtros_aplicados'] = self.request.GET
        
        return context

class ProveedorCreateView(LoginRequiredMixin, CreateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'compras/generic_form.html'
    success_url = reverse_lazy('lista_proveedores')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Registrar Nuevo Proveedor"
        return context

class ProveedorUpdateView(LoginRequiredMixin, UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'compras/generic_form.html'
    success_url = reverse_lazy('lista_proveedores')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f"Editando a {self.object.razon_social}"
        return context

class ProveedorDetailView(LoginRequiredMixin, DetailView):
    model = Proveedor
    template_name = 'compras/proveedor_detail.html'

class ProveedorDeleteView(LoginRequiredMixin, DeleteView):
    model = Proveedor
    template_name = 'compras/_confirm_delete.html'
    success_url = reverse_lazy('lista_proveedores')


# --- CRUD ARTÍCULOS ---

class ArticuloListView(LoginRequiredMixin, ListView):
    model = Articulo
    template_name = 'compras/articulo_list.html'
    context_object_name = 'articulos'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'empresa', 'categoria', 'unidad_medida', 'origen'
        ).prefetch_related(
            'proveedores'
        )
        
        # --- INICIO DE FILTROS ---
        query = self.request.GET.get('q')
        empresa_id = self.request.GET.get('empresa')
        categoria_id = self.request.GET.get('categoria') 
        tipo = self.request.GET.get('tipo')             
        estatus = self.request.GET.get('estatus')
        origen_id = self.request.GET.get('origen') # <-- AÑADIDO

        # Aplicar filtros
        if query:
            queryset = queryset.filter(
                Q(nombre__icontains=query) | 
                Q(sku__icontains=query) |
                Q(descripcion__icontains=query) 
            )
        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)
        if categoria_id:
            queryset = queryset.filter(categoria_id=categoria_id)
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        if estatus:
            queryset = queryset.filter(activo=(estatus == 'activo'))
            
        # --- FILTRO AÑADIDO ---
        if origen_id:
            queryset = queryset.filter(origen_id=origen_id)
        # --- FIN DE FILTROS ---

        return queryset.order_by('nombre') 
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['empresas'] = Empresa.objects.all().order_by('nombre')
        context['categorias'] = Categoria.objects.all().order_by('nombre')
        context['tipo_choices'] = Articulo.TIPO_CHOICES
        context['estatus_choices'] = [
            ('activo', 'Activo'),
            ('inactivo', 'Inactivo')
        ]
        
        # --- LÍNEA AÑADIDA ---
        # Pasamos todos los Lugares de tipo 'ORIGEN' al contexto
        context['origenes'] = Lugar.objects.filter(tipo='ORIGEN').order_by('nombre')
        
        context['filtros_aplicados'] = self.request.GET
        
        return context

@login_required
def crear_articulo(request):
    """
    Vista para CREAR un artículo y sus proveedores, usando el mismo
    template que la vista de edición.
    """
    if request.method == 'POST':
        form = ArticuloForm(request.POST)
        formset = ArticuloProveedorFormSet(request.POST, prefix='proveedores')
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                articulo = form.save() # Guarda el artículo
                formset.instance = articulo # Asigna el artículo al formset
                formset.save() # Guarda los proveedores
                messages.success(request, f"Artículo '{articulo.nombre}' creado correctamente.")
                return redirect('lista_articulos')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario.")
    else:
        # Petición GET: Muestra el formulario vacío
        form = ArticuloForm()
        formset = ArticuloProveedorFormSet(prefix='proveedores', queryset=ArticuloProveedor.objects.none())

    context = {
        'form': form,
        'formset': formset,
        'titulo': "Crear Nuevo Artículo/Servicio"
    }
    return render(request, 'compras/articulo_form_with_suppliers.html', context)
@login_required
def editar_articulo(request, pk):
    articulo = get_object_or_404(Articulo, pk=pk)
    
    if request.method == 'POST':
        form = ArticuloForm(request.POST, instance=articulo)
        formset = ArticuloProveedorFormSet(request.POST, instance=articulo, prefix='proveedores')
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                messages.success(request, f"Artículo '{articulo.nombre}' actualizado correctamente.")
                return redirect('lista_articulos')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario.")
    else:
        form = ArticuloForm(instance=articulo)
        formset = ArticuloProveedorFormSet(instance=articulo, prefix='proveedores')

    context = {
        'form': form,
        'formset': formset,
        'articulo': articulo,
        'titulo': f"Editando Artículo: {articulo.nombre}"
    }
    return render(request, 'compras/articulo_form_with_suppliers.html', context)


# --- CRUD Y FLUJO DE SOLICITUD DE COMPRA ---

class SolicitudCompraListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'compras.acceso_compras'
    model = SolicitudCompra
    template_name = 'compras/solicitud_lista.html'
    context_object_name = 'solicitudes'
    paginate_by = 15
    ordering = ['-creado_en']

    def get_queryset(self):
        """
        Sobrescribimos este método para añadir la lógica de filtrado
        basada en los parámetros GET de la URL.
        """
        # --- INICIO MODIFICACIÓN ---
        # Añadimos 'lugar' al select_related para optimizar
        queryset = super().get_queryset().select_related(
            'empresa', 'lugar', 'solicitante', 'aprobado_por'
        )
        # --- FIN MODIFICACIÓN ---
        
        # Obtener parámetros del formulario de filtros
        folio = self.request.GET.get('folio')
        empresa_id = self.request.GET.get('empresa')
        lugar_id = self.request.GET.get('lugar') # <-- AÑADIDO
        solicitante_id = self.request.GET.get('solicitante')
        estatus = self.request.GET.get('estatus')
        prioridad = self.request.GET.get('prioridad')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        # Aplicar filtros al queryset si los parámetros existen
        if folio:
            queryset = queryset.filter(folio__icontains=folio)
        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)
        
        # --- FILTRO AÑADIDO ---
        if lugar_id:
            queryset = queryset.filter(lugar_id=lugar_id)
        # --- FIN FILTRO AÑADIDO ---
            
        if solicitante_id:
            queryset = queryset.filter(solicitante_id=solicitante_id)
        if estatus:
            queryset = queryset.filter(estatus=estatus)
        if prioridad:
            queryset = queryset.filter(prioridad=prioridad)
        if start_date:
            queryset = queryset.filter(creado_en__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(creado_en__date__lte=end_date)
            
        return queryset

    def get_context_data(self, **kwargs):
        """
        Añadimos al contexto los datos necesarios para popular los
        selects del formulario de filtros.
        """
        context = super().get_context_data(**kwargs)
        
        # Datos para los dropdowns del formulario de filtros
        context['empresas'] = Empresa.objects.all().order_by('nombre')
        
        # --- LÍNEA AÑADIDA ---
        context['lugares'] = Lugar.objects.filter(tipo='ORIGEN').order_by('nombre')
        # --- FIN LÍNEA AÑADIDA ---
        
        solicitantes_ids = SolicitudCompra.objects.values_list('solicitante', flat=True).distinct()
        context['solicitantes'] = User.objects.filter(id__in=solicitantes_ids).order_by('username')
        context['estatus_choices'] = SolicitudCompra.ESTATUS_CHOICES
        context['prioridad_choices'] = SolicitudCompra.PRIORIDAD_CHOICES
        
        # Pasamos los filtros aplicados de vuelta al template para mantener el estado del formulario
        context['filtros_aplicados'] = self.request.GET
        
        return context

class SolicitudCompraDetailView(LoginRequiredMixin, DetailView):
    model = SolicitudCompra
    template_name = 'compras/solicitud_detalle.html'
    context_object_name = 'solicitud'
    
@login_required
def get_proveedores_por_empresa(request, empresa_id):
    """Devuelve una lista de proveedores para una empresa específica."""
    proveedores = Proveedor.objects.filter(empresa_id=empresa_id, activo=True).values('id', 'razon_social')
    return JsonResponse({'proveedores': list(proveedores)})

@login_required
def get_articulos_por_proveedor(request, proveedor_id):
    """
    Devuelve los artículos de un proveedor incluyendo sus TASAS reales de impuestos.
    """
    try:
        # Filtramos artículos activos y del proveedor seleccionado
        articulos_prov = ArticuloProveedor.objects.filter(
            proveedor_id=proveedor_id, 
            articulo__activo=True
        ).select_related('articulo', 'articulo__categoria', 'articulo__unidad_medida')
        
        data = []
        for ap in articulos_prov:
            articulo = ap.articulo
            data.append({
                'id': articulo.id,
                'nombre': articulo.nombre,
                'sku': articulo.sku,
                'precio': ap.precio_unitario,
                
                # --- CAMBIO IMPORTANTE: Enviamos el valor numérico exacto ---
                # Si el campo es None, enviamos 0.0
                'iva_tasa': float(articulo.porcentaje_iva or 0), 
                'ret_iva_tasa': float(articulo.porcentaje_retencion_iva or 0),
                # ------------------------------------------------------------
                
                'unidad_medida': articulo.unidad_medida.abreviatura if articulo.unidad_medida else None,
                'categoria': str(articulo.categoria) if articulo.categoria else None,
                'tipo': articulo.get_tipo_display(),
            })
        
        return JsonResponse({'articulos': data})
    except Exception as e:
        print(f"Error en API Articulos: {e}") 
        return JsonResponse({'articulos': []})

@login_required
def crear_solicitud(request):
    DetalleFormSet = inlineformset_factory(
        SolicitudCompra, 
        DetalleSolicitud, 
        form=DetalleSolicitudForm, 
        extra=1, 
        can_delete=True
    )
    
    if request.method == 'POST':
        form = SolicitudCompraForm(request.POST, request.FILES)
        
        # Obtenemos el ID del proveedor de forma segura
        proveedor_id = request.POST.get('proveedor')
        if not proveedor_id:
            proveedor_id = None # Asegurar que sea None y no cadena vacía si falla
        
        formset = DetalleFormSet(
            request.POST, 
            request.FILES,
            prefix='detalles',
            form_kwargs={'proveedor_id': proveedor_id} 
        )
        
        if form.is_valid():
            # Validamos el formset. Aquí es donde DetalleSolicitudForm usará el 
            # proveedor_id que pasamos arriba para asegurar que el artículo sea válido.
            if formset.is_valid():
                if not formset.has_changed():
                     messages.error(request, "La solicitud debe tener al menos un artículo.")
                else:
                    try:
                        with transaction.atomic():
                            solicitud = form.save(commit=False)
                            solicitud.solicitante = request.user
                            solicitud.estatus = 'PENDIENTE_APROBACION'
                            solicitud.save()
                            
                            formset.instance = solicitud
                            formset.save()
                            
                            messages.success(request, f'Solicitud {solicitud.folio} enviada para aprobación.')
                            return redirect('lista_solicitudes')
                    except Exception as e:
                        messages.error(request, f"Error al crear la solicitud: {e}")
            else:
                # Errores específicos de los artículos
                for i, form_errors in enumerate(formset.errors):
                    for field, errors in form_errors.items():
                        for error in errors:
                            messages.error(request, f"Error en el artículo #{i+1} ({field}): {error}")
        else:
            messages.error(request, f"Error en datos generales: {form.errors.as_text()}")

    else: # GET
        form = SolicitudCompraForm()
        # Inicializamos con None, lo que activará el "Articulo.objects.filter(activo=True)" en forms.py
        # permitiendo que el widget se renderice correctamente para el JS.
        formset = DetalleFormSet(prefix='detalles', form_kwargs={'proveedor_id': None})

    context = { 
        'form': form, 
        'formset': formset, 
        'titulo': 'Nueva Solicitud de Compra' 
    }
    return render(request, 'compras/solicitud_form.html', context)
@login_required
def aprobar_solicitud(request, pk):
    if request.method == 'POST':
        solicitud = get_object_or_404(SolicitudCompra, pk=pk)
        
        if solicitud.estatus != 'PENDIENTE_APROBACION':
            messages.warning(request, "Esta solicitud no se puede aprobar en su estado actual.")
            return redirect('detalle_solicitud', pk=pk)

        if hasattr(solicitud, 'orden_de_compra'):
            messages.warning(request, f"Ya existe una orden de compra ({solicitud.orden_de_compra.folio}) para esta solicitud.")
            return redirect('detalle_solicitud', pk=pk)

        try:
            with transaction.atomic():
                # 1. Aprueba la solicitud
                solicitud.estatus = 'APROBADA'
                solicitud.aprobado_por = request.user
                solicitud.fecha_aprobacion = timezone.now()
                solicitud.save()

                condiciones = f"{solicitud.proveedor.dias_credito} días de crédito" if solicitud.proveedor and solicitud.proveedor.dias_credito > 0 else "Contado"

                # 2. Crea la Orden de Compra en estado BORRADOR
                orden = OrdenCompra.objects.create(
                    solicitud_origen=solicitud,
                    empresa=solicitud.empresa,
                    proveedor=solicitud.proveedor,
                    fecha_entrega_esperada=timezone.now().date() + timezone.timedelta(days=7),
                    condiciones_pago=condiciones,
                    estatus='BORRADOR',
                    creado_por=request.user,
                    usuario_creacion=request.user,
                    # Heredamos modalidad de pago por defecto (se puede cambiar al generar OC)
                    modalidad_pago='UNA_EXHIBICION' 
                )

                # 3. Crea los detalles de la OC
                for detalle_sol in solicitud.detalles.all():
                    DetalleOrdenCompra.objects.create(
                        orden_compra=orden,
                        articulo=detalle_sol.articulo,
                        cantidad=detalle_sol.cantidad,
                        precio_unitario=detalle_sol.precio_unitario,
                        descuento=0
                    )
                
                # --- MODIFICACIÓN: Lógica de CXP y Plazos ---
                try:
                    from cuentas_por_pagar.models import Factura
                    from decimal import Decimal
                    from datetime import timedelta
                    
                    # Verificamos si ya existen facturas vinculadas
                    if not hasattr(orden, 'factura_cxp') and not orden.factura_cxp_set.exists() if hasattr(orden, 'factura_cxp_set') else True:
                        
                        # --- LÓGICA PARA PLAZOS ---
                        if orden.modalidad_pago == 'A_PLAZOS' and orden.cantidad_plazos and orden.cantidad_plazos > 1:
                            monto_por_plazo = orden.total_general / Decimal(orden.cantidad_plazos)
                            
                            for i in range(1, orden.cantidad_plazos + 1):
                                # Nombre: CXP-OC-XXXXX-1, CXP-OC-XXXXX-2...
                                numero_cxp = f"CXP-{orden.folio}-{i}"
                                
                                # Fecha: Cada plazo vence 30 días después del anterior (aproximado)
                                fecha_vencimiento = timezone.now().date() + timedelta(days=30 * i)
                                
                                Factura.objects.create(
                                    orden_compra=orden,
                                    numero_factura=numero_cxp,
                                    fecha_emision=timezone.now().date(),
                                    fecha_vencimiento=fecha_vencimiento,
                                    monto=monto_por_plazo,
                                    creado_por=request.user,
                                    descripcion=f"Plazo {i} de {orden.cantidad_plazos} - OC {orden.folio}" # Opcional si el modelo tiene descripción
                                )
                            messages.success(request, f"Solicitud aprobada. OC {orden.folio} generada con {orden.cantidad_plazos} plazos en CXP.")

                        # --- LÓGICA PARA PAGO ÚNICO ---
                        else:
                            # Nombre: CXP-OC-XXXXX
                            numero_cxp = f"CXP-{orden.folio}"
                            
                            # Fecha vencimiento según días de crédito del proveedor
                            dias_credito = getattr(orden.proveedor, 'dias_credito', 0)
                            fecha_vencimiento = timezone.now().date() + timedelta(days=dias_credito)
                            
                            Factura.objects.create(
                                orden_compra=orden,
                                numero_factura=numero_cxp,
                                fecha_emision=timezone.now().date(),
                                fecha_vencimiento=fecha_vencimiento,
                                monto=orden.total_general,
                                creado_por=request.user
                            )
                            messages.success(request, f"Solicitud aprobada. OC {orden.folio} y cuenta por pagar {numero_cxp} generadas.")
                    
                except ImportError:
                    messages.success(request, f"Solicitud aprobada y OC {orden.folio} generada. (Módulo CXP no encontrado)")
                except Exception as e:
                    print(f"Error al generar CXP: {e}")
                    messages.warning(request, f"Solicitud aprobada y OC {orden.folio} generada, pero hubo un error creando la cuenta por pagar: {e}")
                # --- FIN MODIFICACIÓN ---
        
        except Exception as e:
            messages.error(request, f"Ocurrió un error al aprobar la solicitud: {e}")

        return redirect('detalle_solicitud', pk=pk)
    
    return HttpResponseForbidden()

@login_required
def rechazar_solicitud(request, pk):
    if request.method == 'POST':
        solicitud = get_object_or_404(SolicitudCompra, pk=pk)
        # Lógica de permisos
        if solicitud.estatus == 'PENDIENTE_APROBACION':
            solicitud.estatus = 'RECHAZADA'
            solicitud.save()
            messages.error(request, f"Solicitud {solicitud.folio} ha sido RECHAZADA.")
        else:
            messages.warning(request, "Esta solicitud no se puede rechazar en su estado actual.")
        return redirect('detalle_solicitud', pk=pk)
    return HttpResponseForbidden()

# --- GENERACIÓN Y CRUD DE ÓRDENES DE COMPRA ---

class OrdenCompraListView(LoginRequiredMixin, ListView):
    model = OrdenCompra
    template_name = 'compras/orden_compra_lista.html'
    context_object_name = 'ordenes'
    paginate_by = 15
    
    # --- CAMBIO AQUÍ: Cambiamos '-fecha_emision' por '-id' ---
    # '-id' ordena del ID más alto al más bajo (Folio más nuevo al más viejo)
    ordering = ['-id'] 
    # ---------------------------------------------------------

    def get_queryset(self):
        """
        Sobrescribe el método para añadir la lógica de filtrado
        basada en los parámetros GET de la URL.
        """
        queryset = super().get_queryset().select_related(
            'empresa', 'proveedor', 'solicitud_origen', 'creado_por',
            'solicitud_origen__lugar' 
        )

        # --- Obtiene parámetros del formulario de filtros ---
        folio = self.request.GET.get('folio', '').strip()
        proveedor_id = self.request.GET.get('proveedor')
        empresa_id = self.request.GET.get('empresa')
        lugar_id = self.request.GET.get('lugar') 
        estatus = self.request.GET.get('estatus')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        # --- Aplica filtros al queryset si los parámetros existen ---
        if folio:
            queryset = queryset.filter(folio__icontains=folio)
        if proveedor_id:
            queryset = queryset.filter(proveedor_id=proveedor_id)
        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)
        if lugar_id:
            queryset = queryset.filter(solicitud_origen__lugar_id=lugar_id)
        if estatus:
            queryset = queryset.filter(estatus=estatus)
        if start_date:
            queryset = queryset.filter(fecha_emision__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(fecha_emision__date__lte=end_date)
            
        # Aseguramos que el ordenamiento se aplique incluso después de filtrar
        return queryset.order_by('-id')

class OrdenCompraDetailView(LoginRequiredMixin, DetailView):
    model = OrdenCompra
    template_name = 'compras/orden_compra_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orden = self.object
        
        # Información del checklist
        context['checklist'] = {
            'factura': {
                'completado': orden.factura_subida,
                'archivo': orden.factura,
                'subido_por': orden.factura_subida_por,
                'fecha': orden.fecha_factura_subida,
            },
            'comprobante': {
                'completado': orden.comprobante_pago_subido,
                'archivo': orden.comprobante_pago,
                'subido_por': orden.comprobante_subido_por,
                'fecha': orden.fecha_comprobante_subido,
            }
        }
        
        return context


@login_required
def generar_orden_de_compra(request, pk):
    # 1. Obtener objetos
    solicitud = get_object_or_404(SolicitudCompra, pk=pk)
    orden_existente = get_object_or_404(OrdenCompra, solicitud_origen=solicitud)

    # 2. Validación
    if orden_existente.estatus != 'BORRADOR':
        messages.warning(request, f"La orden {orden_existente.folio} no es un borrador y no puede ser modificada aquí.")
        return redirect('detalle_orden_compra', pk=orden_existente.pk)

    # 3. FormSet
    DetalleOCFormSet = inlineformset_factory(
        OrdenCompra, 
        DetalleOrdenCompra, 
        form=DetalleOrdenCompraForm, 
        extra=0, 
        can_delete=False
    )

    if request.method == 'POST':
        form = OrdenCompraForm(request.POST, instance=orden_existente)
        formset = DetalleOCFormSet(request.POST, instance=orden_existente, prefix='detalles')

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                oc = form.save(commit=False)
                oc.estatus = 'APROBADA'
                oc.save()
                formset.save() # Guardar artículos para tener el total real
                
                # --- LÓGICA DE CONDICIONES (TEXTO) ---
                if oc.modalidad_pago == 'A_PLAZOS' and oc.cantidad_plazos > 0:
                    total_orden = oc.total_general
                    monto_individual = total_orden / Decimal(oc.cantidad_plazos)
                    oc.condiciones_pago = f"A {oc.cantidad_plazos} pagos de ${monto_individual:,.2f}"
                    oc.save()

                # --- INTEGRACIÓN CON CUENTAS POR PAGAR (CXP) ---
                try:
                    from cuentas_por_pagar.models import Factura
                    from datetime import timedelta
                    
                    # 1. Calcular Fecha de Vencimiento basada en Días de Crédito
                    dias_credito = 0
                    if oc.proveedor and oc.proveedor.dias_credito:
                        dias_credito = oc.proveedor.dias_credito
                    
                    fecha_emision = timezone.now().date()
                    fecha_vencimiento = fecha_emision + timedelta(days=dias_credito)
                    
                    # 2. Determinar cantidad de plazos para CXP
                    num_plazos_cxp = 1
                    if oc.modalidad_pago == 'A_PLAZOS' and oc.cantidad_plazos > 1:
                        num_plazos_cxp = oc.cantidad_plazos

                    # 3. Crear o Actualizar la Factura Única (Relación 1 a 1)
                    # Usamos update_or_create para que si ya existe, se actualicen los datos
                    # (ej: si cambiaste de Contado a Plazos, se actualiza la factura existente)
                    Factura.objects.update_or_create(
                        orden_compra=oc,
                        defaults={
                            'proveedor': oc.proveedor,
                            # Usamos un folio temporal si no tiene uno fiscal real aún
                            'numero_factura': f"REF-{oc.folio}", 
                            'fecha_emision': fecha_emision,
                            'fecha_vencimiento': fecha_vencimiento,
                            'monto': oc.total_general,
                            'cantidad_plazos': num_plazos_cxp, # Aquí se pasan los plazos reales
                            'creado_por': request.user,
                            'estatus': 'PENDIENTE',
                            'pagada': False,
                            'notas': f"Generada autom. desde OC {oc.folio}. Condiciones: {oc.condiciones_pago}"
                        }
                    )
                        
                except ImportError:
                    print("Advertencia: El módulo cuentas_por_pagar no está disponible.")
                except Exception as e:
                    print(f"Error al generar CXP: {e}")
                # -----------------------------------------------

            messages.success(request, f"Orden de Compra {oc.folio} aprobada y enviada a Cuentas por Pagar.")
            return redirect('detalle_orden_compra', pk=oc.pk)
        else:
            messages.error(request, "Hay errores en el formulario.")
    
    else:
        form = OrdenCompraForm(instance=orden_existente)
        formset = DetalleOCFormSet(instance=orden_existente, prefix='detalles')

    zipped_forms_and_articles = []
    for formulario in formset:
        articulo = formulario.instance.articulo
        zipped_forms_and_articles.append((formulario, articulo))

    context = {
        'form': form,
        'formset': formset,
        'solicitud': solicitud,
        'zipped_forms_and_articles': zipped_forms_and_articles,
        'today_str': timezone.now().date().strftime('%Y-%m-%d'),
        'titulo': "Generar Orden de Compra"
    }
    return render(request, 'compras/orden_compra_generar.html', context)
@login_required
def get_articulos_por_empresa(request, empresa_id):
    # Obtenemos el primer precio de proveedor asociado a cada artículo
    primer_proveedor_precio = ArticuloProveedor.objects.filter(
        articulo=F('articulo_id')
    ).order_by('pk').values('precio_unitario')[:1]

    articulos = Articulo.objects.filter(
        empresa_id=empresa_id, activo=True
    ).annotate(
        # Anotamos el precio del primer proveedor como 'precio_base'
        precio_base=primer_proveedor_precio
    ).values(
        'id', 'nombre', 'sku', 'precio_base', 
        'lleva_iva', 'lleva_retencion_isr', 'lleva_retencion_iva'
    )
    
    return JsonResponse({'articulos': list(articulos)})

@login_required
def get_proveedores_por_articulo(request, articulo_id):
    proveedores = ArticuloProveedor.objects.filter(articulo_id=articulo_id).select_related('proveedor')
    data = [{
        'id': ap.proveedor.id,
        'nombre': ap.proveedor.razon_social,
        'precio': ap.precio_unitario
    } for ap in proveedores]
    return JsonResponse({'proveedores': data})

@login_required
def editar_solicitud(request, pk):
    solicitud = get_object_or_404(SolicitudCompra, pk=pk)

    # --- INICIO DE LA MODIFICACIÓN ---
    # REGLA: No se puede editar una solicitud que ya ha sido procesada.
    if solicitud.estatus in ['APROBADA', 'RECHAZADA', 'CERRADA']:
        messages.error(request, f"La solicitud {solicitud.folio} no se puede editar porque su estatus es '{solicitud.get_estatus_display()}'.")
        return redirect('detalle_solicitud', pk=solicitud.pk)
    # --- FIN DE LA MODIFICACIÓN ---

    DetalleFormSet = inlineformset_factory(
        SolicitudCompra, 
        DetalleSolicitud, 
        form=DetalleSolicitudForm, 
        extra=1, 
        can_delete=True
    )

    if request.method == 'POST':
        form = SolicitudCompraForm(request.POST, request.FILES, instance=solicitud)
        proveedor_id = request.POST.get('proveedor')
        formset = DetalleFormSet(
            request.POST, 
            request.FILES,
            instance=solicitud,
            prefix='detalles',
            form_kwargs={'proveedor_id': proveedor_id}
        )
    
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                solicitud_actualizada = form.save(commit=False)
                # Al editar, siempre vuelve a pendiente de aprobación
                solicitud_actualizada.estatus = 'PENDIENTE_APROBACION' 
                solicitud_actualizada.save()
                
                formset.save()
            
            messages.success(request, f'La solicitud {solicitud.folio} fue actualizada correctamente.')
            return redirect('detalle_solicitud', pk=solicitud.pk)
        else:
            # ... (manejo de errores del formulario)
            pass
    else:
        form = SolicitudCompraForm(instance=solicitud)
        formset = DetalleFormSet(instance=solicitud, prefix='detalles', form_kwargs={'proveedor_id': solicitud.proveedor_id})

    context = {
        'form': form, 'formset': formset, 'solicitud': solicitud,
        'titulo': f'Editando Solicitud: {solicitud.folio}'
    }
    return render(request, 'compras/solicitud_form.html', context)

class CategoriaListView(LoginRequiredMixin, ListView):
    model = Categoria
    template_name = 'compras/categoria_list.html'
    context_object_name = 'categorias'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Obtenemos solo las categorías principales (las que no tienen padre)
        context['categorias_principales'] = Categoria.objects.filter(parent__isnull=True).prefetch_related('subcategorias')
        return context
    
@login_required
@require_POST
def subir_factura_oc(request, pk):
    """Vista para subir factura desde el detalle de OC"""
    orden = get_object_or_404(OrdenCompra, pk=pk)
    
    if orden.estatus not in ['APROBADA', 'LISTA_PARA_AUDITAR']:
        messages.error(request, "No se puede subir factura en el estado actual de la orden.")
        return redirect('detalle_orden_compra', pk=pk)
    
    if 'factura' in request.FILES:
        orden.factura = request.FILES['factura']
        orden.factura_subida = True
        orden.factura_subida_por = request.user
        orden.fecha_factura_subida = timezone.now()
        orden.actualizar_estado_auditoria()
        
        messages.success(request, "Factura subida correctamente.")
    else:
        messages.error(request, "Debe seleccionar un archivo de factura.")
    
    return redirect('detalle_orden_compra', pk=pk)

@login_required
@require_POST
def subir_comprobante_oc(request, pk):
    """Vista para subir comprobante de pago desde el detalle de OC"""
    orden = get_object_or_404(OrdenCompra, pk=pk)
    
    if orden.estatus not in ['APROBADA', 'LISTA_PARA_AUDITAR']:
        messages.error(request, "No se puede subir comprobante en el estado actual de la orden.")
        return redirect('detalle_orden_compra', pk=pk)
    
    if 'comprobante_pago' in request.FILES:
        orden.comprobante_pago = request.FILES['comprobante_pago']
        orden.comprobante_pago_subido = True
        orden.comprobante_subido_por = request.user
        orden.fecha_comprobante_subido = timezone.now()
        orden.actualizar_estado_auditoria()
        
        messages.success(request, "Comprobante de pago subido correctamente.")
    else:
        messages.error(request, "Debe seleccionar un archivo de comprobante.")
    
    return redirect('detalle_orden_compra', pk=pk)

@login_required
@require_POST
def eliminar_documento_oc(request, pk, tipo):
    """Vista para eliminar documentos de OC"""
    orden = get_object_or_404(OrdenCompra, pk=pk)
    
    if orden.estatus in ['AUDITADA', 'CANCELADA']:
        messages.error(request, "No se pueden modificar documentos en órdenes finalizadas.")
        return redirect('detalle_orden_compra', pk=pk)
    
    try:
        if tipo == 'factura':
            orden.factura.delete(save=False)
            orden.factura = None
            orden.factura_subida = False
            orden.factura_subida_por = None
            orden.fecha_factura_subida = None
        elif tipo == 'comprobante':
            orden.comprobante_pago.delete(save=False)
            orden.comprobante_pago = None
            orden.comprobante_pago_subido = False
            orden.comprobante_subido_por = None
            orden.fecha_comprobante_subido = None
        
        orden.actualizar_estado_auditoria()
        messages.success(request, f"Documento {tipo} eliminado correctamente.")
        
    except Exception as e:
        messages.error(request, f"Error al eliminar el documento: {e}")
    
    return redirect('detalle_orden_compra', pk=pk)


class CategoriaCreateView(LoginRequiredMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'compras/generic_form.html'
    success_url = reverse_lazy('lista_categorias')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Crear Nueva Categoría"
        return context

class CategoriaUpdateView(LoginRequiredMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'compras/generic_form.html'
    success_url = reverse_lazy('lista_categorias')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f"Editando Categoría: {self.object.nombre}"
        return context

class CategoriaDeleteView(LoginRequiredMixin, DeleteView):
    model = Categoria
    template_name = 'compras/_confirm_delete.html'
    success_url = reverse_lazy('lista_categorias')
    
    
# --- AÑADE ESTOS IMPORTS AL INICIO DEL ARCHIVO ---
import json
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_POST
# -----------------------------------------------


# --- REEMPLAZA TU FUNCIÓN update_articulo_proveedor_precio CON ESTA ---
@login_required
@require_POST
def update_articulo_proveedor_precio(request):
    """
    API para actualizar el precio de un ArticuloProveedor desde el frontend.
    Es más robusta: valida que el precio sea un número decimal válido.
    """
    try:
        data = json.loads(request.body)
        articulo_id = data.get('articulo_id')
        proveedor_id = data.get('proveedor_id')
        precio_str = data.get('nuevo_precio')

        if not all([articulo_id, proveedor_id, precio_str]):
            return JsonResponse({'status': 'error', 'message': 'Faltan datos (artículo, proveedor o precio).'}, status=400)
        
        # Validación robusta del precio
        try:
            nuevo_precio = Decimal(precio_str)
        except InvalidOperation:
            return JsonResponse({'status': 'error', 'message': f"El precio '{precio_str}' no es un número válido."}, status=400)

        articulo_proveedor = get_object_or_404(
            ArticuloProveedor, 
            articulo_id=articulo_id, 
            proveedor_id=proveedor_id
        )
        
        articulo_proveedor.precio_unitario = nuevo_precio
        articulo_proveedor.save()
        
        return JsonResponse({'status': 'success', 'message': '¡Precio de catálogo actualizado!'})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Error en el formato de los datos enviados.'}, status=400)
    except ArticuloProveedor.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'No se encontró la relación artículo-proveedor en el catálogo.'}, status=404)
    except Exception as e:
        # Log del error para depuración en el servidor
        print(f"Error inesperado al actualizar precio: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ocurrió un error inesperado en el servidor.'}, status=500)
    
class OrdenCompraArchivosUpdateView(LoginRequiredMixin, UpdateView):
    """
    Vista para subir y administrar los archivos de una Orden de Compra.
    Se añade una validación para impedir la edición si la OC ya fue auditada.
    """
    model = OrdenCompra
    form_class = OrdenCompraArchivosForm
    template_name = 'compras/orden_compra_archivos_form.html'

    def get_success_url(self):
        return reverse_lazy('detalle_orden_compra', kwargs={'pk': self.object.pk})

    def dispatch(self, request, *args, **kwargs):
        # Obtenemos la orden que se intenta editar
        orden = self.get_object()
        # REGLA: Si la orden ya está auditada o cancelada, no se pueden cambiar los archivos.
        if orden.estatus in ['AUDITADA', 'CANCELADA']:
            messages.error(request, f"La orden {orden.folio} ya está finalizada y no se pueden modificar sus archivos.")
            return redirect('detalle_orden_compra', pk=orden.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f"Administrar Archivos de OC: {self.object.folio}"
        return context

@login_required
def orden_compra_pdf_view(request, pk):
    """
    Vista que genera y devuelve el PDF de una Orden de Compra.
    """
    orden = get_object_or_404(OrdenCompra, pk=pk)
    template_path = 'compras/orden_compra_pdf_template.html'
    
    if not orden.usuario_creacion:
        orden.usuario_creacion = orden.creado_por
    
    # --- INICIO DE LA MODIFICACIÓN ---
    # Convierte el total a palabras para el template
    total_general = orden.total_general
    parte_entera = int(total_general)
    parte_decimal = int(round((total_general - parte_entera) * 100))

    total_en_letra = f"{num2words(parte_entera, lang='es').capitalize()} {orden.get_moneda_display()} con {parte_decimal:02d}/100"
    # --- FIN DE LA MODIFICACIÓN ---

    context = {
        'orden': orden,
        'empresa': orden.empresa,
        'total_en_letra': total_en_letra # <--- AÑADE ESTA LÍNEA AL CONTEXTO
    }

    # Create an HTTP response with the content type for PDF
    response = HttpResponse(content_type='application/pdf')
    # Quita 'attachment;' si quieres que se vea en el navegador en lugar de descargarse
    response['Content-Disposition'] = f'inline; filename="OC_{orden.folio}.pdf"' 

    # Find the template and render it
    template = get_template(template_path)
    html = template.render(context)

    # Create the PDF
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
       return HttpResponse('Hubo un error al generar el PDF <pre>' + html + '</pre>')
    return response

@login_required
@require_POST
def iniciar_auditoria_oc(request, pk):
    """
    Cambia el estatus de una Orden de Compra a 'Auditada'.
    """
    # --- CORRECCIÓN DEL ERROR DE TIPEO AQUÍ ---
    orden = get_object_or_404(OrdenCompra, pk=pk)
    # -----------------------------------------

    # Doble validación: solo se puede auditar si está lista
    if orden.lista_para_auditoria:
        orden.estatus = 'AUDITADA'
        orden.save()
        messages.success(request, f"La Orden de Compra {orden.folio} ha sido marcada como 'Auditada' exitosamente.")
    else:
        messages.error(request, "Esta orden aún no tiene todos los documentos para ser auditada.")
    
    return redirect('detalle_orden_compra', pk=pk)

@login_required
@require_POST
def cancelar_orden_compra(request, pk):
    """
    Cancela una Orden de Compra.
    - Si el estatus es 'Aprobada', reabre la solicitud de origen.
    - Si el estatus es 'Borrador', simplemente la cancela.
    - No permite cancelar si ya está 'Auditada'.
    """
    orden = get_object_or_404(OrdenCompra, pk=pk)

    # REGLA 1: No se puede cancelar una orden que ya ha sido auditada.
    if orden.estatus == 'AUDITADA':
        messages.error(request, f"La orden {orden.folio} ya fue auditada y no puede ser cancelada.")
        return redirect('detalle_orden_compra', pk=pk)

    # REGLA 2: No se puede cancelar si ya está cancelada.
    if orden.estatus == 'CANCELADA':
        messages.warning(request, f"La orden {orden.folio} ya se encuentra cancelada.")
        return redirect('detalle_orden_compra', pk=pk)

    # REGLA 3: Solo se puede cancelar desde 'Aprobada' o 'Borrador'
    if orden.estatus not in ['APROBADA', 'BORRADOR']:
        messages.error(request, f"La orden no puede ser cancelada en su estatus actual ('{orden.get_estatus_display()}').")
        return redirect('detalle_orden_compra', pk=pk)

    try:
        with transaction.atomic():
            estatus_anterior = orden.get_estatus_display()
            orden.estatus = 'CANCELADA'
            orden.save()

            # Si la orden venía de una solicitud, la reabrimos
            if orden.solicitud_origen and estatus_anterior == 'Aprobada':
                solicitud = orden.solicitud_origen
                solicitud.estatus = 'APROBADA'
                solicitud.save()
                messages.success(request, f"Orden {orden.folio} cancelada. La solicitud {solicitud.folio} ha sido reabierta.")
            else:
                messages.success(request, f"Orden de Compra {orden.folio} ha sido cancelada correctamente.")

    except Exception as e:
        messages.error(request, f"Ocurrió un error inesperado al cancelar la orden: {e}")

    return redirect('detalle_orden_compra', pk=pk)

@login_required
def redirigir_a_generar_oc(request, pk):
    """
    Toma la ID de una Orden de Compra, encuentra su solicitud de origen
    y redirige a la página para terminar esa OC.
    """
    orden = get_object_or_404(OrdenCompra, pk=pk)
    
    if not orden.solicitud_origen:
        messages.error(request, "Esta orden no se puede editar de esta forma porque no tiene una solicitud de origen.")
        return redirect('lista_ordenes_compra')

    return redirect('generar_orden_de_compra', pk=orden.solicitud_origen.pk)
from ternium.models import Empresa, Origen, Lugar
@login_required
def get_origenes_por_empresa(request, empresa_id):
    """
    API view para obtener los Lugares tipo 'ORIGEN' de una empresa.
    Responde a la llamada 'fetch' del JavaScript del formulario de Artículos.
    """
    try:
        # 1. Busca la empresa seleccionada
        empresa = Empresa.objects.get(pk=empresa_id)
        
        # 2. Esta es la lógica que TÚ quieres:
        # Busca en el modelo 'Lugar' todos los que...
        # ...estén asociados con esta 'empresa' (vía el M2M 'empresas')
        # ...Y sean de tipo 'ORIGEN'.
        lugares_tipo_origen = Lugar.objects.filter(
            empresas=empresa,  # Filtra por la relación ManyToMany
            tipo='ORIGEN'      # Filtra por el tipo de lugar
        ).order_by('nombre').distinct() # Usamos distinct por seguridad en M2M

        # 3. Prepara los datos en el formato que el JavaScript espera
        data = {
            # ¡La llave debe seguir siendo 'origenes' porque el JavaScript la busca así!
            'origenes': [
                {'id': lugar.id, 'nombre': lugar.nombre}
                for lugar in lugares_tipo_origen
            ]
        }
        
        return JsonResponse(data)
        
    except Empresa.DoesNotExist:
        # Si la empresa no existe, devuelve una lista vacía
        return JsonResponse({'origenes': []}, status=404)
    except Exception as e:
        # Manejo de cualquier otro error
        return JsonResponse({'error': str(e)}, status=500)
    
@login_required
def get_empresas_por_operacion(request, operacion_id):
    """
    API para el formulario de Proveedores.
    Devuelve los 'Lugares' (Empresas) de una 'Empresa' (Operación).
    """
    try:
        operacion = Empresa.objects.get(pk=operacion_id)
        
        # --- VARIABLE CORREGIDA ---
        # (Aquí estaba el SyntaxError)
        empresas_lugares = Lugar.objects.filter(
            empresas=operacion, 
            tipo='ORIGEN'
        ).order_by('nombre').distinct()
        
        data = {
    'empresas': [
        {'id': lugar.id, 'nombre': lugar.nombre}
        for lugar in empresas_lugares  # <-- Asegúrate que diga 'empresas_lugares'
    ]
}
        return JsonResponse(data)
        
    except Empresa.DoesNotExist:
        return JsonResponse({'empresas': []}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@permission_required('compras.ver_reportes_compras', raise_exception=True)
def reporte_compras_excel(request):
    """
    Genera CSV con cálculos seguros usando Decimal para evitar errores de tipo float.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reporte_compras_detallado.csv"'
    response.write(u'\ufeff'.encode('utf8')) # BOM para Excel
    
    writer = csv.writer(response)
    writer.writerow([
        'Folio OC', 'Fecha Emisión', 'Estatus', 'Proveedor', 'RFC', 
        'Solicitante', 'Artículo', 'SKU', 'Categoría', 'Cantidad', 'U.M.', 
        'Precio Unit.', 'Desc. %', 'Subtotal Base', 'Tasa IVA %', 'Monto IVA', 
        'Tasa Ret %', 'Monto Ret', 'Total Línea', 'Moneda'
    ])
    
    ordenes = OrdenCompra.objects.filter(
        estatus__in=['APROBADA', 'AUDITADA', 'RECIBIDA_PARCIAL', 'RECIBIDA_TOTAL', 'CERRADA']
    ).select_related('proveedor', 'creado_por').prefetch_related('detalles__articulo__unidad_medida', 'detalles__articulo__categoria')
    
    for orden in ordenes:
        for detalle in orden.detalles.all():
            # 1. Convertir todo a Decimal seguro
            cantidad = detalle.cantidad or Decimal('0')
            precio = detalle.precio_unitario or Decimal('0')
            descuento_val = detalle.descuento or Decimal('0')
            
            # 2. Cálculos Base
            subtotal_bruto = cantidad * precio
            monto_descuento = subtotal_bruto * (descuento_val / Decimal('100'))
            subtotal_neto = subtotal_bruto - monto_descuento
            
            # 3. Impuestos (Usando Decimal para los porcentajes)
            articulo = detalle.articulo
            tasa_iva = articulo.porcentaje_iva or Decimal('0')
            tasa_ret = articulo.porcentaje_retencion_iva or Decimal('0')
            
            monto_iva = subtotal_neto * (tasa_iva / Decimal('100'))
            monto_ret = subtotal_neto * (tasa_ret / Decimal('100'))
            
            total_linea = subtotal_neto + monto_iva - monto_ret
            
            # 4. Escribir fila
            writer.writerow([
                orden.folio,
                orden.fecha_emision.strftime('%d/%m/%Y'),
                orden.get_estatus_display(),
                orden.proveedor.razon_social,
                orden.proveedor.rfc,
                orden.creado_por.get_full_name() or orden.creado_por.username,
                articulo.nombre,
                articulo.sku or 'N/A',
                articulo.categoria.nombre if articulo.categoria else 'General',
                f"{cantidad:.2f}",
                articulo.unidad_medida.abreviatura if articulo.unidad_medida else 'N/A',
                f"{precio:.2f}",
                f"{descuento_val:.2f}",
                f"{subtotal_neto:.2f}",
                f"{tasa_iva:.0f}",
                f"{monto_iva:.2f}",
                f"{tasa_ret:.0f}",
                f"{monto_ret:.2f}",
                f"{total_linea:.2f}",
                orden.moneda
            ])
            
    return response