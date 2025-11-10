# compras/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.forms import inlineformset_factory
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
    DetalleSolicitudForm, OrdenCompraForm, DetalleOrdenCompraForm, CategoriaForm,OrdenCompraArchivosForm,SolicitudCompra,
)
# Modelos de la app ternium
from ternium.models import Empresa
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from ternium.models import Empresa, Origen # Asegúrate que Origen esté importado

# --- DASHBOARD ---

@login_required
def dashboard_compras(request):
    solicitudes_pendientes = SolicitudCompra.objects.filter(estatus='PENDIENTE_APROBACION').count()
    ordenes_abiertas = OrdenCompra.objects.filter(estatus='APROBADA').count()
    total_proveedores = Proveedor.objects.filter(activo=True).count()

    context = {
        'solicitudes_pendientes': solicitudes_pendientes,
        'ordenes_abiertas': ordenes_abiertas,
        'total_proveedores': total_proveedores,
    }
    return render(request, 'compras/dashboard.html', context)

# --- CRUD PROVEEDORES ---

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

class SolicitudCompraListView(LoginRequiredMixin, ListView):
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
    Devuelve los artículos de un proveedor con su precio y todos los detalles
    adicionales que el frontend necesita.
    """
    # --- INICIO DE LA CORRECCIÓN ---
    # 1. Optimizamos la consulta para traer los datos relacionados en una sola petición a la BD.
    articulos_prov = ArticuloProveedor.objects.filter(
        proveedor_id=proveedor_id, 
        articulo__activo=True
    ).select_related('articulo', 'articulo__categoria', 'articulo__unidad_medida')
    
    # 2. Construimos la respuesta incluyendo los campos que faltaban.
    data = []
    for ap in articulos_prov:
        articulo = ap.articulo
        data.append({
            'id': articulo.id,
            'nombre': articulo.nombre,
            'sku': articulo.sku,
            'precio': ap.precio_unitario,
            'lleva_iva': articulo.lleva_iva,
            'lleva_retencion_iva': articulo.lleva_retencion_iva,
            
            # --- Campos añadidos que solucionan el problema ---
            'unidad_medida': articulo.unidad_medida.abreviatura if articulo.unidad_medida else None,
            'categoria': str(articulo.categoria) if articulo.categoria else None,
            'tipo': articulo.get_tipo_display(), # Devuelve el texto legible ('Producto' o 'Servicio')
        })
    
    return JsonResponse({'articulos': data})


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
        
        # --- INICIO DE LA CORRECCIÓN ---
        # Obtenemos el ID del proveedor directamente del POST para pasarlo al formset
        proveedor_id = request.POST.get('proveedor')
        
        formset = DetalleFormSet(
            request.POST, 
            request.FILES,
            prefix='detalles',
            # ¡Clave! Pasamos el proveedor_id para que los formularios de detalle
            # sepan qué queryset de artículos usar durante la validación.
            form_kwargs={'proveedor_id': proveedor_id} 
        )
        # --- FIN DE LA CORRECCIÓN ---
        
        if form.is_valid() and formset.is_valid() and formset.has_changed():
            try:
                with transaction.atomic():
                    solicitud = form.save(commit=False)
                    solicitud.solicitante = request.user
                    solicitud.estatus = 'PENDIENTE_APROBACION'
                    solicitud.save() # Guardamos la solicitud principal
                    
                    formset.instance = solicitud
                    formset.save() # Guardamos los detalles
                    
                    messages.success(request, f'Solicitud {solicitud.folio} enviada para aprobación.')
                    return redirect('detalle_solicitud', pk=solicitud.pk)
            except Exception as e:
                messages.error(request, f"Error al crear la solicitud: {e}")
        else:
            # Lógica para mostrar errores de validación
            if not form.is_valid():
                messages.error(request, f"Error en datos generales: {form.errors.as_text()}")
            if not formset.is_valid():
                for i, form_errors in enumerate(formset.errors):
                    if form_errors:
                        messages.error(request, f"Error en el artículo #{i+1}: {form_errors.as_text()}")
            if not formset.has_changed():
                messages.error(request, "La solicitud debe tener al menos un artículo.")

    else: # Petición GET
        form = SolicitudCompraForm()
        # Al crear, no hay proveedor, por lo que el form_kwargs es None
        formset = DetalleFormSet(prefix='detalles', form_kwargs={'proveedor_id': None})

    context = { 'form': form, 'formset': formset, 'titulo': 'Nueva Solicitud de Compra' }
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

                # --- INICIO DE LA CORRECCIÓN ---
                # Se establece un valor por defecto o vacío para las condiciones de pago,
                # en lugar de usar los días de crédito.
                condiciones = f"{solicitud.proveedor.dias_credito} días de crédito" if solicitud.proveedor and solicitud.proveedor.dias_credito > 0 else "Contado"
                # --- FIN DE LA CORRECCIÓN ---

                # 2. Crea la Orden de Compra en estado BORRADOR
                orden = OrdenCompra.objects.create(
                    solicitud_origen=solicitud,
                    empresa=solicitud.empresa,
                    proveedor=solicitud.proveedor,
                    fecha_entrega_esperada=timezone.now().date() + timezone.timedelta(days=7),
                    condiciones_pago=condiciones, # Usamos la variable corregida
                    estatus='BORRADOR',
                    creado_por=request.user,
                    usuario_creacion=request.user,
                )

                # 3. Crea los detalles de la OC a partir de los detalles de la solicitud
                for detalle_sol in solicitud.detalles.all():
                    DetalleOrdenCompra.objects.create(
                        orden_compra=orden,
                        articulo=detalle_sol.articulo,
                        cantidad=detalle_sol.cantidad,
                        precio_unitario=detalle_sol.precio_unitario,
                        descuento=0
                    )
                
                # --- NUEVO: CREAR FACTURA AUTOMÁTICA EN CXP ---
                try:
                    from cuentas_por_pagar.models import Factura
                    from datetime import datetime
                    
                    # Verificar si ya existe factura para evitar duplicados
                    if not hasattr(orden, 'factura_cxp'):
                        # Generar número de factura único
                        numero_factura = f"FAC-{orden.folio}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        
                        # Calcular fecha de vencimiento (usar días de crédito del proveedor si existe)
                        dias_credito = getattr(orden.proveedor, 'dias_credito', 30)
                        fecha_vencimiento = timezone.now().date() + timezone.timedelta(days=dias_credito)
                        
                        # Crear la factura en CXP
                        factura = Factura.objects.create(
                            orden_compra=orden,
                            numero_factura=numero_factura,
                            fecha_emision=timezone.now().date(),
                            fecha_vencimiento=fecha_vencimiento,
                            monto=orden.total_general,
                            creado_por=request.user
                        )
                        
                        messages.success(request, f"Solicitud {solicitud.folio} aprobada. Se ha generado el borrador de la OC {orden.folio} y la factura {factura.numero_factura} en CXP.")
                    else:
                        messages.success(request, f"Solicitud {solicitud.folio} aprobada. Se ha generado el borrador de la OC {orden.folio}.")
                        
                except ImportError:
                    # Si no se puede importar el modelo de CXP, continuar sin crear factura
                    messages.success(request, f"Solicitud {solicitud.folio} aprobada. Se ha generado el borrador de la OC {orden.folio}. (No se pudo crear factura en CXP)")
                except Exception as e:
                    # Si hay error al crear factura, continuar pero mostrar advertencia
                    messages.warning(request, f"Solicitud {solicitud.folio} aprobada. Se ha generado el borrador de la OC {orden.folio}. (Error al crear factura: {e})")
                # --- FIN NUEVO ---
        
        except Exception as e:
            messages.error(request, f"Ocurrió un error al aprobar la solicitud y generar la OC: {e}")

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
    ordering = ['-fecha_emision']

    def get_queryset(self):
        """
        Sobrescribe el método para añadir la lógica de filtrado
        basada en los parámetros GET de la URL.
        """
        # --- INICIO MODIFICACIÓN ---
        # Añadimos 'solicitud_origen__lugar' para poder filtrar por el lugar
        # de la solicitud de origen.
        queryset = super().get_queryset().select_related(
            'empresa', 'proveedor', 'solicitud_origen', 'creado_por',
            'solicitud_origen__lugar' # <-- AÑADIDO
        )
        # --- FIN MODIFICACIÓN ---

        # --- Obtiene parámetros del formulario de filtros ---
        folio = self.request.GET.get('folio', '').strip()
        proveedor_id = self.request.GET.get('proveedor')
        empresa_id = self.request.GET.get('empresa')
        lugar_id = self.request.GET.get('lugar') # <-- AÑADIDO
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
        
        # --- FILTRO AÑADIDO ---
        # Filtra por el 'lugar' de la solicitud de origen.
        # Asume que las OCs manuales no se filtrarán por lugar (o puedes ajustar la lógica).
        if lugar_id:
            queryset = queryset.filter(solicitud_origen__lugar_id=lugar_id)
        # --- FIN FILTRO AÑADIDO ---
            
        if estatus:
            queryset = queryset.filter(estatus=estatus)
        if start_date:
            queryset = queryset.filter(fecha_emision__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(fecha_emision__date__lte=end_date)
            
        return queryset

    def get_context_data(self, **kwargs):
        """
        Añade al contexto los datos necesarios para popular los
        selects del formulario de filtros.
        """
        context = super().get_context_data(**kwargs)
        
        # --- Datos para los dropdowns del formulario de filtros ---
        context['empresas'] = Empresa.objects.all().order_by('nombre')
        context['proveedores'] = Proveedor.objects.filter(activo=True).order_by('razon_social')
        context['estatus_choices'] = OrdenCompra.ESTATUS_CHOICES
        
        # --- LÍNEA AÑADIDA ---
        context['lugares'] = Lugar.objects.filter(tipo='ORIGEN').order_by('nombre')
        # --- FIN LÍNEA AÑADIDA ---

        # --- Mantiene el estado del formulario ---
        context['filtros_aplicados'] = self.request.GET
        
        return context

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
    solicitud = get_object_or_404(SolicitudCompra, pk=pk)
    orden_existente = get_object_or_404(OrdenCompra, solicitud_origen=solicitud)

    if orden_existente.estatus != 'BORRADOR':
        messages.warning(request, f"La orden {orden_existente.folio} no es un borrador y no puede ser modificada aquí.")
        return redirect('detalle_orden_compra', pk=orden_existente.pk)

    articulos_para_template = [detalle.articulo for detalle in orden_existente.detalles.select_related('articulo')]
    
    DetalleOCFormSet = inlineformset_factory(OrdenCompra, DetalleOrdenCompra, form=DetalleOrdenCompraForm, extra=0, can_delete=False)

    if request.method == 'POST':
        form = OrdenCompraForm(request.POST, instance=orden_existente)
        formset = DetalleOCFormSet(request.POST, instance=orden_existente, prefix='detalles')

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                oc = form.save(commit=False)
                oc.estatus = 'APROBADA'
                oc.save()
                formset.save()
                
                # --- NUEVO: ACTUALIZAR FACTURA EN CXP SI EXISTE ---
                try:
                    from cuentas_por_pagar.models import Factura
                    if hasattr(oc, 'factura_cxp'):
                        factura = oc.factura_cxp
                        factura.monto = oc.total_general  # Actualizar monto por si cambió
                        factura.save()
                        messages.success(request, f"Orden de Compra {oc.folio} ha sido finalizada y aprobada exitosamente. Factura {factura.numero_factura} actualizada en CXP.")
                    else:
                        messages.success(request, f"Orden de Compra {oc.folio} ha sido finalizada y aprobada exitosamente.")
                except Exception as e:
                    messages.success(request, f"Orden de Compra {oc.folio} ha sido finalizada y aprobada exitosamente. (No se pudo actualizar factura en CXP: {e})")
                # --- FIN NUEVO ---
                
                return redirect('detalle_orden_compra', pk=oc.pk)
        else:
            messages.error(request, "El formulario no es válido. Revisa los errores.")
            
    else: # Petición GET
        form = OrdenCompraForm(instance=orden_existente)
        formset = DetalleOCFormSet(instance=orden_existente, prefix='detalles')

    titulo = f"Terminar y Aprobar OC {orden_existente.folio} (Solicitud: {solicitud.folio})"
    zipped_data = zip(formset.forms, articulos_para_template)

    context = {
        'form': form,
        'formset': formset,
        'zipped_forms_and_articles': zipped_data,
        'solicitud': solicitud,
        'titulo': titulo,
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
