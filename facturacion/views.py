# facturacion/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP # <--- IMPORTANTE
from django.utils import timezone
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db.models import Sum, Count, Q # <--- Asegúrate de importar esto
# Modelos
from .models import Factura, ConceptoFactura, DatosFiscales
from ternium.models import Remision, Cliente, Lugar
from .models import Factura, ConceptoFactura, DatosFiscales, ComplementoPago, PagoDoctoRelacionado
from django.shortcuts import render

# Formularios
from .forms import (
    GenerarFacturaForm, 
    NuevaFacturaLibreForm, 
    ConfigurarEmisorForm, 
    DatosFiscalesClienteForm,
    PagoForm,
    ComplementoPagoCabeceraForm  # <--- AGREGA ESTO
)

try:
    from weasyprint import HTML
except ImportError:
    HTML = None

# --- HELPER ---
def get_emisor_fiscal():
    return DatosFiscales.objects.filter(es_emisor=True).first()

# --- VISTAS ---

@login_required
def dashboard_facturacion(request):
    """
    Dashboard principal de facturación.
    """
    # 1. Query Base Facturas
    facturas = Factura.objects.all().select_related('receptor').prefetch_related('remisiones').order_by('-fecha_emision')

    # 2. Query Base Pagos (CORREGIDO PARA NUEVO MODELO)
    # Ya no existe 'factura' en ComplementoPago. Ahora traemos el 'receptor'
    # y "pre-cargamos" los documentos relacionados para evitar lentitud.
    pagos = ComplementoPago.objects.select_related('receptor')\
        .prefetch_related('documentos_relacionados', 'documentos_relacionados__factura')\
        .all().order_by('-fecha_pago')

    # 3. Filtros
    q_cliente = request.GET.get('q_cliente')
    q_folio = request.GET.get('q_folio')

    if q_cliente:
        # Filtro en facturas
        facturas = facturas.filter(receptor__razon_social__icontains=q_cliente)
        # Filtro en pagos (El cliente está directo en el encabezado ahora)
        pagos = pagos.filter(receptor__razon_social__icontains=q_cliente)
    
    if q_folio:
        # Filtro en facturas
        facturas = facturas.filter(folio__icontains=q_folio)
        
        # Filtro en pagos (CORREGIDO):
        # Buscamos si alguno de los documentos relacionados tiene ese folio de factura
        pagos = pagos.filter(documentos_relacionados__factura__folio__icontains=q_folio).distinct()

    # --- DESCARGA MASIVA XML (ZIP) ---
    if request.GET.get('exportar') == 'xml_masivo':
        # ... (Tu código de exportación existente) ...
        pass 

    # 4. KPIs
    total_timbradas = Factura.objects.filter(estado='timbrado').count()
    total_pendientes = Factura.objects.filter(estado='pendiente').count()
    total_canceladas = Factura.objects.filter(estado='cancelada').count()

    # 5. Datos para el ComboBox
    clientes_combo = DatosFiscales.objects.filter(
        facturas_recibidas__isnull=False
    ).values_list('razon_social', flat=True).distinct().order_by('razon_social')

    context = {
        'facturas': facturas,
        'pagos': pagos,
        'total_timbradas': total_timbradas,
        'total_pendientes': total_pendientes,
        'total_canceladas': total_canceladas,
        'clientes_combo': clientes_combo,
        'q_cliente': q_cliente,
        'q_folio': q_folio,
    }

    return render(request, 'facturacion/dashboard.html', context)

