# facturacion/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required 
from django.db import transaction
from django.core.paginator import Paginator  # <--- AGREGA ESTA LÍNEA
import json
from .models import Colonia, CodigoPostalFiscal
import requests # <--- Para consultar los timbres
import csv  # <--- AGREGA ESTA LÍNEA AQUÍ
from .models import SeriePersonalizada
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.http import JsonResponse
from .models import Colonia, Municipio, Estado
from django.http import HttpResponse
from num2words import num2words 
from .models import CatalogoSAT #
from .models import SatObjetoImpuesto  # <--- Importante
from django.template.loader import render_to_string
from django.db.models import Sum, Q, Value, DecimalField, Count, Case, When, F
from .services import buscar_en_fiscalapi, timbrar_factura_api, timbrar_pago_api, cancelar_cfdi_api, API_URL, API_KEY, ISSUER_ID # Importamos credenciales
from django.core.files.base import ContentFile
import base64
import qrcode
import base64
from io import BytesIO
import xml.etree.ElementTree as ET
from .forms import NotaCreditoLibreForm 

# Modelos
from .models import Factura, ConceptoFactura, DatosFiscales, ComplementoPago, PagoDoctoRelacionado
from ternium.models import Remision, Cliente, Lugar

# Formularios
from .forms import (
    GenerarFacturaForm, 
    NuevaFacturaLibreForm, 
    ConfigurarEmisorForm, 
    DatosFiscalesClienteForm,
    PagoForm,
    ComplementoPagoCabeceraForm
)

try:
    from weasyprint import HTML
except ImportError:
    HTML = None
    
import base64
from django.core.files.base import ContentFile
from .services import timbrar_pago_api # <--- IMPORTANTE

# --- HELPER ---
def get_emisor_fiscal():
    return DatosFiscales.objects.filter(es_emisor=True).first()

# --- VISTAS ---

@login_required
@permission_required('facturacion.view_factura', raise_exception=True)
def dashboard_facturacion(request):
    """
    Dashboard principal con cálculos reales de impuestos desglosados.
    """
    # -----------------------------------------------------
    # A. Consulta Base con Cálculos Reales (ANNOTATE)
    # -----------------------------------------------------
    facturas = Factura.objects.all().select_related('receptor').prefetch_related('remisiones', 'conceptos').annotate(
        # 1. Calcular ISR Real (Suma de conceptos donde la clave de retención es '001')
        isr_monto=Sum(
            Case(
                When(conceptos__retencion_impuesto_clave='001', then='conceptos__iva_ret_importe'),
                default=Value(0),
                output_field=DecimalField()
            )
        ),
        # 2. Calcular IEPS Real (Suma de conceptos donde la clave de traslado es '003')
        ieps_monto=Sum(
        Case(
            When(conceptos__traslado_impuesto_clave='003', then='conceptos__iva_importe'),
            default=Value(0),
            output_field=DecimalField()
        )
    ),
    # 3. Retención de IVA Pura (Ya lo tienes en tu código, ¡pero no lo usas en el HTML!)
    ret_iva_monto=Sum(
        Case(
            When(conceptos__retencion_impuesto_clave='002', then='conceptos__iva_ret_importe'),
            default=Value(0),
            output_field=DecimalField()
        )
    ),
    # 4. AGREGAR ESTO: IVA Trasladado Puro (Solo clave 002)
    iva_trasaladado_puro=Sum(
        Case(
            When(conceptos__traslado_impuesto_clave='002', then='conceptos__iva_importe'),
            default=Value(0),
            output_field=DecimalField()
        )
    )
).order_by('-fecha_emision')

    pagos = ComplementoPago.objects.select_related('receptor')\
        .prefetch_related('documentos_relacionados', 'documentos_relacionados__factura')\
        .all().order_by('-fecha_pago')

    # -----------------------------------------------------
    # B. Filtros (Igual que antes)
    # -----------------------------------------------------
    q_cliente = request.GET.get('q_cliente')
    q_folio = request.GET.get('q_folio')
    q_estado = request.GET.get('q_estado')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if q_cliente:
        facturas = facturas.filter(receptor__razon_social__icontains=q_cliente)
        pagos = pagos.filter(receptor__razon_social__icontains=q_cliente)
    
    if q_folio:
        facturas = facturas.filter(
            Q(folio__icontains=q_folio) | Q(folio_fiscal__icontains=q_folio)
        )
        pagos = pagos.filter(
            Q(serie__icontains=q_folio) | 
            Q(folio__icontains=q_folio) | 
            Q(uuid__icontains=q_folio) |
            Q(documentos_relacionados__factura__folio__icontains=q_folio)
        ).distinct()

    if q_estado:
        facturas = facturas.filter(estado=q_estado)
        if q_estado == 'timbrado':
            pagos = pagos.filter(timbrado=True)
        elif q_estado == 'pendiente':
            pagos = pagos.filter(timbrado=False)

    if fecha_inicio:
        facturas = facturas.filter(fecha_emision__date__gte=fecha_inicio)
        pagos = pagos.filter(fecha_pago__date__gte=fecha_inicio)
    
    if fecha_fin:
        facturas = facturas.filter(fecha_emision__date__lte=fecha_fin)
        pagos = pagos.filter(fecha_pago__date__lte=fecha_fin)

    # -----------------------------------------------------
    # C. KPIs
    # -----------------------------------------------------
    total_timbradas = Factura.objects.filter(estado='timbrado').count()
    total_pendientes = Factura.objects.filter(estado='pendiente').count()
    total_canceladas = Factura.objects.filter(estado='cancelada').count()

    timbres_disponibles = obtener_saldo_timbres()

    clientes_combo = DatosFiscales.objects.filter(
        facturas_recibidas__isnull=False
    ).values_list('razon_social', flat=True).distinct().order_by('razon_social')

    context = {
        'facturas': facturas,
        'pagos': pagos,
        'total_timbradas': total_timbradas,
        'total_pendientes': total_pendientes,
        'total_canceladas': total_canceladas,
        'timbres_disponibles': timbres_disponibles,
        'clientes_combo': clientes_combo,
        'q_cliente': q_cliente,
        'q_folio': q_folio,
        'q_estado': q_estado,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
    }

    return render(request, 'facturacion/dashboard.html', context)

@login_required
@permission_required('facturacion.change_datosfiscales', raise_exception=True)
def configurar_emisor(request):
    emisor_actual = DatosFiscales.objects.filter(es_emisor=True).first()

    if request.method == 'POST':
        form = ConfigurarEmisorForm(request.POST)
        if form.is_valid():
            lugar = form.cleaned_data['lugar_origen']
            
            # 1. Validación de seguridad
            if not lugar.rfc:
                messages.error(request, f"El lugar '{lugar.nombre}' no tiene RFC capturado.")
                return redirect('configurar_emisor')

            # --- CORRECCIÓN AQUÍ ---
            # 2. NO BORRAR. Buscar el existente para actualizarlo, o crear uno si no existe.
            datos = DatosFiscales.objects.filter(es_emisor=True).first()
            
            if not datos:
                # Si no existe ninguno, creamos una instancia nueva
                datos = DatosFiscales(es_emisor=True)
            
            # 3. Actualizamos los datos (sea nuevo o existente)
            # Mapeo exacto basado en tu ternium/models.py
            datos.rfc = lugar.rfc
            datos.razon_social = lugar.razon_social or f"Sucursal {lugar.nombre}"
            datos.regimen_fiscal = lugar.regimen_fiscal or '601'
            datos.uso_cfdi = lugar.uso_cfdi or 'G03'
            datos.codigo_postal = lugar.codigo_postal
            
            # Construcción de Dirección Completa
            partes = []
            if lugar.calle: partes.append(lugar.calle)
            if lugar.numero_exterior: partes.append(f"No. {lugar.numero_exterior}")
            if lugar.numero_interior: partes.append(f"Int. {lugar.numero_interior}")
            if lugar.colonia: partes.append(f"Col. {lugar.colonia}")
            if lugar.municipio: partes.append(lugar.municipio)
            if lugar.estado: partes.append(lugar.estado)
            if lugar.pais: partes.append(lugar.pais)
            
            datos.direccion = ", ".join(partes).upper()
            
            datos.save()
            
            messages.success(request, f"✅ Configuración guardada: {datos.razon_social} ({datos.rfc})")
            return redirect('configurar_emisor')
    else:
        form = ConfigurarEmisorForm()

    return render(request, 'facturacion/configurar_emisor.html', {
        'form': form,
        'emisor_actual': emisor_actual
    })
@login_required
@permission_required('facturacion.add_factura', raise_exception=True)
def prefacturar_remisiones(request):
    if request.method != 'POST':
        return redirect('remisiones_por_facturar')

    remisiones_ids = request.POST.getlist('remisiones_ids')
    if not remisiones_ids:
        messages.warning(request, "No seleccionaste ninguna remisión.")
        return redirect('remisiones_por_facturar')

    # === CORRECCIÓN AQUÍ ===
    # En lugar de 'facturada=False', usamos 'facturas__isnull=True'
    # Esto busca remisiones que no tengan ninguna factura asociada.
    remisiones = Remision.objects.filter(id__in=remisiones_ids, facturas__isnull=True)
    
    if not remisiones.exists():
        messages.error(request, "Las remisiones seleccionadas no son válidas o ya están facturadas.")
        return redirect('remisiones_por_facturar')

    # Obtener cliente de la primera remisión
    primera_remision = remisiones.first()
    cliente = primera_remision.cliente
    
    if not cliente:
        messages.error(request, "Error: La remisión no tiene un cliente asignado.")
        return redirect('remisiones_por_facturar')

    # Validar que todas sean del mismo cliente
    for r in remisiones:
        if r.cliente_id != cliente.pk:  # Usamos IDs para comparar más seguro
            messages.error(request, "Todas las remisiones deben ser del mismo cliente.")
            return redirect('remisiones_por_facturar')

    # --- CONFIGURACIÓN DE DATOS FISCALES Y RECEPTOR ---
    try:
        receptor = cliente.datos_fiscales
    except:
        receptor = None

    # 1. Preparar datos iniciales para el formulario del Modal
    initial_data = {}
    
    # Buscamos si el cliente tiene un LUGAR asociado con datos
    lugar_asociado = Lugar.objects.filter(
        remisiones_destino__cliente=cliente
    ).exclude(rfc__isnull=True).exclude(rfc__exact='').first()

    # Si hay lugar, lo usamos para pre-llenar
    if lugar_asociado:
        initial_data = {
            'rfc': lugar_asociado.rfc,
            'razon_social': lugar_asociado.razon_social or cliente.nombre,
            'codigo_postal': lugar_asociado.codigo_postal,
            'regimen_fiscal': lugar_asociado.regimen_fiscal,
            'uso_cfdi': lugar_asociado.uso_cfdi or 'G03',
            'calle': lugar_asociado.calle,
            'numero_exterior': lugar_asociado.numero_exterior,
            'numero_interior': lugar_asociado.numero_interior,
            'colonia': lugar_asociado.colonia,
            'municipio': lugar_asociado.municipio,
            'estado': lugar_asociado.estado
        }

    # Si ya existe configuración fiscal guardada, esa tiene prioridad
    if receptor:
        fiscal_instance = receptor
        if not fiscal_instance.codigo_postal and lugar_asociado:
             initial_data['codigo_postal'] = lugar_asociado.codigo_postal
    else:
        fiscal_instance = DatosFiscales(es_emisor=False, cliente_interno=cliente)

    form_fiscal = DatosFiscalesClienteForm(instance=fiscal_instance, initial=initial_data)

    # --- VALIDACIÓN DE INTEGRIDAD ---
    faltan_datos = True
    if receptor and receptor.rfc and receptor.codigo_postal and receptor.direccion:
        faltan_datos = False

    # --- PREPARAR FORMULARIO DE FACTURA ---
    initial_factura = {
        'moneda': 'MXN',
        'tipo_cambio': 1.0,
        'uso_cfdi': receptor.uso_cfdi if receptor else 'G03',
        'metodo_pago': 'PPD', 
        'forma_pago': '99'
    }
    form = NuevaFacturaLibreForm(initial=initial_factura)
    
    traslados_disponibles = CatalogoImpuesto.objects.filter(activo=True, categoria='Traslado')
    retenciones_disponibles = CatalogoImpuesto.objects.filter(activo=True, categoria='Retencion')

    return render(request, 'facturacion/prefactura.html', {
        'remisiones': remisiones,
        'emisor': get_emisor_fiscal(),
        'receptor': receptor,
        'cliente': cliente,
        'form': form,
        'form_fiscal': form_fiscal,
        'impuestos_traslado': traslados_disponibles,
        'impuestos_retencion': retenciones_disponibles,
        'faltan_datos_fiscales': faltan_datos,
    })

@login_required
@transaction.atomic
@permission_required('facturacion.add_factura', raise_exception=True)
def generar_factura_accion(request):
    if request.method == 'POST':
        form = GenerarFacturaForm(request.POST)
        
        if form.is_valid():
            # 1. CREAMOS EL PUNTO DE GUARDADO (SAVEPOINT)
            sid = transaction.savepoint()

            try:
                # Recuperar Cliente y Emisor
                cliente_id = request.POST.get('receptor')
                if not cliente_id:
                    messages.error(request, "Error: No se identificó al cliente.")
                    return redirect('remisiones_por_facturar')

                cliente = get_object_or_404(Cliente, pk=cliente_id)
                
                # Buscamos datos fiscales
                receptor_fiscal = getattr(cliente, 'datos_fiscales', None)
                if not receptor_fiscal:
                    receptor_fiscal = DatosFiscales.objects.filter(rfc=cliente.rfc, es_emisor=False).first()
                
                if not receptor_fiscal:
                    messages.error(request, f"El cliente {cliente.nombre} no tiene datos fiscales configurados.")
                    return redirect('remisiones_por_facturar')

                emisor = get_emisor_fiscal()
                if not emisor:
                    messages.error(request, "Falta configurar el Emisor.")
                    return redirect('configurar_emisor')

                # 2. Crear Cabecera de Factura
                factura = form.save(commit=False)
                factura.emisor = emisor
                factura.receptor = receptor_fiscal
                factura.cliente = cliente
                
                # Serie y Folio
                serie_id = request.POST.get('serie_personalizada')
                serie_actual = "F" 
                if serie_id:
                    try:
                        serie_obj = SeriePersonalizada.objects.get(id=serie_id)
                        serie_actual = serie_obj.nombre
                    except SeriePersonalizada.DoesNotExist: pass
                
                consecutivo = Factura.objects.filter(serie=serie_actual).count() + 1
                factura.serie = serie_actual
                factura.folio = f"{serie_actual}-{consecutivo}"
                factura.fecha_emision = timezone.now()
                factura.estado = 'pendiente'
                factura.subtotal = 0
                factura.monto_total = 0
                factura.save()

                # 3. Procesar Conceptos
                remision_ids = request.POST.getlist('remision_id[]')
                claves_sat = request.POST.getlist('clave_prod_serv[]')
                claves_unidad = request.POST.getlist('clave_unidad[]')
                cantidades = request.POST.getlist('cantidad[]')
                descripciones = request.POST.getlist('descripcion[]')
                precios = request.POST.getlist('valor_unitario[]')
                objetos_imp = request.POST.getlist('objeto_impuesto[]') 

                subtotal_acum = Decimal(0)
                iva_acum = Decimal(0)
                ret_acum = Decimal(0)
                aplicar_retencion = form.cleaned_data.get('aplicar_retencion', False)

                for i, r_id in enumerate(remision_ids):
                    if i >= len(precios) or not precios[i]: continue

                    # Conversión a Decimal
                    cantidad = Decimal(str(cantidades[i]))
                    precio = Decimal(str(precios[i]))
                    importe = cantidad * precio
                    
                    clave_sat_val = claves_sat[i]
                    clave_unidad_val = claves_unidad[i]
                    desc_val = descripciones[i]
                    obj_imp_val = objetos_imp[i] if i < len(objetos_imp) else '02'

                    # Cálculo Impuestos
                    iva_concepto = Decimal(0)
                    ret_concepto = Decimal(0)
                    
                    if obj_imp_val == '02':
                        iva_concepto = importe * Decimal("0.16")
                        if aplicar_retencion:
                            ret_concepto = importe * Decimal("0.06")

                    # Crear Concepto
                    ConceptoFactura.objects.create(
                        factura=factura,
                        clave_prod_serv=clave_sat_val,
                        cantidad=cantidad,
                        clave_unidad=clave_unidad_val,
                        unidad="Unidad",
                        descripcion=desc_val,
                        valor_unitario=precio,
                        importe=importe,
                        objeto_impuesto=obj_imp_val,
                        iva_importe=iva_concepto,
                        iva_ret_importe=ret_concepto
                    )

                    # Vincular la remisión
                    try:
                        Remision.objects.filter(id=r_id).update(factura=factura)
                    except: pass

                    subtotal_acum += importe
                    iva_acum += iva_concepto
                    ret_acum += ret_concepto

                # 4. Totales
                factura.subtotal = subtotal_acum
                factura.impuestos_trasladados = iva_acum
                factura.impuestos_retenidos = ret_acum
                factura.monto_total = subtotal_acum + iva_acum - ret_acum
                factura.save()

                # 5. Timbrar
                print(f"📡 Timbrando prefactura {factura.folio}...")
                resultado = timbrar_factura_api(factura)

                if resultado['success']:
                    # A) ÉXITO
                    data = resultado['data']
                    factura.folio_fiscal = data.get('uuid')
                    factura.id_fiscalapi = data.get('id')
                    factura.estado = 'timbrado'
                    factura.fecha_timbrado = timezone.now()
                    
                    if data.get('xml'):
                        try:
                            import base64
                            from django.core.files.base import ContentFile
                            xml_content = base64.b64decode(data['xml'])
                            factura.archivo_xml.save(f"{factura.folio_fiscal}.xml", ContentFile(xml_content), save=False)
                        except: pass

                    factura.save()
                    
                    # CONFIRMAR CAMBIOS (Incluye remisiones vinculadas)
                    transaction.savepoint_commit(sid)
                    
                    messages.success(request, f"✅ Factura {factura.folio} TIMBRADA correctamente.")
                    return redirect('detalle_factura_cliente', pk=factura.pk)
                else:
                    # B) ERROR: ROLLBACK
                    err = resultado.get('error', 'Error desconocido')
                    transaction.savepoint_rollback(sid)
                    
                    messages.error(request, f"❌ Error SAT: {err}. La factura NO se generó y las remisiones siguen pendientes.")
                    return redirect('remisiones_por_facturar')

            except Exception as e:
                # C) EXCEPCIÓN: ROLLBACK
                transaction.savepoint_rollback(sid)
                import traceback
                print(traceback.format_exc())
                messages.error(request, f"Error interno: {str(e)}")
                return redirect('remisiones_por_facturar')
        else:
            messages.error(request, "Datos inválidos en el formulario.")
            return redirect('remisiones_por_facturar')
            
    return redirect('dashboard_facturacion')