@login_required
def configurar_emisor(request):
    if request.method == 'POST':
        form = ConfigurarEmisorForm(request.POST)
        if form.is_valid():
            lugar = form.cleaned_data['lugar_origen']
            
            datos, _ = DatosFiscales.objects.get_or_create(es_emisor=True)
            
            # Copiar datos
            datos.rfc = lugar.rfc
            datos.razon_social = lugar.razon_social
            datos.regimen_fiscal = lugar.regimen_fiscal
            datos.codigo_postal = lugar.codigo_postal
            datos.uso_cfdi = lugar.uso_cfdi or 'G03'
            
            # Dirección
            datos.calle = f"{lugar.calle} {lugar.numero_exterior}".strip()
            datos.colonia = lugar.colonia
            datos.municipio = lugar.municipio
            datos.estado = lugar.estado
            datos.save()
            
            messages.success(request, f"Emisor configurado con datos de {lugar.nombre}")
            return redirect('dashboard_facturacion')
    else:
        form = ConfigurarEmisorForm()
    return render(request, 'facturacion/configurar_emisor.html', {'form': form})

@login_required
def prefacturar_remisiones(request):
    """
    Vista clave: Detecta datos fiscales del Lugar(Destino) si el Cliente no tiene.
    """
    if request.method == 'POST':
        remision_ids = request.POST.getlist('remisiones_ids')
        
        if not remision_ids:
            messages.error(request, "Selecciona al menos una remisión.")
            return redirect('remisiones_por_facturar')

        # 1. DEFINIR LA VARIABLE 'remisiones' (Crucial para evitar NameError)
        remisiones = Remision.objects.filter(id__in=remision_ids)\
            .select_related('cliente', 'destino')\
            .prefetch_related('detalles__material')

        if not remisiones.exists():
            messages.error(request, "No se encontraron las remisiones seleccionadas.")
            return redirect('remisiones_por_facturar')

        # 2. Validar Cliente
        cliente = remisiones.first().cliente
        if any(r.cliente != cliente for r in remisiones):
            messages.error(request, "Todas las remisiones deben ser del mismo cliente.")
            return redirect('remisiones_por_facturar')

        # 3. Validar Emisor
        emisor = get_emisor_fiscal()
        if not emisor:
            messages.warning(request, "Configura tu Emisor primero (Tus datos fiscales).")
            return redirect('configurar_emisor')

        # 4. Buscar Receptor (Datos Fiscales del Cliente)
        try:
            receptor = cliente.datos_fiscales
        except:
            receptor = None

        # 5. AUTO-DESCUBRIMIENTO (Si el cliente no tiene datos, buscamos en los Lugares)
        if not receptor:
            lugar_con_datos = None
            # Buscamos en las remisiones si alguna tiene un destino con RFC
            for r in remisiones:
                if r.destino and r.destino.rfc:
                    lugar_con_datos = r.destino
                    break
            
            if lugar_con_datos:
                # Construimos la dirección completa en una sola cadena
                direccion_completa = f"{lugar_con_datos.calle or ''} {lugar_con_datos.numero_exterior or ''} {lugar_con_datos.numero_interior or ''}, Col. {lugar_con_datos.colonia or ''}, {lugar_con_datos.municipio or ''}, {lugar_con_datos.estado or ''}"
                direccion_completa = direccion_completa.replace(" ,", ",").strip(", ")

                # Creamos los datos fiscales
                receptor = DatosFiscales.objects.create(
                    es_emisor=False,
                    cliente_interno=cliente,
                    rfc=lugar_con_datos.rfc,
                    razon_social=lugar_con_datos.razon_social,
                    regimen_fiscal=lugar_con_datos.regimen_fiscal or '601',
                    uso_cfdi=lugar_con_datos.uso_cfdi or 'G03',
                    codigo_postal=lugar_con_datos.codigo_postal,
                    direccion=direccion_completa
                )
                messages.info(request, f"Datos fiscales importados automáticamente del lugar '{lugar_con_datos.nombre}'.")

        # 6. Preparar formulario y renderizar
        form = GenerarFacturaForm()
        if receptor:
            form.initial['uso_cfdi'] = receptor.uso_cfdi

        return render(request, 'facturacion/prefactura.html', {
            'remisiones': remisiones,
            'emisor': emisor,
            'receptor': receptor,
            'cliente': cliente,
            'form': form
        })

    # RETORNO PARA GET (Evita el ValueError)
    messages.warning(request, "Acceso inválido a prefacturación.")
    return redirect('remisiones_por_facturar')