@login_required
@permission_required('facturacion.change_datosfiscales', raise_exception=True)
def configurar_cliente_fiscal(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    try:
        instance = cliente.datos_fiscales
    except:
        instance = DatosFiscales(es_emisor=False, cliente_interno=cliente)

    if request.method == 'POST':
        form = DatosFiscalesClienteForm(request.POST, instance=instance)
        if form.is_valid():
            datos = form.save(commit=False)
            datos.es_emisor = False
            datos.cliente_interno = cliente
            
            # Construcción de dirección
            c = form.cleaned_data.get('calle') or ''
            n_ext = form.cleaned_data.get('numero_exterior') or ''
            n_int = form.cleaned_data.get('numero_interior') or ''
            col = form.cleaned_data.get('colonia') or ''
            mun = form.cleaned_data.get('municipio') or ''
            est = form.cleaned_data.get('estado') or ''
            cp = form.cleaned_data.get('codigo_postal') or ''

            partes = [p for p in [c, n_ext, n_int, col, cp, mun, est, 'MÉXICO'] if p]
            datos.direccion = ", ".join(partes).upper()
            
            datos.save()
            
            # Sincronizar Lugares (Opcional)
            Lugar.objects.filter(remisiones_destino__cliente=cliente).update(
                rfc=datos.rfc, razon_social=datos.razon_social, codigo_postal=datos.codigo_postal,
                regimen_fiscal=datos.regimen_fiscal, uso_cfdi=datos.uso_cfdi,
                calle=c, numero_exterior=n_ext, numero_interior=n_int, colonia=col, municipio=mun, estado=est
            )
            
            # --- RESPUESTA AJAX PARA NO SACAR AL USUARIO ---
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Datos fiscales guardados correctamente.',
                    'data': {
                        'rfc': datos.rfc,
                        'razon': datos.razon_social,
                        'direccion': datos.direccion,
                        'cp': datos.codigo_postal,
                        'regimen': datos.regimen_fiscal
                    }
                })
            # -----------------------------------------------

            messages.success(request, "Datos fiscales actualizados.")
            return redirect('remisiones_por_facturar') # Fallback si no es JS
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    return render(request, 'facturacion/configurar_cliente.html', {'cliente': cliente})

from ternium.models import DetalleRemision # Asegúrate de importar esto arriba

@login_required
@permission_required('facturacion.add_factura', raise_exception=True)
def remisiones_por_facturar(request):
    # =========================================================================
    # 1. AUTO-CORRECCIÓN (FIX: Llenar Cliente en Remisión desde el Destino)
    # =========================================================================
    # Buscamos remisiones sin cliente pero con destino, y les asignamos el cliente del destino.
    # Usamos update() masivo si es posible, o iteramos si necesitamos lógica python.
    remisiones_fix = Remision.objects.filter(
        status__in=['TERMINADO', 'AUDITADO'],
        cliente__isnull=True,
        destino__isnull=False
    ).select_related('destino')

    count_fixed = 0
    for r in remisiones_fix:
        # Si el lugar destino tiene un cliente asignado
        if r.destino and hasattr(r.destino, 'cliente') and r.destino.cliente:
            r.cliente = r.destino.cliente
            r.save(update_fields=['cliente'])
            count_fixed += 1
            
    if count_fixed > 0:
        print(f"🔧 SISTEMA: Se corrigieron automáticamente {count_fixed} remisiones asignándoles el cliente de su destino.")
    # =========================================================================

    # 2. QUERY PRINCIPAL
    # Quitamos 'cliente' de select_related para evitar el error anterior,
    # pero mantenemos destino y origen para optimizar.
    queryset = Remision.objects.filter(
        status__in=['TERMINADO', 'AUDITADO']
    ).exclude(
        facturas__estado='timbrado'
    ).exclude(
        destino__nombre__icontains="PATIO"
    ).select_related(
        'destino', 'origen'
    ).order_by('-fecha')

    # 3. FILTROS
    q_cliente = request.GET.get('q_cliente')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if q_cliente:
        # Filtramos por el nombre del cliente de la remisión
        queryset = queryset.filter(cliente__nombre__icontains=q_cliente)
    
    if fecha_inicio and fecha_fin:
        queryset = queryset.filter(fecha__range=[fecha_inicio, fecha_fin])

    # 4. EXPORTAR EXCEL
    if request.GET.get('exportar') == 'excel':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="remisiones_pendientes.csv"'
        response.write(u'\ufeff'.encode('utf8'))
        
        writer = csv.writer(response)
        writer.writerow(['Folio', 'Fecha', 'Cliente', 'Origen', 'Destino', 'Material', 'Peso Neto (kg)'])

        for r in queryset:
            # Intentamos obtener material del primer detalle
            material_nombre = "N/A"
            detalle = r.detalles.first()
            if detalle and detalle.material:
                material_nombre = detalle.material.nombre
                
            writer.writerow([
                r.remision,
                r.fecha.strftime('%d/%m/%Y'),
                r.cliente.nombre if r.cliente else "S/C",
                r.origen.nombre if r.origen else "S/O",
                r.destino.nombre if r.destino else "S/D",
                material_nombre,
                r.total_peso_dlv or 0 
            ])
        return response

    # 5. PAGINACIÓN Y CONTEXTO
    total_pendientes = queryset.count()

    # Resumen rápido por Cliente
    resumen_clientes = queryset.values('cliente__nombre').annotate(
        conteo=Count('id')
    ).order_by('-conteo')

    paginator = Paginator(queryset, 50) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # === CORRECCIÓN DEL COMBO (Aquí estaba el error FieldError) ===
    # Usamos 'remision__' porque el error nos dijo que 'remision' sí es una opción válida en Cliente.
    clientes_combo = Cliente.objects.filter(
        remision__status__in=['TERMINADO', 'AUDITADO'],
        remision__facturas__isnull=True
    ).distinct().order_by('nombre')

    context = {
        'remisiones': page_obj,
        'total_pendientes': total_pendientes,
        'resumen_clientes': resumen_clientes,
        'clientes_combo': clientes_combo,
        'filtro_cliente': q_cliente,
        'filtro_inicio': fecha_inicio,
        'filtro_fin': fecha_fin,
    }
    
    return render(request, 'facturacion/por_facturar.html', context)