@login_required
@transaction.atomic
def generar_factura_accion(request):
    if request.method == 'POST':
        form = GenerarFacturaForm(request.POST)
        if form.is_valid():
            remision_ids = request.POST.getlist('remision_id')
            remisiones = Remision.objects.filter(id__in=remision_ids)
            
            emisor = get_emisor_fiscal()
            
            if not remisiones.exists():
                messages.error(request, "No se seleccionaron remisiones.")
                return redirect('remisiones_por_facturar')

            cliente = remisiones.first().cliente
            receptor = getattr(cliente, 'datos_fiscales', None)

            if not receptor:
                messages.error(request, "Error: El cliente sigue sin datos fiscales.")
                return redirect('remisiones_por_facturar')

            # Crear Encabezado de Factura
            factura = Factura.objects.create(
                emisor=emisor,
                receptor=receptor,
                folio=f"F-{Factura.objects.count() + 1}",
                uso_cfdi=form.cleaned_data['uso_cfdi'],
                metodo_pago=form.cleaned_data['metodo_pago'],
                forma_pago=form.cleaned_data['forma_pago'],
                moneda=form.cleaned_data['moneda'],
                tipo_cambio=form.cleaned_data['tipo_cambio'],
                subtotal=0, 
                monto_total=0
            )
            factura.remisiones.set(remisiones)

            subtotal = 0
            impuestos = 0
            retenciones = 0
            aplicar_ret = form.cleaned_data.get('aplicar_retencion')

            for r in remisiones:
                precio_input = request.POST.get(f"precio_{r.id}", "0")
                try:
                    precio_unitario = float(precio_input)
                except ValueError:
                    precio_unitario = 0.0
                
                # --- NUEVO: GUARDAR PRECIO EN LA REMISIÓN ---
                # Esto cumple tu requerimiento de "que se guarde el precio"
                r.tarifa = precio_unitario
                r.save() 
                # ---------------------------------------------

                cantidad = float(r.total_peso_dlv)
                importe = cantidad * precio_unitario
                iva = importe * 0.16
                ret = importe * 0.06 if aplicar_ret else 0
                
                material = r.detalles.first().material
                clave_sat = getattr(material, 'clave_sat', '01010101') 
                clave_unidad = getattr(material, 'clave_unidad_sat', 'KGM')

                ConceptoFactura.objects.create(
                    factura=factura,
                    cantidad=cantidad,
                    descripcion=f"{material.nombre} - Nota {r.remision}",
                    valor_unitario=precio_unitario,
                    importe=importe,
                    unidad="Kilogramo",
                    iva_importe=iva,
                    iva_ret_importe=ret,
                    clave_prod_serv=clave_sat,
                    clave_unidad=clave_unidad,
                )
                subtotal += importe
                impuestos += iva
                retenciones += ret

            factura.subtotal = subtotal
            factura.impuestos_trasladados = impuestos
            factura.impuestos_retenidos = retenciones
            factura.monto_total = subtotal + impuestos - retenciones
            
            factura.estado = 'timbrado' 
            factura.fecha_timbrado = timezone.now()
            factura.save()

            messages.success(request, f"Factura {factura.folio} generada correctamente.")
            return redirect('detalle_factura_cliente', pk=factura.pk)

    return redirect('dashboard_facturacion')

@login_required
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
            datos.save()
            messages.success(request, "Datos fiscales guardados.")
            return redirect('remisiones_por_facturar')
    else:
        form = DatosFiscalesClienteForm(instance=instance)

    return render(request, 'facturacion/configurar_cliente.html', {'form': form, 'cliente': cliente})


# Asegúrate de importar Paginator al inicio
from django.core.paginator import Paginator

@login_required
def remisiones_por_facturar(request):
    # 1. Query Base
    queryset = Remision.objects.filter(
        status__in=['TERMINADO', 'AUDITADO']
    ).exclude(
        facturas__estado='timbrado'
    ).exclude(
        destino__nombre__icontains="PATIO"
    ).select_related('cliente', 'destino', 'origen').prefetch_related('detalles__material').order_by('-fecha')

    # 2. Filtros
    q_cliente = request.GET.get('q_cliente')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if q_cliente:
        queryset = queryset.filter(cliente__nombre=q_cliente)
    
    if fecha_inicio and fecha_fin:
        queryset = queryset.filter(fecha__range=[fecha_inicio, fecha_fin])

    # --- EXPORTAR A EXCEL ---
    if request.GET.get('exportar') == 'excel':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="remisiones_pendientes.csv"'
        response.write(u'\ufeff'.encode('utf8'))
        
        writer = csv.writer(response)
        writer.writerow(['Folio', 'Fecha', 'Cliente', 'Origen', 'Destino', 'Material', 'Peso Neto (kg)'])

        for r in queryset:
            # Aquí SÍ podemos usar .total_peso_dlv porque estamos en un bucle de Python, no en una consulta SQL directa
            material_nombre = r.detalles.first().material.nombre if r.detalles.exists() else "N/A"
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

    # 3. CÁLCULOS OPTIMIZADOS (CORREGIDO)
    total_pendientes = queryset.count()

    # Quitamos 'peso_total' del annotate porque 'total_peso_dlv' no es un campo de BD.
    # Solo contamos los viajes por cliente, que es muy rápido.
    resumen_clientes = queryset.values('cliente__nombre').annotate(
        conteo=Count('id')
    ).order_by('-conteo')

    # 4. PAGINACIÓN
    paginator = Paginator(queryset, 50) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 5. DATOS PARA EL COMBOBOX
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
def detalle_factura(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    return render(request, 'facturacion/detalle.html', {'factura': factura})

@login_required
def generar_pdf(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    html_string = render_to_string('facturacion/pdf_factura.html', {'factura': factura})
    if HTML:
        pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="F-{factura.folio}.pdf"'
        return response
    return HttpResponse("WeasyPrint no instalado", status=500)

@login_required
@transaction.atomic
def crear_factura_nueva(request):
    if request.method == 'POST':
        form = NuevaFacturaLibreForm(request.POST)
        
        if form.is_valid():
            try:
                # ... (Tu código de validación de emisor y creación de encabezado sigue igual) ...
                emisor = get_emisor_fiscal()
                if not emisor:
                    messages.error(request, "No tienes configurados tus datos fiscales como Emisor.")
                    return redirect('configurar_emisor')

                factura = form.save(commit=False)
                factura.emisor = emisor
                factura.folio = f"F-LIBRE-{Factura.objects.count() + 1}"
                factura.fecha_emision = timezone.now()
                factura.estado = 'pendiente'
                factura.subtotal = 0
                factura.monto_total = 0
                factura.save()

                # --- AQUI EMPIEZA EL CAMBIO EN LOS CONCEPTOS ---
                
                # Recibimos las listas del HTML
                cantidades = request.POST.getlist('cantidad[]')
                unidades = request.POST.getlist('unidad[]')       # <--- NUEVO
                claves_sat = request.POST.getlist('clave_sat[]')  # <--- NUEVO
                descripciones = request.POST.getlist('descripcion[]')
                valores = request.POST.getlist('valor_unitario[]')
                
                subtotal = 0
                impuestos = 0
                retenciones = 0
                aplicar_ret = form.cleaned_data.get('aplicar_retencion', False)

                for i in range(len(descripciones)):
                    # Validar que la línea tenga datos esenciales
                    if not descripciones[i] or not cantidades[i] or not valores[i]:
                        continue
                        
                    cant = float(cantidades[i])
                    val = float(valores[i])
                    desc = descripciones[i]
                    
                    # Recuperamos Unidad y Clave SAT ingresadas
                    uni = unidades[i] if i < len(unidades) and unidades[i] else "Pieza"
                    # Clave Prod/Serv (Ej: 84111506)
                    c_sat = claves_sat[i] if i < len(claves_sat) and claves_sat[i] else "01010101"
                    
                    importe = cant * val
                    iva = importe * 0.16
                    ret = importe * 0.06 if aplicar_ret else 0

                    ConceptoFactura.objects.create(
                        factura=factura,
                        cantidad=cant,
                        unidad=uni,                # Guardamos la unidad del input
                        clave_prod_serv=c_sat,     # Guardamos la clave SAT del input
                        clave_unidad="H87",        # Puedes dejar H87 por defecto o agregar otro input hidden
                        descripcion=desc,
                        valor_unitario=val,
                        importe=importe,
                        iva_importe=iva,
                        iva_ret_importe=ret
                    )
                    
                    subtotal += importe
                    impuestos += iva
                    retenciones += ret

                # ... (El resto del código de guardar totales sigue igual) ...
                factura.subtotal = subtotal
                factura.impuestos_trasladados = impuestos
                factura.impuestos_retenidos = retenciones
                factura.monto_total = subtotal + impuestos - retenciones
                
                factura.estado = 'timbrado'
                factura.fecha_timbrado = timezone.now()
                factura.save()

                messages.success(request, f"Factura {factura.folio} creada exitosamente.")
                return redirect('detalle_factura_cliente', pk=factura.pk)

            except Exception as e:
                messages.error(request, f"Ocurrió un error al guardar: {e}")
                # Es recomendable imprimir el error en consola para depurar
                print(e)
        else:
            messages.error(request, "Formulario inválido.")
    
    else:
        form = NuevaFacturaLibreForm()

    return render(request, 'facturacion/crear_factura.html', {'form': form})

# views.py

@login_required
@transaction.atomic
def registrar_pago(request, factura_id):
    """
    Registra un pago INDIVIDUAL (botón en dashboard).
    Crea internamente un ComplementoPago (Encabezado) y un PagoDoctoRelacionado (Detalle).
    """
    factura = get_object_or_404(Factura, pk=factura_id)
    
    if factura.metodo_pago != 'PPD':
        messages.warning(request, "Solo se pueden agregar complementos de pago a facturas PPD.")
        return redirect('detalle_factura_cliente', pk=factura.pk)

    # 1. Calcular Saldo Actual usando la nueva relación
    total_pagado = factura.pagos_recibidos.aggregate(suma=Sum('importe_pagado'))['suma'] or 0
    saldo_actual = factura.monto_total - total_pagado
    
    if saldo_actual <= 0:
        messages.warning(request, "Esta factura ya está pagada totalmente.")
        return redirect('detalle_factura_cliente', pk=factura.pk)

    if request.method == 'POST':
        form = PagoForm(request.POST, factura_obj=factura)
        
        if form.is_valid():
            # Datos del formulario (Monto Total, Fecha, etc.)
            datos_pago = form.cleaned_data
            monto_recibido = datos_pago['monto_total']

            try:
                # --- PASO A: Crear Encabezado (ComplementoPago) ---
                ultimo_folio = ComplementoPago.objects.order_by('-folio').first()
                nuevo_folio = (ultimo_folio.folio + 1) if ultimo_folio else 1
                
                complemento = form.save(commit=False)
                complemento.usuario = request.user
                complemento.receptor = factura.receptor  # El cliente es el receptor de la factura
                complemento.serie = 'CP'
                complemento.folio = nuevo_folio
                complemento.save()

                # --- PASO B: Crear Detalle (PagoDoctoRelacionado) ---
                # Cálculos de alta precisión
                saldo_ant_dec = Decimal(str(saldo_actual)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                imp_pagado_dec = Decimal(str(monto_recibido)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                
                saldo_ins_calc = saldo_ant_dec - imp_pagado_dec
                if saldo_ins_calc < 0: saldo_ins_calc = Decimal('0.00')

                # Calcular número de parcialidad
                num_parcialidad = factura.pagos_recibidos.count() + 1

                PagoDoctoRelacionado.objects.create(
                    complemento=complemento,
                    factura=factura,
                    numero_parcialidad=num_parcialidad,
                    saldo_anterior=saldo_ant_dec,
                    importe_pagado=imp_pagado_dec,
                    saldo_insoluto=saldo_ins_calc
                )

                # --- PASO C: Actualizar Estado Factura ---
                if saldo_ins_calc <= 0:
                    factura.estado = 'pagada'
                    factura.save()

                messages.success(request, f"Pago registrado correctamente (CP-{nuevo_folio}).")
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
@transaction.atomic
def nuevo_complemento_pago(request):
    """
    Genera un Complemento de Pago (REP) que puede pagar múltiples facturas.
    """
    # Obtenemos facturas pendientes para mostrar si se selecciona un cliente
    facturas_pendientes = []
    cliente_id = request.GET.get('cliente_id') # Para recargar la página con datos
    
    if cliente_id:
        facturas_pendientes = Factura.objects.filter(
            receptor_id=cliente_id,
            metodo_pago='PPD',
            estado__in=['timbrado', 'pendiente'] # Solo vigentes
        ).exclude(estado='pagada').order_by('fecha_emision')

        # Calculamos saldo real actual para cada factura
        for f in facturas_pendientes:
            pagado = f.pagos_recibidos.aggregate(suma=Sum('importe_pagado'))['suma'] or 0
            f.saldo_pendiente = f.monto_total - pagado

    if request.method == 'POST':
        form = ComplementoPagoCabeceraForm(request.POST)
        if form.is_valid():
            try:
                data = form.cleaned_data
                receptor = data['cliente'] # Viene del select
                
                # 1. Crear Encabezado (ComplementoPago)
                ultimo_folio = ComplementoPago.objects.order_by('-folio').first()
                nuevo_folio = (ultimo_folio.folio + 1) if ultimo_folio else 1
                
                complemento = form.save(commit=False)
                complemento.usuario = request.user
                complemento.receptor = receptor
                complemento.folio = nuevo_folio
                complemento.serie = 'CP'
                complemento.save()

                # 2. Procesar Facturas Seleccionadas
                facturas_ids = request.POST.getlist('facturas_seleccionadas')
                total_aplicado = Decimal('0.00')

                for f_id in facturas_ids:
                    monto_a_pagar = Decimal(request.POST.get(f'pago_factura_{f_id}', '0'))
                    
                    if monto_a_pagar > 0:
                        factura = Factura.objects.get(id=f_id)
                        
                        # Cálculos de saldos
                        historial_pagos = factura.pagos_recibidos.aggregate(suma=Sum('importe_pagado'))['suma'] or Decimal('0')
                        saldo_ant = factura.monto_total - historial_pagos
                        saldo_ins = saldo_ant - monto_a_pagar
                        
                        # Validar parcialidad
                        parcialidad = factura.pagos_recibidos.count() + 1
                        
                        # Crear Relación
                        PagoDoctoRelacionado.objects.create(
                            complemento=complemento,
                            factura=factura,
                            numero_parcialidad=parcialidad,
                            saldo_anterior=saldo_ant,
                            importe_pagado=monto_a_pagar,
                            saldo_insoluto=saldo_ins
                        )
                        
                        # Actualizar estado factura si se liquida
                        if saldo_ins <= 0.01: # Margen de error 1 centavo
                            factura.estado = 'pagada'
                            factura.save()
                        
                        total_aplicado += monto_a_pagar

                # Validar que no se asigne más dinero del recibido
                if total_aplicado > complemento.monto_total:
                    raise Exception("El total aplicado a las facturas supera el monto recibido.")
                
                messages.success(request, f"Complemento CP-{nuevo_folio} generado exitosamente.")
                return redirect('dashboard_facturacion')

            except Exception as e:
                messages.error(request, f"Error al guardar: {str(e)}")
    else:
        form = ComplementoPagoCabeceraForm()
        if cliente_id:
            form.fields['cliente'].initial = cliente_id

    return render(request, 'facturacion/nuevo_complemento.html', {
        'form': form,
        'facturas': facturas_pendientes,
        'cliente_seleccionado': int(cliente_id) if cliente_id else None
    })