@login_required
@permission_required('facturacion.view_factura', raise_exception=True)
def detalle_factura(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    return render(request, 'facturacion/detalle.html', {'factura': factura})

from .models import Factura, DatosFiscales
from ternium.models import Lugar # <--- IMPORTANTE: Importar el modelo Lugar


@login_required
@permission_required('facturacion.view_factura', raise_exception=True)
def generar_pdf(request, pk):
    factura = get_object_or_404(Factura, pk=pk)

    # =========================================================
    # 1. AUTORRELLENADO DE DIRECCIÓN FISCAL (RECEPTOR)
    # =========================================================
    lugar_fuente = None
    
    # ESTRATEGIA A: Buscar en la remisión vinculada (Prioridad Alta)
    remision = factura.remisiones.first()
    if remision and remision.destino:
        lugar_fuente = remision.destino
    
    # ESTRATEGIA B: Historial del Cliente (Prioridad Media)
    # CORRECCIÓN: Obtenemos el cliente desde el receptor fiscal de manera segura
    cliente_real = None
    if factura.receptor and hasattr(factura.receptor, 'cliente_interno'):
        cliente_real = factura.receptor.cliente_interno
    
    # Si no obtuvimos cliente del receptor, intentamos desde la remisión (si existe)
    if not cliente_real and remision:
        cliente_real = remision.cliente

    # Si encontramos cliente y aún no tenemos lugar fuente, buscamos en su historial
    if not lugar_fuente and cliente_real:
        lugar_fuente = Lugar.objects.filter(
            remisiones_destino__cliente=cliente_real
        ).exclude(calle__isnull=True).exclude(calle__exact='').order_by('-id').first()

    # Si encontramos un lugar válido (A o B), construimos la dirección
    if lugar_fuente:
        partes = [
            lugar_fuente.calle,
            f"No. {lugar_fuente.numero_exterior}" if lugar_fuente.numero_exterior else None,
            f"Int. {lugar_fuente.numero_interior}" if lugar_fuente.numero_interior else None,
            f"Col. {lugar_fuente.colonia}" if lugar_fuente.colonia else None,
            f"CP {lugar_fuente.codigo_postal}" if lugar_fuente.codigo_postal else None,
            lugar_fuente.municipio,
            lugar_fuente.estado,
            lugar_fuente.pais
        ]
        direccion_completa = ", ".join(filter(None, partes)).upper()

        if direccion_completa and factura.receptor:
            if factura.receptor.direccion != direccion_completa:
                factura.receptor.direccion = direccion_completa
                
                if lugar_fuente.codigo_postal and not factura.receptor.codigo_postal:
                    factura.receptor.codigo_postal = lugar_fuente.codigo_postal
                
                factura.receptor.save()

    # =========================================================
    # 2. LÓGICA DE IMPORTE CON LETRA
    # =========================================================
    try:
        total = factura.monto_total
        enteros = int(total)
        centavos = int(round((total - enteros) * 100))
        texto_enteros = num2words(enteros, lang='es').upper()
        factura.monto_letra_calculado = f"{texto_enteros} PESOS {centavos:02d}/100 M.N."
    except Exception:
        factura.monto_letra_calculado = "(ERROR AL GENERAR LETRA)"

    # =========================================================
    # 3. LÓGICA DE XML, QR Y SELLOS
    # =========================================================
    if factura.archivo_xml and (factura.estado == 'timbrado' or factura.folio_fiscal):
        try:
            with factura.archivo_xml.open('rb') as xml_file:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4', 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
                tfd = root.find('.//tfd:TimbreFiscalDigital', ns)
                
                if tfd is not None:
                    factura.sello_sat = tfd.get('SelloSAT')
                    factura.no_certificado_sat = tfd.get('NoCertificadoSAT')
                    factura.fecha_timbrado = tfd.get('FechaTimbrado')
                    uuid = tfd.get('UUID')
                    rfc_prov = tfd.get('RfcProvCertif')
                    sello_cfd = root.get('Sello')
                    factura.sello_digital = sello_cfd
                    
                    factura.cadena_original = f"||1.1|{uuid}|{factura.fecha_timbrado}|{rfc_prov}|{sello_cfd}|{factura.no_certificado_sat}||"
                    
                    total_xml = root.get('Total')
                    rfc_emisor = root.find('cfdi:Emisor', ns).get('Rfc')
                    rfc_receptor = root.find('cfdi:Receptor', ns).get('Rfc')
                    sello_last8 = sello_cfd[-8:] if sello_cfd else ""
                    
                    qr_content = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={uuid}&re={rfc_emisor}&rr={rfc_receptor}&tt={total_xml}&fe={sello_last8}"
                    
                    qr_img = qrcode.make(qr_content)
                    buffer = BytesIO()
                    qr_img.save(buffer, format="PNG")
                    img_str = base64.b64encode(buffer.getvalue()).decode()
                    factura.qr_url = f"data:image/png;base64,{img_str}"
        except Exception:
            pass

    # =========================================================
    # 4. RENDERIZADO
    # =========================================================
    emisor_default = DatosFiscales.objects.filter(es_emisor=True).first()

    context = {
        'factura': factura,
        'emisor_default': emisor_default
    }

    html_string = render_to_string('facturacion/pdf_factura.html', context)
    
    if HTML:
        pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="F-{factura.folio}.pdf"'
        return response
    
    return HttpResponse("Error: Librería WeasyPrint no instalada", status=500)
@login_required
@transaction.atomic
@permission_required('facturacion.add_factura', raise_exception=True)
def crear_factura_nueva(request):
    
    traslados_disponibles = CatalogoImpuesto.objects.filter(activo=True, categoria='Traslado')
    retenciones_disponibles = CatalogoImpuesto.objects.filter(activo=True, categoria='Retencion')

    if request.method == 'POST':
        form = NuevaFacturaLibreForm(request.POST)
        
        if form.is_valid():
            sid = transaction.savepoint()
            
            try:
                emisor = get_emisor_fiscal()
                if not emisor:
                    messages.error(request, "Configura tu emisor primero.")
                    return redirect('configurar_emisor')

                # --- NUEVA LÓGICA DE RECEPTOR ---
                lugar_seleccionado = form.cleaned_data['lugar_receptor']
                
                # Buscamos si ya existen DatosFiscales para ese RFC
                receptor_fiscal = DatosFiscales.objects.filter(
                    rfc=lugar_seleccionado.rfc, 
                    es_emisor=False
                ).first()

                # Si no existe, lo creamos usando los datos del Lugar
                if not receptor_fiscal:
                    # Construir dirección
                    partes = []
                    if lugar_seleccionado.calle: partes.append(lugar_seleccionado.calle)
                    if lugar_seleccionado.numero_exterior: partes.append(f"No. {lugar_seleccionado.numero_exterior}")
                    if lugar_seleccionado.colonia: partes.append(f"Col. {lugar_seleccionado.colonia}")
                    if lugar_seleccionado.municipio: partes.append(lugar_seleccionado.municipio)
                    if lugar_seleccionado.estado: partes.append(lugar_seleccionado.estado)
                    direccion_completa = ", ".join(partes).upper()

                    receptor_fiscal = DatosFiscales.objects.create(
                        es_emisor=False,
                        rfc=lugar_seleccionado.rfc,
                        razon_social=lugar_seleccionado.razon_social or lugar_seleccionado.nombre,
                        regimen_fiscal=lugar_seleccionado.regimen_fiscal or '601',
                        codigo_postal=lugar_seleccionado.codigo_postal,
                        uso_cfdi=lugar_seleccionado.uso_cfdi or 'G03',
                        direccion=direccion_completa
                        # Nota: Si Lugar tiene relación con Cliente, podrías asignarlo aquí también
                        # cliente_interno=lugar_seleccionado.cliente (si existe esa relación directa)
                    )
                # --------------------------------

                factura = form.save(commit=False)
                factura.emisor = emisor
                factura.receptor = receptor_fiscal # Asignamos el receptor procesado
                
                # Serie y Folio
                serie_id = request.POST.get('serie_personalizada')
                serie_actual = "F"
                if serie_id:
                    try: 
                        serie_actual = SeriePersonalizada.objects.get(id=serie_id).nombre
                    except: pass
                
                consecutivo = Factura.objects.filter(serie=serie_actual).count() + 1
                factura.serie = serie_actual
                factura.folio = f"{serie_actual}-{consecutivo}"
                factura.fecha_emision = timezone.now()
                factura.estado = 'pendiente'
                factura.save()

                # ... (El resto del código de procesar conceptos sigue EXACTAMENTE IGUAL) ...
                # 2. Procesar Conceptos
                cantidades = request.POST.getlist('cantidad[]')
                unidades = request.POST.getlist('clave_unidad[]')
                claves_sat = request.POST.getlist('clave_prod_serv[]')
                descripciones = request.POST.getlist('descripcion[]')
                valores = request.POST.getlist('valor_unitario[]')
                
                impuestos_tras_ids = request.POST.getlist('impuesto_traslado[]')
                impuestos_ret_ids = request.POST.getlist('impuesto_retencion[]')

                subtotal_gral = 0
                impuestos_gral = 0
                retenciones_gral = 0

                MAPA_IMPUESTOS = {'ISR': '001', 'IVA': '002', 'IEPS': '003'}

                for i in range(len(descripciones)):
                    if not descripciones[i] or not cantidades[i]: continue
                    
                    cant = Decimal(str(cantidades[i]))
                    val = Decimal(str(valores[i]))
                    importe = cant * val
                    
                    monto_traslado = Decimal(0)
                    clave_traslado = "002"
                    tasa_traslado = Decimal(0)

                    traslado_id = impuestos_tras_ids[i] if i < len(impuestos_tras_ids) else None
                    if traslado_id:
                        try:
                            imp_obj = CatalogoImpuesto.objects.get(id=traslado_id)
                            clave_traslado = MAPA_IMPUESTOS.get(imp_obj.impuesto, '002')
                            if imp_obj.tipo_factor == 'Tasa':
                                tasa_traslado = Decimal(str(imp_obj.tasa_o_cuota))
                                monto_traslado = importe * tasa_traslado
                        except Exception: pass

                    monto_retencion = Decimal(0)
                    clave_retencion = "002"
                    tasa_retencion = Decimal(0)

                    ret_id = impuestos_ret_ids[i] if i < len(impuestos_ret_ids) else None
                    if ret_id:
                        try:
                            imp_obj = CatalogoImpuesto.objects.get(id=ret_id)
                            clave_retencion = MAPA_IMPUESTOS.get(imp_obj.impuesto, '002')
                            if imp_obj.tipo_factor == 'Tasa':
                                tasa_retencion = Decimal(str(imp_obj.tasa_o_cuota))
                                monto_retencion = importe * tasa_retencion
                        except Exception: pass

                    ConceptoFactura.objects.create(
                        factura=factura,
                        clave_prod_serv=claves_sat[i] or "01010101",
                        cantidad=cant,
                        clave_unidad=unidades[i] or "H87",
                        descripcion=descripciones[i],
                        valor_unitario=val,
                        importe=importe,
                        objeto_impuesto='02' if (traslado_id or ret_id) else '01',
                        iva_importe=monto_traslado,       
                        iva_ret_importe=monto_retencion,
                        traslado_impuesto_clave=clave_traslado,
                        traslado_tasa=tasa_traslado,
                        retencion_impuesto_clave=clave_retencion,
                        retencion_tasa=tasa_retencion
                    )
                    
                    subtotal_gral += importe
                    impuestos_gral += monto_traslado
                    retenciones_gral += monto_retencion

                factura.subtotal = subtotal_gral
                factura.impuestos_trasladados = impuestos_gral
                factura.impuestos_retenidos = retenciones_gral
                factura.monto_total = subtotal_gral + impuestos_gral - retenciones_gral
                factura.save()

                resultado = timbrar_factura_api(factura)
                
                if resultado['success']:
                    data = resultado['data']
                    factura.folio_fiscal = data.get('uuid')
                    factura.id_fiscalapi = data.get('id')
                    factura.estado = 'timbrado'
                    factura.fecha_timbrado = timezone.now()
                    
                    if data.get('xml'):
                        try:
                            import base64
                            from django.core.files.base import ContentFile
                            xml_content = base64.b64decode(data['xml'])
                            factura.archivo_xml.save(f"{factura.folio_fiscal}.xml", ContentFile(xml_content), save=False)
                        except: pass
                    
                    factura.save()
                    transaction.savepoint_commit(sid)
                    messages.success(request, f"Factura {factura.folio} Timbrada Exitosamente.")
                    return redirect('detalle_factura_cliente', pk=factura.pk)
                else:
                    error_msg = resultado.get('error')
                    transaction.savepoint_rollback(sid)
                    messages.error(request, f"NO SE GUARDÓ LA FACTURA. Error PAC: {error_msg}")

            except Exception as e:
                transaction.savepoint_rollback(sid)
                import traceback
                traceback.print_exc()
                messages.error(request, f"Error interno: {e}")
    else:
        form = NuevaFacturaLibreForm()

    return render(request, 'facturacion/crear_factura.html', {
        'form': form,
        'impuestos_traslado': traslados_disponibles,
        'impuestos_retencion': retenciones_disponibles
    })

@login_required
@transaction.atomic
@permission_required('facturacion.add_complementopago', raise_exception=True)
def registrar_pago(request, factura_id):
    """
    Registra un pago INDIVIDUAL (botón en dashboard) y lo timbra.
    """
    factura = get_object_or_404(Factura, pk=factura_id)
    
    if factura.metodo_pago != 'PPD':
        messages.warning(request, "Solo se pueden agregar complementos de pago a facturas PPD.")
        return redirect('detalle_factura_cliente', pk=factura.pk)

    total_pagado = factura.pagos_recibidos.aggregate(suma=Sum('importe_pagado'))['suma'] or 0
    saldo_actual = factura.monto_total - total_pagado
    
    if saldo_actual <= 0:
        messages.warning(request, "Esta factura ya está pagada totalmente.")
        return redirect('detalle_factura_cliente', pk=factura.pk)

    if request.method == 'POST':
        form = PagoForm(request.POST, factura_obj=factura)
        
        if form.is_valid():
            datos_pago = form.cleaned_data
            monto_recibido = datos_pago['monto_total']

            try:
                ultimo_folio = ComplementoPago.objects.order_by('-folio').first()
                nuevo_folio = (ultimo_folio.folio + 1) if ultimo_folio else 1
                
                complemento = form.save(commit=False)
                complemento.usuario = request.user
                complemento.receptor = factura.receptor
                complemento.serie = 'CP'
                complemento.folio = nuevo_folio
                complemento.timbrado = False
                complemento.save()

                saldo_ant_dec = Decimal(str(saldo_actual)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                imp_pagado_dec = Decimal(str(monto_recibido)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                
                saldo_ins_calc = saldo_ant_dec - imp_pagado_dec
                if saldo_ins_calc < 0: saldo_ins_calc = Decimal('0.00')

                num_parcialidad = factura.pagos_recibidos.count() + 1

                PagoDoctoRelacionado.objects.create(
                    complemento=complemento,
                    factura=factura,
                    numero_parcialidad=num_parcialidad,
                    saldo_anterior=saldo_ant_dec,
                    importe_pagado=imp_pagado_dec,
                    saldo_insoluto=saldo_ins_calc
                )

                if saldo_ins_calc <= 0:
                    factura.estado = 'pagada'
                    factura.save()

                # --- TIMBRADO EN EL SAT ---
                resultado = timbrar_pago_api(complemento)
                
                if resultado['success']:
                    complemento.timbrado = True
                    complemento.uuid = resultado['data']['uuid']
                    complemento.fecha_timbrado = timezone.now()
                    
                    xml_b64 = resultado['data'].get('xml')
                    if xml_b64:
                        try:
                            xml_content = base64.b64decode(xml_b64)
                            filename = f"Pago_{complemento.serie}{complemento.folio}.xml"
                            complemento.archivo_xml.save(filename, ContentFile(xml_content), save=False)
                        except Exception as e:
                            print(f"Error guardando XML: {e}")
                    
                    complemento.save()
                    messages.success(request, f"Pago registrado y TIMBRADO correctamente (CP-{nuevo_folio}). UUID: {complemento.uuid}")
                else:
                    messages.warning(request, f"Pago guardado localmente, pero NO TIMBRADO. Error SAT: {resultado.get('error')}")

                return redirect('detalle_factura_cliente', pk=factura.pk)

            except Exception as e:
                messages.error(request, f"Error al guardar el pago: {e}")

    else:
        form = PagoForm()

    return render(request, 'facturacion/registrar_pago.html', {
        'factura': factura,
        'form': form,
        'saldo_actual': saldo_actual
    })
    
@login_required
@permission_required('facturacion.add_complementopago', raise_exception=True)
def nuevo_complemento_pago(request):
    """
    Genera un Complemento de Pago (REP) con protección ATÓMICA.
    Si el SAT rechaza, NO se guarda nada en la base de datos.
    """
    facturas_pendientes = []
    cliente_id = request.GET.get('cliente_id')
    
    if cliente_id:
        facturas_pendientes = Factura.objects.filter(
            receptor_id=cliente_id,
            metodo_pago='PPD',
            estado__in=['timbrado', 'pendiente']
        ).exclude(estado='pagada').order_by('fecha_emision')

        for f in facturas_pendientes:
            pagado = f.pagos_recibidos.aggregate(suma=Sum('importe_pagado'))['suma'] or 0
            f.saldo_pendiente = f.monto_total - pagado

    if request.method == 'POST':
        form = ComplementoPagoCabeceraForm(request.POST)
        if form.is_valid():
            # INICIO DE TRANSACCIÓN ATÓMICA
            # Nada se confirma en BD hasta que lleguemos al commit final
            with transaction.atomic():
                sid = transaction.savepoint() # Marcamos un punto de retorno
                try:
                    data = form.cleaned_data
                    receptor = data['cliente']
                    
                    ultimo_folio = ComplementoPago.objects.order_by('-folio').first()
                    nuevo_folio = (ultimo_folio.folio + 1) if ultimo_folio else 1
                    
                    complemento = form.save(commit=False)
                    complemento.usuario = request.user
                    complemento.receptor = receptor
                    complemento.folio = nuevo_folio
                    complemento.serie = 'CP'
                    complemento.timbrado = False
                    complemento.save() # Se guarda temporalmente

                    facturas_ids = request.POST.getlist('facturas_seleccionadas')
                    total_aplicado = Decimal('0.00')

                    # 1. Crear relaciones
                    for f_id in facturas_ids:
                        monto_a_pagar = Decimal(request.POST.get(f'pago_factura_{f_id}', '0'))
                        
                        if monto_a_pagar > 0:
                            factura = Factura.objects.get(id=f_id)
                            
                            historial_pagos = factura.pagos_recibidos.aggregate(suma=Sum('importe_pagado'))['suma'] or Decimal('0')
                            saldo_ant = factura.monto_total - historial_pagos
                            saldo_ins = saldo_ant - monto_a_pagar
                            
                            parcialidad = factura.pagos_recibidos.count() + 1
                            
                            PagoDoctoRelacionado.objects.create(
                                complemento=complemento,
                                factura=factura,
                                numero_parcialidad=parcialidad,
                                saldo_anterior=saldo_ant,
                                importe_pagado=monto_a_pagar,
                                saldo_insoluto=saldo_ins
                            )
                            
                            total_aplicado += monto_a_pagar
                            
                            # Actualizar estado de factura TEMPORALMENTE
                            if saldo_ins <= 0.01:
                                factura.estado = 'pagada'
                                factura.save()

                    if total_aplicado > complemento.monto_total:
                        raise Exception("El total aplicado supera el monto recibido.")
                    
                    # 2. INTENTO DE TIMBRADO
                    # Aquí es donde puede fallar
                    resultado = timbrar_pago_api(complemento)
                    
                    if resultado['success']:
                        # ¡ÉXITO! Confirmamos los cambios en la BD
                        complemento.timbrado = True
                        complemento.uuid = resultado['data']['uuid']
                        complemento.fecha_timbrado = timezone.now()
                        
                        xml_b64 = resultado['data'].get('xml')
                        if xml_b64:
                            try:
                                xml_content = base64.b64decode(xml_b64)
                                filename = f"Pago_{complemento.serie}{complemento.folio}.xml"
                                complemento.archivo_xml.save(filename, ContentFile(xml_content), save=False)
                            except: pass
                        
                        complemento.save()
                        transaction.savepoint_commit(sid) # <--- PUNTO DE NO RETORNO (COMMIT)
                        
                        messages.success(request, f"Complemento CP-{nuevo_folio} TIMBRADO correctamente.")
                        return redirect('dashboard_facturacion')
                    
                    else:
                        # FALLÓ EL TIMBRADO -> BORRAR TODO (ROLLBACK)
                        error_msg = resultado.get('error')
                        transaction.savepoint_rollback(sid) # <--- DESHACER TODO
                        
                        messages.error(request, f"NO SE GUARDÓ NADA. Error SAT: {error_msg}")
                        # No redirigimos para que el usuario pueda corregir el formulario
                        # aunque perderá los datos de los inputs manuales por recarga

                except Exception as e:
                    transaction.savepoint_rollback(sid) # <--- DESHACER SI HAY EXCEPCIÓN
                    messages.error(request, f"Error interno (Rollback): {str(e)}")

    else:
        form = ComplementoPagoCabeceraForm()
        if cliente_id:
            form.fields['cliente'].initial = cliente_id

    return render(request, 'facturacion/nuevo_complemento.html', {
        'form': form,
        'facturas': facturas_pendientes,
        'cliente_seleccionado': int(cliente_id) if cliente_id else None
    })
    
    
def nueva_cuenta_por_pagar(request):
    # Asumiendo que usas DatosFiscales también para proveedores
    proveedores = DatosFiscales.objects.all() # Filtra si tienes un campo 'es_proveedor'
    return render(request, 'facturacion/nueva_cuenta_por_pagar.html', {
        'proveedores': proveedores
    })
    
@login_required
@permission_required('facturacion.change_factura', raise_exception=True)
def cancelar_factura_view(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    
    if request.method == 'POST':
        motivo = request.POST.get('motivo', '02')
        # Capturamos el campo del modal (sustitucion)
        sustitucion = request.POST.get('sustitucion', None)
        
        if not factura.folio_fiscal and not factura.id_fiscalapi:
            factura.estado = 'cancelada'
            factura.save()
            messages.success(request, "Borrador cancelado localmente.")
        else:
            # Pasamos la factura y el motivo
            resultado = cancelar_cfdi_api(factura, motivo=motivo, sustitucion=sustitucion)
            
            if resultado['success']:
                factura.estado = 'cancelada'
                factura.save()
                messages.success(request, f"Factura cancelada correctamente en el SAT.")
            else:
                # Si la API falla, mostramos el error exacto
                messages.error(request, f"Error SAT: {resultado.get('error')}")
                
    return redirect('detalle_factura_cliente', pk=pk)
# Vista para cancelar Pagos (REP)
@login_required
def cancelar_pago_view(request, pk):
    pago = get_object_or_404(ComplementoPago, pk=pk)
    
    if request.method == 'POST':
        if not pago.uuid:
            pago.delete() # Si no es timbrado, lo borramos
            messages.success(request, "Pago eliminado.")
        else:
            res = cancelar_cfdi_api(pago.uuid, motivo="02")
            if res['success']:
                # Revertir saldos de facturas
                for doc in pago.documentos_relacionados.all():
                    factura = doc.factura
                    if factura.estado == 'pagada':
                        factura.estado = 'timbrado' # Regresa a estar pendiente de pago
                    factura.save()
                
                # Marcar pago como cancelado (puedes agregar un campo estatus al modelo Pago o borrarlo lógicamente)
                pago.uuid = f"CANCELADO_{pago.uuid}" 
                pago.save()
                messages.success(request, "Complemento de pago cancelado en el SAT.")
            else:
                messages.error(request, f"Error SAT: {res['error']}")
                
    return redirect('dashboard_facturacion')

@login_required
def buscar_catalogo_sat(request):
    """
    Búsqueda LOCAL en tu base de datos (Ultra rápida).
    Ya NO usa requests ni la API externa.
    """
    termino = request.GET.get('q', '')
    tipo = request.GET.get('tipo', 'ClaveProdServ') # ClaveProdServ o ClaveUnidad
    
    # Validar mínimo de caracteres
    if not termino or len(termino) < 2:
        return JsonResponse({'results': []})

    # 1. Buscar en la tabla que acabas de llenar con el Excel
    resultados = CatalogoSAT.objects.filter(
        tipo=tipo
    ).filter(
        Q(clave__icontains=termino) | Q(descripcion__icontains=termino)
    )[:50] # Limitamos a 50 resultados

    # 2. Formatear para Select2
    data = []
    for item in resultados:
        data.append({
            'id': item.clave,
            'text': f"{item.clave} - {item.descripcion}" 
        })
    
    return JsonResponse({'results': data})


from django.http import HttpResponse, Http404
from django.conf import settings
import os

@login_required
@permission_required('facturacion.view_factura', raise_exception=True)
def descargar_xml_view(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    
    # A) Si el archivo ya existe físicamente en tu servidor, lo descargamos directo
    if factura.archivo_xml and os.path.exists(factura.archivo_xml.path):
        with open(factura.archivo_xml.path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/xml")
            response['Content-Disposition'] = f'attachment; filename="F-{factura.folio}.xml"'
            return response

    # B) Si NO existe (se borró o no se guardó), lo recuperamos con el ID Interno
    print(f"⚠️ XML local no encontrado para F-{factura.folio}. Recuperando de API...")
    
    resultado = recuperar_xml_api(factura) # <--- Llamada al servicio nuevo
    
    if resultado['success']:
        xml_content = resultado['xml_content']
        
        # 1. Guardarlo en el modelo para la próxima vez
        try:
            # Si viene en base64, decodificar, si viene en texto, encode a bytes
            if "<cfdi:Comprobante" in str(xml_content):
                # Es texto plano
                contenido_bytes = xml_content.encode('utf-8')
            else:
                # Es base64
                contenido_bytes = base64.b64decode(xml_content)

            filename = f"F-{factura.folio}_{factura.folio_fiscal}.xml"
            factura.archivo_xml.save(filename, ContentFile(contenido_bytes))
            factura.save()
            
            # 2. Entregar el archivo al usuario
            response = HttpResponse(contenido_bytes, content_type="application/xml")
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            messages.error(request, f"Error al procesar el XML recuperado: {e}")
            return redirect('dashboard_facturacion')
    else:
        messages.error(request, f"No se pudo recuperar el XML: {resultado.get('error')}")
        return redirect('dashboard_facturacion')
    
@login_required
@transaction.atomic
@permission_required('facturacion.add_factura', raise_exception=True)
def generar_nota_credito(request, factura_id):
    factura_origen = get_object_or_404(Factura, pk=factura_id)

    if not factura_origen.folio_fiscal:
        messages.error(request, "La factura origen debe estar timbrada para crear una Nota de Crédito.")
        return redirect('detalle_factura_cliente', pk=factura_origen.pk)

    if request.method == 'POST':
        form = NotaCreditoForm(request.POST)
        if form.is_valid():
            try:
                emisor = get_emisor_fiscal()
                
                # 1. Crear Cabecera de Nota de Crédito
                nc = Factura.objects.create(
                    emisor=emisor,
                    receptor=factura_origen.receptor,
                    tipo_comprobante='E', # <--- IMPORTANTE
                    serie='NC',
                    folio=f"NC-{Factura.objects.filter(tipo_comprobante='E').count() + 1}",
                    
                    # Relación con la factura origen
                    tipo_relacion='01', # Nota de crédito de los documentos relacionados
                    uuid_relacionado=factura_origen.folio_fiscal,
                    
                    uso_cfdi=form.cleaned_data['uso_cfdi'],
                    metodo_pago='PUE', 
                    forma_pago=form.cleaned_data['forma_pago'],
                    moneda=factura_origen.moneda,
                    tipo_cambio=factura_origen.tipo_cambio,
                    estado='pendiente',
                    fecha_emision=timezone.now()
                )

                # 2. Crear Concepto (Servicios de facturación / 84111506)
                monto = form.cleaned_data['monto_descuento']
                iva = monto * Decimal('0.16')
                
                ConceptoFactura.objects.create(
                    factura=nc,
                    clave_prod_serv="84111506", # Clave estándar para descuentos/bonificaciones
                    clave_unidad="ACT", # Actividad
                    unidad="Actividad",
                    cantidad=1,
                    descripcion=form.cleaned_data['concepto_descripcion'],
                    valor_unitario=monto,
                    importe=monto,
                    iva_importe=iva,
                    iva_ret_importe=0
                )

                # 3. Calcular Totales
                nc.subtotal = monto
                nc.impuestos_trasladados = iva
                nc.monto_total = monto + iva
                nc.save()

                # 4. Timbrar
                resultado = timbrar_factura_api(nc)

                if resultado['success']:
                    data_sat = resultado['data']
                    nc.folio_fiscal = data_sat.get('uuid')
                    nc.id_fiscalapi = data_sat.get('id')
                    nc.estado = 'timbrado'
                    nc.fecha_timbrado = timezone.now()
                    
                    # Guardar XML
                    xml_b64 = data_sat.get('xml')
                    if xml_b64:
                        import base64
                        from django.core.files.base import ContentFile
                        xml_content = base64.b64decode(xml_b64)
                        filename = f"{nc.folio_fiscal}.xml"
                        nc.archivo_xml.save(filename, ContentFile(xml_content), save=False)
                    
                    nc.save()
                    messages.success(request, f"Nota de Crédito {nc.folio} generada correctamente.")
                    return redirect('detalle_factura_cliente', pk=nc.pk)
                else:
                    nc.estado = 'error'
                    nc.save()
                    messages.error(request, f"Error al timbrar Nota de Crédito: {resultado.get('error')}")
                    return redirect('detalle_factura_cliente', pk=nc.pk)

            except Exception as e:
                messages.error(request, f"Error interno: {e}")

    else:
        # Pre-llenar forma de pago con la de la factura origen
        form = NotaCreditoForm(initial={'forma_pago': factura_origen.forma_pago})

    return render(request, 'facturacion/crear_nota_credito.html', {
        'form': form,
        'factura_origen': factura_origen
    })
    
@login_required
@transaction.atomic
@permission_required('facturacion.add_factura', raise_exception=True)
def crear_nota_credito_libre(request):
    if request.method == 'POST':
        form = NotaCreditoLibreForm(request.POST)
        if form.is_valid():
            try:
                emisor = get_emisor_fiscal()
                if not emisor:
                    messages.error(request, "No hay emisor configurado.")
                    return redirect('dashboard_facturacion')

                # 1. Crear Cabecera
                nc = form.save(commit=False)
                nc.emisor = emisor
                nc.tipo_comprobante = 'E' # EGRESO
                nc.serie = 'NC'
                nc.folio = f"NC-{Factura.objects.filter(tipo_comprobante='E').count() + 1}"
                nc.metodo_pago = 'PUE' # Siempre PUE
                nc.moneda = 'MXN'
                nc.tipo_cambio = 1
                nc.fecha_emision = timezone.now()
                nc.estado = 'pendiente'
                nc.save()

                # 2. Crear Concepto
                monto = form.cleaned_data['monto_sin_iva']
                desc = form.cleaned_data['concepto_descripcion']
                iva = monto * Decimal('0.16')
                
                ConceptoFactura.objects.create(
                    factura=nc,
                    clave_prod_serv="84111506", # Servicios de facturación
                    clave_unidad="ACT", 
                    unidad="Actividad",
                    cantidad=1,
                    descripcion=desc,
                    valor_unitario=monto,
                    importe=monto,
                    iva_importe=iva,
                    iva_ret_importe=0
                )

                # 3. Totales
                nc.subtotal = monto
                nc.impuestos_trasladados = iva
                nc.monto_total = monto + iva
                nc.save()

                # 4. Intentar Timbrar
                resultado = timbrar_factura_api(nc)

                if resultado['success']:
                    data_sat = resultado['data']
                    nc.folio_fiscal = data_sat.get('uuid')
                    nc.id_fiscalapi = data_sat.get('id')
                    nc.estado = 'timbrado'
                    nc.fecha_timbrado = timezone.now()
                    
                    xml_b64 = data_sat.get('xml')
                    if xml_b64:
                        xml_content = base64.b64decode(xml_b64)
                        filename = f"{nc.folio_fiscal}.xml"
                        nc.archivo_xml.save(filename, ContentFile(xml_content), save=False)
                    
                    nc.save()
                    messages.success(request, f"Nota de Crédito {nc.folio} creada y timbrada.")
                else:
                    nc.estado = 'error'
                    nc.save()
                    messages.warning(request, f"Nota guardada pero NO timbrada: {resultado.get('error')}")

                return redirect('detalle_factura_cliente', pk=nc.pk)

            except Exception as e:
                messages.error(request, f"Error: {e}")
    else:
        form = NotaCreditoLibreForm()

    return render(request, 'facturacion/crear_nota_credito_libre.html', {'form': form})

@login_required
def api_crear_serie(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip().upper()
        if not nombre:
            return JsonResponse({'success': False, 'error': 'El nombre es obligatorio'})
        
        if SeriePersonalizada.objects.filter(nombre=nombre).exists():
            return JsonResponse({'success': False, 'error': 'Esta serie ya existe'})
            
        serie = SeriePersonalizada.objects.create(nombre=nombre)
        return JsonResponse({'success': True, 'id': serie.id, 'nombre': serie.nombre})
    return JsonResponse({'success': False})

@login_required
def api_eliminar_serie(request, serie_id):
    if request.method == 'POST':
        try:
            serie = SeriePersonalizada.objects.get(pk=serie_id)
            # Solo la borramos de la lista de opciones futuras.
            # NO afecta a las facturas pasadas porque en Factura guardamos el texto, no el ID.
            serie.delete() 
            return JsonResponse({'success': True})
        except SeriePersonalizada.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Serie no encontrada'})
    return JsonResponse({'success': False})

def obtener_saldo_timbres():
    try:
        url = f"{API_URL}/api/v4/account"
        headers = {
            "X-API-KEY": API_KEY,
            "Content-Type": "application/json"
        }

        response = requests.get(url, headers=headers, timeout=5)

        if response.status_code != 200:
            print("⚠️ Error FiscalAPI:", response.text)
            return "--"

        data = response.json()

        # Estos campos SÍ existen según la cuenta
        return (
            data.get('available_credits')
            or data.get('credits')
            or data.get('balance')
            or "--"
        )

    except Exception as e:
        print("❌ Error consultando timbres:", str(e))
        return "--"
# facturacion/views.py

@login_required
@permission_required('facturacion.view_complementopago', raise_exception=True)
def generar_pdf_pago(request, pk):
    pago = get_object_or_404(ComplementoPago, pk=pk)
    
    # Variable para almacenar el contenido del XML en memoria
    xml_bytes = None

    # 1. INTENTO DE LECTURA LOCAL
    # Intentamos leer el archivo si la BD dice que existe
    if pago.archivo_xml:
        try:
            with pago.archivo_xml.open('rb') as f:
                xml_bytes = f.read()
        except Exception as e:
            print(f"⚠️ Archivo físico no encontrado o error lectura: {e}")
            xml_bytes = None

    # 2. RECUPERACIÓN DE EMERGENCIA (API)
    # Si no pudimos leer el archivo (xml_bytes is None) pero tenemos UUID, pedimos ayuda a FiscalAPI
    if not xml_bytes and pago.uuid:
        print(f"🔄 Recuperando XML de pago {pago.folio} desde API...")
        from .services import recuperar_cfdi_xml
        res = recuperar_cfdi_xml(pago.uuid) 
        
        if res['success']:
            xml_raw = res['xml']
            # Decodificar si viene en base64 o usar directo si es texto
            if "<cfdi:Comprobante" in str(xml_raw):
                xml_bytes = xml_raw.encode('utf-8') if isinstance(xml_raw, str) else xml_raw
            else:
                xml_bytes = base64.b64decode(xml_raw)
            
            # Guardamos el archivo recuperado para la próxima vez
            filename = f"Pago_{pago.serie}{pago.folio}.xml"
            # save=False para no disparar señales ni loops, luego hacemos pago.save()
            pago.archivo_xml.save(filename, ContentFile(xml_bytes), save=False)
            pago.save()

    # 3. PROCESAMIENTO DE DATOS SAT (QR y Sellos)
    datos_sat = {
        'sello_sat': '', 'sello_cfd': '', 'cadena_original': '',
        'no_certificado': '', 'fecha_timbrado': '', 'rfc_prov': '',
        'qr_url': None,
        'uuid': pago.uuid
    }
    
    # Solo procesamos si logramos obtener el contenido del XML (Local o API)
    if xml_bytes:
        try:
            # Parsear desde memoria (BytesIO) es más seguro que leer archivo directo
            root = ET.fromstring(xml_bytes)
            
            ns = {
                'cfdi': 'http://www.sat.gob.mx/cfd/4',
                'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
            }
            
            # Buscamos el timbre (el .// es recursivo, encuentra el nodo donde esté)
            tfd = root.find('.//tfd:TimbreFiscalDigital', ns)
            
            if tfd is not None:
                datos_sat['uuid'] = tfd.get('UUID')
                datos_sat['fecha_timbrado'] = tfd.get('FechaTimbrado')
                datos_sat['sello_sat'] = tfd.get('SelloSAT')
                datos_sat['sello_cfd'] = tfd.get('SelloCFD') or root.get('Sello')
                datos_sat['no_certificado'] = tfd.get('NoCertificadoSAT')
                datos_sat['rfc_prov'] = tfd.get('RfcProvCertif')
                
                datos_sat['cadena_original'] = f"||1.1|{datos_sat['uuid']}|{datos_sat['fecha_timbrado']}|{datos_sat['rfc_prov']}|{datos_sat['sello_cfd']}|{datos_sat['no_certificado']}||"

                # --- GENERACIÓN DEL QR ---
                total_xml = root.get('Total', '0')
                rfc_emisor = root.find('cfdi:Emisor', ns).get('Rfc')
                rfc_receptor = root.find('cfdi:Receptor', ns).get('Rfc')
                # Tomamos los últimos 8 caracteres del sello
                sello_last8 = (datos_sat['sello_cfd'] or "")[-8:]
                
                qr_content = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={datos_sat['uuid']}&re={rfc_emisor}&rr={rfc_receptor}&tt={total_xml}&fe={sello_last8}"
                
                qr_img = qrcode.make(qr_content)
                buffer = BytesIO()
                qr_img.save(buffer, format="PNG")
                img_str = base64.b64encode(buffer.getvalue()).decode()
                datos_sat['qr_url'] = f"data:image/png;base64,{img_str}"
            else:
                print("❌ XML válido pero SIN TimbreFiscalDigital")

        except Exception as e:
            print(f"❌ Error procesando XML: {e}")

    # 4. Monto en Letra
    try:
        total_float = float(pago.monto_total)
        enteros = int(total_float)
        centavos = int(round((total_float - enteros) * 100))
        texto = num2words(enteros, lang='es').upper()
        monto_letra = f"{texto} PESOS {centavos:02d}/100 M.N."
    except:
        monto_letra = "CANTIDAD EN LETRA NO DISPONIBLE"

    context = {
        'pago': pago,
        'datos_sat': datos_sat,
        'monto_letra': monto_letra,
        'emisor': get_emisor_fiscal(),
        'color_principal': '#198754', 
    }
    
    html_string = render_to_string('facturacion/pdf_pago.html', context)
    
    if HTML:
        pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="REP-{pago.serie}{pago.folio}.pdf"'
        return response
    
    return HttpResponse("Error: Librería WeasyPrint no instalada", status=500)


@login_required
@permission_required('facturacion.view_complementopago', raise_exception=True)
def descargar_xml_pago(request, pk):
    """
    Descarga el XML del Complemento de Pago.
    Si no está en el servidor, intenta recuperarlo de la API usando el UUID.
    """
    pago = get_object_or_404(ComplementoPago, pk=pk)
    
    # 1. Si el archivo ya existe físicamente, lo descargamos directo
    if pago.archivo_xml and os.path.exists(pago.archivo_xml.path):
        with open(pago.archivo_xml.path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/xml")
            # Nombre de archivo sugerido: REP-SERIEFOLIO.xml
            response['Content-Disposition'] = f'attachment; filename="REP-{pago.serie}{pago.folio}.xml"'
            return response

    # 2. Si NO existe, validamos que esté timbrado para pedirlo a la API
    if not pago.uuid:
        messages.error(request, "Este pago no tiene UUID, no se puede recuperar el XML.")
        return redirect('dashboard_facturacion')

    print(f"⚠️ XML local no encontrado para REP-{pago.folio}. Recuperando de API...")
    
    # Usamos el servicio existente en services.py
    from .services import recuperar_cfdi_xml
    resultado = recuperar_cfdi_xml(pago.uuid) 
    
    if resultado['success']:
        xml_content = resultado['xml']
        
        try:
            # 3. Procesar contenido (Texto vs Base64)
            if "<cfdi:Comprobante" in str(xml_content):
                # Es texto plano
                contenido_bytes = xml_content.encode('utf-8')
            else:
                # Es base64
                contenido_bytes = base64.b64decode(xml_content)

            # 4. Guardarlo en el modelo para el futuro
            filename = f"REP-{pago.serie}{pago.folio}_{pago.uuid}.xml"
            pago.archivo_xml.save(filename, ContentFile(contenido_bytes))
            pago.save()
            
            # 5. Entregar el archivo al usuario
            response = HttpResponse(contenido_bytes, content_type="application/xml")
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            messages.error(request, f"Error al procesar el XML recuperado: {e}")
            return redirect('dashboard_facturacion')
    else:
        messages.error(request, f"No se pudo recuperar el XML: {resultado.get('error')}")
        return redirect('dashboard_facturacion')
    
def buscar_cp_view(request):
    cp = request.GET.get('cp')
    if not cp: return JsonResponse({'found': False})

    data = {'found': False, 'colonias': []}

    # 1. Buscar Estado y Municipio (Usando la tabla de cruce)
    try:
        relacion = CodigoPostalFiscal.objects.filter(codigo=cp).first()
        if relacion:
            data['found'] = True
            data['estado'] = relacion.estado.nombre
            # Ajustamos nombre de municipio (a veces viene con clave en la descripción)
            data['municipio'] = relacion.municipio.nombre 
    except Exception as e:
        print(f"Error buscando CP: {e}")

    # 2. Buscar Colonias (Usando la tabla de colonias)
    colonias = Colonia.objects.filter(codigo_postal=cp).order_by('nombre')
    if colonias.exists():
        data['found'] = True # Encontramos colonias aunque no tengamos estado/muni
        data['colonias'] = [{'nombre': c.nombre} for c in colonias]
    
    return JsonResponse(data)

@login_required
@permission_required('facturacion.view_factura', raise_exception=True)
def exportar_reporte_contable(request):
    """
    Genera un CSV detallado para contabilidad (Ingresos y Egresos)
    respetando los filtros del Dashboard.
    """
    # 1. Recuperar filtros del request
    q_cliente = request.GET.get('q_cliente')
    q_folio = request.GET.get('q_folio')
    q_estado = request.GET.get('q_estado')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    # 2. QueryBase
    facturas = Factura.objects.all().select_related('receptor').order_by('fecha_emision')

    # 3. Aplicar los mismos filtros que el Dashboard
    if q_cliente:
        facturas = facturas.filter(receptor__razon_social__icontains=q_cliente)
    
    if q_folio:
        facturas = facturas.filter(
            Q(folio__icontains=q_folio) | Q(folio_fiscal__icontains=q_folio)
        )

    if q_estado:
        facturas = facturas.filter(estado=q_estado)
    
    if fecha_inicio:
        facturas = facturas.filter(fecha_emision__date__gte=fecha_inicio)
    
    if fecha_fin:
        facturas = facturas.filter(fecha_emision__date__lte=fecha_fin)

    # 4. Generar respuesta CSV
    response = HttpResponse(content_type='text/csv')
    nombre_archivo = f"Reporte_Contable_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    response.write(u'\ufeff'.encode('utf8'))
    
    writer = csv.writer(response)
    
    # 5. Encabezados DETALLADOS
    writer.writerow([
        'Tipo Comprobante',
        'Serie',
        'Folio Interno',
        'UUID (Folio Fiscal)',
        'Fecha Emisión',
        'Fecha Timbrado',
        'RFC Receptor',
        'Nombre Receptor (Cliente)',
        'Uso CFDI',
        'Método Pago',
        'Forma Pago',
        'Moneda',
        'Tipo Cambio',
        'Subtotal',
        'Total Traslados (IVA)',
        'Total Retención IVA',  # Separado
        'Total Retención ISR',  # Separado
        'Total Facturado',
        'Estado',
        'Estatus Cobranza',
        'UUID Relacionado'
    ])

    # 6. Barrido de datos con cálculo
    for f in facturas:
        # Calcular desglose real iterando conceptos (Más preciso para contabilidad)
        ret_iva = Decimal(0)
        ret_isr = Decimal(0)
        
        # Iteramos conceptos para separar ISR de IVA Retenido
        for c in f.conceptos.all():
            # Si la clave es 001 es ISR, si es 002 es IVA
            if c.retencion_impuesto_clave == '001':
                ret_isr += c.iva_ret_importe
            else:
                ret_iva += c.iva_ret_importe

        # Estatus Cobranza
        estatus_cobranza = "PENDIENTE"
        if f.estado == 'pagada' or (f.metodo_pago == 'PUE' and f.estado == 'timbrado'):
            estatus_cobranza = "PAGADO"
        elif f.estado == 'cancelada':
            estatus_cobranza = "CANCELADO"
            
        tipo_comp = "INGRESO" if f.tipo_comprobante == 'I' else "EGRESO (NC)"
        fecha_timbrado = f.fecha_timbrado.strftime('%d/%m/%Y %H:%M') if f.fecha_timbrado else "Sin Timbrar"

        writer.writerow([
            tipo_comp,
            f.serie or "",
            f.folio,
            f.folio_fiscal or "NO TIMBRADO",
            f.fecha_emision.strftime('%d/%m/%Y %H:%M'),
            fecha_timbrado,
            f.receptor.rfc,
            f.receptor.razon_social,
            f.uso_cfdi,
            f.metodo_pago,
            f.forma_pago,
            f.moneda,
            f.tipo_cambio,
            f.subtotal,
            f.impuestos_trasladados, # Asumimos mayormente IVA
            ret_iva,                 # Columna Ret IVA
            ret_isr,                 # Columna Ret ISR
            f.monto_total,
            f.get_estado_display().upper(),
            estatus_cobranza,
            f.uuid_relacionado or ""
        ])

    return response

# facturacion/views.py

from .models import ProductoServicio
from .forms import ProductoServicioForm

# --- GESTIÓN DEL CATÁLOGO (CRUD) ---

@login_required
def lista_productos(request):
    productos = ProductoServicio.objects.filter(usuario=request.user).order_by('nombre')
    return render(request, 'facturacion/catalogo/lista.html', {'productos': productos})

@login_required
def crear_producto(request):
    if request.method == 'POST':
        form = ProductoServicioForm(request.POST)
        if form.is_valid():
            prod = form.save(commit=False)
            prod.usuario = request.user
            prod.save()
            messages.success(request, "Producto guardado correctamente.")
            return redirect('lista_productos')
    else:
        form = ProductoServicioForm()
    return render(request, 'facturacion/catalogo/formulario.html', {'form': form, 'titulo': 'Nuevo Producto'})

@login_required
def editar_producto(request, pk):
    prod = get_object_or_404(ProductoServicio, pk=pk, usuario=request.user)
    if request.method == 'POST':
        form = ProductoServicioForm(request.POST, instance=prod)
        if form.is_valid():
            form.save()
            messages.success(request, "Producto actualizado.")
            return redirect('lista_productos')
    else:
        form = ProductoServicioForm(instance=prod)
    return render(request, 'facturacion/catalogo/formulario.html', {'form': form, 'titulo': 'Editar Producto'})

@login_required
def eliminar_producto(request, pk):
    # Al eliminar aquí NO AFECTA facturas pasadas porque usamos copiado de datos
    prod = get_object_or_404(ProductoServicio, pk=pk, usuario=request.user)
    if request.method == 'POST':
        prod.delete()
        messages.success(request, "Producto eliminado del catálogo.")
    return redirect('lista_productos')

# --- API PARA AUTOCOMPLETADO EN FACTURA ---

@login_required
def api_buscar_productos_local(request):
    q = request.GET.get('q', '')
    productos = ProductoServicio.objects.filter(usuario=request.user).filter(
        Q(nombre__icontains=q) | Q(codigo_interno__icontains=q)
    )[:20]
    
    results = []
    for p in productos:
        results.append({
            'id': p.id,
            'text': f"{p.nombre} - ${p.precio_unitario}",
            
            # Datos para rellenar la fila
            'clave_sat': p.clave_prod_serv,
            'clave_unidad': p.clave_unidad,
            'descripcion': p.descripcion_sat,
            'precio': str(p.precio_unitario),
            
            # --- NUEVO: Enviamos los IDs de los impuestos vinculados ---
            'traslado_id': p.impuesto_traslado.id if p.impuesto_traslado else "",
            'retencion_id': p.impuesto_retencion.id if p.impuesto_retencion else ""
        })
    
    return JsonResponse({'results': results})

from .models import CatalogoImpuesto
from .forms import CatalogoImpuestoForm

# --- GESTIÓN DE IMPUESTOS ---
@login_required
def lista_impuestos(request):
    impuestos = CatalogoImpuesto.objects.all()
    return render(request, 'facturacion/impuestos/lista.html', {'impuestos': impuestos})

@login_required
def crear_impuesto(request):
    if request.method == 'POST':
        form = CatalogoImpuestoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Impuesto guardado.")
            return redirect('lista_impuestos')
    else:
        form = CatalogoImpuestoForm()
    return render(request, 'facturacion/impuestos/formulario.html', {'form': form, 'titulo': 'Nuevo Impuesto'})

@login_required
def editar_impuesto(request, pk):
    impuesto = get_object_or_404(CatalogoImpuesto, pk=pk)
    if request.method == 'POST':
        form = CatalogoImpuestoForm(request.POST, instance=impuesto)
        if form.is_valid():
            form.save()
            messages.success(request, "Impuesto actualizado.")
            return redirect('lista_impuestos')
    else:
        form = CatalogoImpuestoForm(instance=impuesto)
    return render(request, 'facturacion/impuestos/formulario.html', {'form': form, 'titulo': 'Editar Impuesto'})

@login_required
def eliminar_impuesto(request, pk):
    impuesto = get_object_or_404(CatalogoImpuesto, pk=pk)
    if request.method == 'POST':
        impuesto.delete()
        messages.success(request, "Impuesto eliminado.")
    return redirect('lista_impuestos')

def api_validar_lugar(request):
    lugar_id = request.GET.get('lugar_id')
    if not lugar_id:
        return JsonResponse({'valido': False, 'error': 'No ID'})
    
    try:
        lugar = Lugar.objects.get(pk=lugar_id)
        faltantes = []
        
        # --- VALIDACIÓN ESTRICTA ---
        if not lugar.rfc: faltantes.append('RFC')
        if not lugar.razon_social: faltantes.append('Razón Social')
        if not lugar.regimen_fiscal: faltantes.append('Régimen Fiscal')
        if not lugar.codigo_postal: faltantes.append('Código Postal')
        
        # Validación de Dirección (Sat requiere al menos Código Postal, pero validamos calle para evitar errores)
        if not lugar.calle: faltantes.append('Calle')
        if not lugar.municipio: faltantes.append('Municipio')
        if not lugar.estado: faltantes.append('Estado')

        es_valido = len(faltantes) == 0
        
        return JsonResponse({
            'valido': es_valido,
            'faltantes': faltantes,
            'mensaje': "Datos completos" if es_valido else f"Falta: {', '.join(faltantes)}"
        })
    except Lugar.DoesNotExist:
        return JsonResponse({'valido': False, 'faltantes': ['Lugar no encontrado']})