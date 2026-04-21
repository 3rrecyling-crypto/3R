from decimal import Decimal
import requests
from django.utils import timezone
import os
# =========================
# FISCALAPI SDK
# =========================
from fiscalapi.models.common_models import FiscalApiSettings
from fiscalapi.models.fiscalapi_models import (
    Invoice,
    InvoiceIssuer,
    InvoiceItem,
    InvoiceRecipient,
    ItemTax,CancelInvoiceRequest,RelatedInvoice,PaidInvoice,PaidInvoiceTax,InvoicePayment
)
from fiscalapi.services.fiscalapi_client import FiscalApiClient

# =========================
# CREDENCIALES
# =========================
API_URL = os.getenv("FISCALAPI_URL")

API_KEY = os.getenv("FISCALAPI_KEY")

TENANT_ID = os.getenv("FISCALAPI_TENANT")

ISSUER_ID = os.getenv("FISCALAPI_ISSUER")
# =========================
# OBJETO AUXILIAR
# =========================
class FiscalObject:
    """
    Permite definir atributos en CamelCase (para el JSON de la API)
    pero responde a llamadas en snake_case (para que el SDK no falle).
    """
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    
    def __getattr__(self, name):
        # Traduce llamadas del SDK (ej. type_code -> typeCode)
        if '_' in name:
            components = name.split('_')
            camel_name = components[0] + ''.join(x.title() for x in components[1:])
            if camel_name in self.__dict__:
                return self.__dict__[camel_name]
        return None # Evita crash si el atributo no existe

# =========================
# CLIENTE
# =========================
def get_fiscal_client():
    settings = FiscalApiSettings(
        api_url=API_URL,
        api_key=API_KEY,
        tenant=TENANT_ID
    )
    return FiscalApiClient(settings=settings)

# =========================
# TIMBRAR FACTURA CFDI 4.0
# =========================
def timbrar_factura_api(factura_obj):
    """
    Timbra factura CFDI 4.0.
    Usa la configuración exacta de impuestos guardada en ConceptoFactura.
    """
    client = get_fiscal_client()
    
    # 0. Sincronizar Cliente
    try:
        sincronizar_cliente_api(factura_obj.receptor)
    except Exception as e:
        print(f"Error sync cliente: {e}")

    cp_emisor = factura_obj.emisor.codigo_postal 
    items_sdk = []

    # ==========================================
    # 1. CONCEPTOS (CON LÓGICA DE IMPUESTOS MIXTA)
    # ==========================================
    for concepto in factura_obj.conceptos.all():
        tax_object_code = getattr(concepto, 'objeto_impuesto', '02')
        if not tax_object_code: tax_object_code = '02'

        sku_val = f"SKU-{concepto.id}" 
        taxes_list = []

        # Si es objeto de impuesto ('02'), agregamos el desglose
        if tax_object_code == "02":
            
            # --- A) TRASLADOS (IVA, IEPS) ---
            # Leemos los campos nuevos. Si no existen (facturas viejas), usamos defaults.
            clave_tras = getattr(concepto, 'traslado_impuesto_clave', '002') 
            tasa_tras = getattr(concepto, 'traslado_tasa', Decimal("0.160000"))
            monto_tras = concepto.iva_importe

            # Agregamos si el monto > 0 O si es tasa 0% explícita (Monto 0 pero Tasa 0)
            # Nota: Si tasa_tras es 0 y monto es 0, sí debe enviarse como Tasa 0.000000
            if monto_tras > 0 or (clave_tras == '002' and tasa_tras == 0): 
                taxes_list.append(ItemTax(
                    tax_code=clave_tras,      # 002=IVA, 003=IEPS (Dinámico)
                    tax_type_code="Tasa",
                    tax_rate=tasa_tras,       # Tasa exacta (0.160000, 0.000000, etc.)
                    tax_flag_code="T",        # T = Traslado
                    base=concepto.importe,    
                    amount=monto_tras         
                ))

            # --- B) RETENCIONES (IVA, ISR) ---
            clave_ret = getattr(concepto, 'retencion_impuesto_clave', '002')
            tasa_ret = getattr(concepto, 'retencion_tasa', Decimal("0.000000"))
            monto_ret = concepto.iva_ret_importe

            if monto_ret > 0:
                taxes_list.append(ItemTax(
                    tax_code=clave_ret,       # 001=ISR, 002=IVA (Dinámico)
                    tax_type_code="Tasa",
                    tax_rate=tasa_ret,        # Ej. 0.012500, 0.106666
                    tax_flag_code="R",        # R = Retención
                    base=concepto.importe,
                    amount=monto_ret
                ))

        items_sdk.append(
            InvoiceItem(
                item_code=concepto.clave_prod_serv,
                description=concepto.descripcion,
                unit_of_measurement_code=concepto.clave_unidad,
                quantity=Decimal(str(concepto.cantidad)),
                unit_price=Decimal(str(concepto.valor_unitario)),
                tax_object_code=tax_object_code,
                item_sku=sku_val,
                item_taxes=taxes_list if taxes_list else None 
            )
        )

    # ==========================================
    # 2. RECEPTOR
    # ==========================================
    receptor = factura_obj.receptor
    rfc = receptor.rfc.upper().strip()
    uso_cfdi = factura_obj.uso_cfdi
    regimen = receptor.regimen_fiscal
    cp_receptor = receptor.codigo_postal
    global_info = None

    # Caso Público en General
    if rfc == "XAXX010101000":
        uso_cfdi = "S01"
        regimen = "616"
        cp_receptor = cp_emisor
        hoy = timezone.now()
        global_info = {
            "periodicity_code": "01",
            "month_code": hoy.strftime("%m"),
            "year": int(hoy.strftime("%Y"))
        }
    # Caso Extranjero
    elif rfc == "XEXX010101000":
        uso_cfdi = "S01"
        regimen = "616" 
        cp_receptor = cp_emisor 

    recipient_sdk = InvoiceRecipient(
        tin=rfc,
        legal_name=receptor.razon_social,
        zip_code=cp_receptor,
        tax_regime_code=regimen,
        cfdi_use_code=uso_cfdi
    )

    # ==========================================
    # 3. CABECERA Y TIMBRADO
    # ==========================================
    tipo_comprobante = getattr(factura_obj, 'tipo_comprobante', 'I')
    serie_defecto = factura_obj.serie or ("NC" if tipo_comprobante == 'E' else "F")
    
    metodo_pago_sat = factura_obj.metodo_pago
    if tipo_comprobante == 'E': metodo_pago_sat = "PUE"

    # Relacionados
    related_invoices_list = None
    uuid_rel = getattr(factura_obj, 'uuid_relacionado', None)
    if uuid_rel and len(uuid_rel) > 10:
        tipo_rel = getattr(factura_obj, 'tipo_relacion', None) or ("01" if tipo_comprobante == 'E' else "04")
        related_invoices_list = [RelatedInvoice(relationship_type_code=tipo_rel, uuid=uuid_rel)]

    fecha_iso = timezone.localtime(factura_obj.fecha_emision).strftime("%Y-%m-%dT%H:%M:%S")
    tc_val = 1 if factura_obj.moneda == "MXN" else float(factura_obj.tipo_cambio)
    
    # ID Emisor Dinámico
    issuer_id_final = getattr(factura_obj.emisor, 'id_fiscalapi', None) or ISSUER_ID

    invoice_sdk = Invoice(
        version_code="4.0",
        series=serie_defecto,
        date=fecha_iso,
        payment_form_code=factura_obj.forma_pago,
        payment_method_code=metodo_pago_sat,
        payment_conditions="Contado",
        currency_code=factura_obj.moneda,
        exchange_rate=tc_val,
        type_code=tipo_comprobante,
        expedition_zip_code=cp_emisor,
        export_code="01",
        issuer=InvoiceIssuer(id=issuer_id_final),
        recipient=recipient_sdk,
        items=items_sdk,
        global_information=global_info,
        related_invoices=related_invoices_list
    )

    try:
        print(f"🚀 Enviando documento {factura_obj.folio}...")
        response = client.invoices.create(invoice_sdk)
        
        if response.succeeded:
            data = response.data
            xml_b64 = None
            if hasattr(data, 'responses') and data.responses:
                xml_b64 = getattr(data.responses[0], 'invoice_base64', None)
            if not xml_b64:
                 xml_b64 = getattr(data, 'xml', None) or getattr(data, 'invoice_base64', None)

            return {
                "success": True,
                "data": { "uuid": data.uuid, "xml": xml_b64, "id": data.id }
            }
        
        detail = getattr(response, 'data', str(response.message))
        return {"success": False, "error": f"{response.message} | {detail}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
# =========================
# COMPLEMENTO DE PAGO
# =========================
# Asegúrate de importar estos modelos del SDK al inicio de tu archivo

# services.py

def timbrar_pago_api(pago_obj):
    client = get_fiscal_client()
    
    # ---------------------------------------------------------
    # A. RECUPERAR DATOS DEL EMISOR (LUGAR EXPEDICIÓN)
    # ---------------------------------------------------------
    cp_emisor = "26015" # Default por seguridad
    try:
        from .models import DatosFiscales
        emisor = DatosFiscales.objects.filter(es_emisor=True).first()
        if emisor and emisor.codigo_postal:
            cp_emisor = emisor.codigo_postal
    except: pass

    # Sincronización básica del cliente
    try:
        sincronizar_cliente_api(pago_obj.receptor)
    except Exception as e:
        print(f"Advertencia Sync Cliente: {e}")

    # ---------------------------------------------------------
    # B. DOCUMENTOS RELACIONADOS (MATEMÁTICA PRECISA)
    # ---------------------------------------------------------
    paid_invoices_list = []
    total_monto_pago = Decimal("0.00")

    for d in pago_obj.documentos_relacionados.all():
        if not d.factura.folio_fiscal:
            return {"success": False, "error": f"Factura {d.factura.folio} sin UUID"}

        # 1. Decimales estrictos
        importe_pagado_dr = Decimal(str(d.importe_pagado)).quantize(Decimal("0.00"))
        saldo_anterior_dr = Decimal(str(d.saldo_anterior)).quantize(Decimal("0.00"))
        
        saldo_insoluto_dr = saldo_anterior_dr - importe_pagado_dr
        if saldo_insoluto_dr < 0: saldo_insoluto_dr = Decimal("0.00") 
        
        total_monto_pago += importe_pagado_dr

        # 2. Impuestos DR
        impuestos_dr_list = []
        factura_subtotal = Decimal(str(d.factura.subtotal or 0))
        factura_impuestos = Decimal(str(d.factura.impuestos_trasladados or 0))
        
        tiene_impuestos = factura_impuestos > 0 and factura_subtotal > 0
        objeto_imp_dr = "02" if tiene_impuestos else "01"
        
        if objeto_imp_dr == "02":
            # Cálculo de Tasa (Corrección 16% / 8%)
            raw_tasa = factura_impuestos / factura_subtotal
            
            if Decimal("0.15") <= raw_tasa <= Decimal("0.17"):
                tasa_calculada = Decimal("0.160000")
            elif Decimal("0.07") <= raw_tasa <= Decimal("0.09"): 
                tasa_calculada = Decimal("0.080000")
            else:
                tasa_calculada = raw_tasa.quantize(Decimal("0.000001"))
            
            divisor = Decimal("1.0") + tasa_calculada
            
            base_dr = (importe_pagado_dr / divisor).quantize(Decimal("0.000001"))
            iva_dr = (importe_pagado_dr - base_dr).quantize(Decimal("0.000001"))

            impuestos_dr_list.append(
                PaidInvoiceTax(
                    tax_code="002",
                    tax_type_code="Tasa",
                    tax_rate=tasa_calculada,    
                    tax_flag_code="T",
                    base=base_dr,
                    amount=iva_dr
                )
            )

        # 3. Construir PaidInvoice (usando model_construct)
        paid_invoices_list.append(
            PaidInvoice.model_construct(
                uuid=d.factura.folio_fiscal,
                series=d.factura.serie or "F",
                number=str(d.factura.folio),
                currency_code=d.factura.moneda,
                equivalency_dr=Decimal("1"),
                partiality_number=int(d.numero_parcialidad),
                previous_balance=saldo_anterior_dr,
                payment_amount=importe_pagado_dr,
                remaining_balance=saldo_insoluto_dr,
                sub_total=Decimal(str(d.factura.subtotal)).quantize(Decimal("0.00")), 
                tax_object_code=objeto_imp_dr,
                paid_invoice_taxes=impuestos_dr_list if impuestos_dr_list else None
            )
        )

    # ---------------------------------------------------------
    # C. PAGO (BYPASS DE VALIDACIÓN PYDANTIC PARA BANCOS)
    # ---------------------------------------------------------
    fecha_pago_fmt = pago_obj.fecha_pago.strftime("%Y-%m-%dT%H:%M:%S")

    # Extraemos valores bancarios
    op_num = pago_obj.num_operacion if pago_obj.num_operacion else None
    
    rfc_emisor_banco = getattr(pago_obj, 'rfc_banco_emisor', None) or None
    cta_emisor_banco = getattr(pago_obj, 'cuenta_emisor', None) or None
    rfc_receptor_banco = getattr(pago_obj, 'rfc_banco_receptor', None) or None
    cta_receptor_banco = getattr(pago_obj, 'cuenta_receptor', None) or None

    payment_sdk = InvoicePayment.model_construct(
        payment_date=fecha_pago_fmt,
        payment_form_code=pago_obj.forma_pago,
        currency_code="MXN",
        exchange_rate=Decimal("1"),
        amount=total_monto_pago,
        paid_invoices=paid_invoices_list,
        operation_number=op_num,
        source_bank_tin=rfc_emisor_banco,
        source_bank_account=cta_emisor_banco,
        target_bank_tin=rfc_receptor_banco,
        target_bank_account=cta_receptor_banco
    )

    # ---------------------------------------------------------
    # D. PREPARAR RECEPTOR
    # ---------------------------------------------------------
    rfc_receptor = pago_obj.receptor.rfc.strip().upper()
    cp_receptor = pago_obj.receptor.codigo_postal
    regimen_receptor = pago_obj.receptor.regimen_fiscal
    razon_social = pago_obj.receptor.razon_social

    if rfc_receptor in ["XAXX010101000", "XEXX010101000"]:
        cp_receptor = cp_emisor 
        regimen_receptor = "616"

    recipient_sdk = InvoiceRecipient(
        tin=rfc_receptor,
        legal_name=razon_social,
        zip_code=cp_receptor,
        tax_regime_code=regimen_receptor,
        cfdi_use_code="CP01"
    )

    # ---------------------------------------------------------
    # E. ESTRUCTURA FACTURA "P"
    # ---------------------------------------------------------
    item_zero = InvoiceItem(
        item_code="84111506", 
        quantity=Decimal("1"), 
        unit_of_measurement_code="ACT",
        description="Pago", 
        unit_price=Decimal("0"), 
        subtotal=Decimal("0"), 
        total=Decimal("0"), 
        tax_object_code="01"
    )

    invoice_pago = Invoice(
        version_code="4.0",
        series=pago_obj.serie,
        date=fecha_pago_fmt,
        currency_code="XXX", 
        type_code="P",
        expedition_zip_code=cp_emisor,
        export_code="01",
        sub_total=Decimal("0"),
        total=Decimal("0"),
        issuer=InvoiceIssuer(id=ISSUER_ID),
        recipient=recipient_sdk,
        items=[item_zero],
        payments=[payment_sdk]
    )

    # ---------------------------------------------------------
    # F. ENVÍO Y DESCARGA DE XML
    # ---------------------------------------------------------
    try:
        print(f"🚀 Enviando Pago {pago_obj.serie}-{pago_obj.folio}...")
        response = client.invoices.create(invoice_pago)
        
        if response.succeeded:
            data = response.data
            internal_id = data.id
            
            # 1. Intentamos obtener el XML de la respuesta inmediata
            xml_data = getattr(data, 'xml', None) or getattr(data, 'invoice_base64', None)
            if hasattr(data, 'responses') and data.responses:
                 xml_data = getattr(data.responses[0], 'invoice_base64', None) or xml_data
            
            # 2. SI FALLA: Lo descargamos explícitamente usando el ID Interno
            if not xml_data and internal_id:
                print(f"🔄 XML no recibido al instante. Descargando desde FiscalAPI con ID: {internal_id}...")
                # Llamamos a nuestra función de recuperación
                res_recuperacion = recuperar_cfdi_xml(internal_id)
                if res_recuperacion['success']:
                    xml_data = res_recuperacion['xml']
                    print("✅ XML descargado correctamente.")
                else:
                    print(f"⚠️ No se pudo descargar el XML: {res_recuperacion.get('error')}")

            return {
                "success": True, 
                "data": {
                    "uuid": data.uuid, 
                    "xml": xml_data, 
                    "id": internal_id
                }
            }
        
        error_detail = "Detalle no disponible"
        if hasattr(response, 'data'): error_detail = response.data
        elif hasattr(response, 'errors'): error_detail = response.errors
            
        print(f"❌ ERROR AL TIMBRAR: {response.message}")
        print(f"❌ DETALLE TÉCNICO: {error_detail}")
        
        return {"success": False, "error": f"SAT/PAC: {response.message} | {error_detail}"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Excepción Interna: {str(e)}"}
# =========================
def cancelar_cfdi_api(factura_db, motivo="02", sustitucion=None):
    """
    Cancela usando el ID interno de FiscalAPI.
    """
    client = get_fiscal_client()

    # 1. Aseguramos que usamos el ID interno (id_fiscalapi)
    # Si id_fiscalapi está vacío, intentamos con folio_fiscal
    invoice_id = factura_db.id_fiscalapi if factura_db.id_fiscalapi else factura_db.folio_fiscal

    if not invoice_id:
        return {"success": False, "error": "No se encontró el ID interno de la factura."}

    try:
        # 2. LIMPIEZA CRUCIAL: 
        # Si 'sustitucion' es una cadena vacía o no es motivo 01, DEBE ser None.
        # Si se envía "" la API responde "Something went wrong".
        uuid_remplazo = None
        if motivo == "01" and sustitucion and len(sustitucion) > 10:
            uuid_remplazo = sustitucion

        cancel_request = CancelInvoiceRequest(
            id=invoice_id,
            cancellation_reason_code=motivo,
            replacement_uuid=uuid_remplazo  # <--- Ahora es None si está vacío
        )

        print(f"📡 Enviando cancelación ID: {invoice_id} | Motivo: {motivo} | Sustituye: {uuid_remplazo}")
        resp = client.invoices.cancel(cancel_request)

        if resp.succeeded:
            return {"success": True, "message": resp.message}
        else:
            return {"success": False, "error": resp.message}

    except Exception as e:
        return {"success": False, "error": str(e)}

# =========================
# BUSCAR CATÁLOGOS SAT
# =========================
def sincronizar_cliente_api(receptor_db):
    """
    Sube o actualiza un cliente en FiscalAPI asegurando que los datos sean válidos.
    """
    if not receptor_db:
        return False

    # 1. Limpieza de Datos
    rfc_limpio = receptor_db.rfc.strip().upper()
    
    # --- CORRECCIÓN AQUÍ ---
    # Ignorar tanto Público en General (XAXX...) como Extranjeros (XEXX...)
    if rfc_limpio in ["XAXX010101000", "XEXX010101000"]:
        return True
    # -----------------------

    # El resto de la función sigue igual...
    regimen_limpio = receptor_db.regimen_fiscal
    if regimen_limpio and " " in regimen_limpio:
        regimen_limpio = regimen_limpio.split(" ")[0]
    
    zip_code = receptor_db.codigo_postal.strip() if receptor_db.codigo_postal else ""
    if len(zip_code) < 5:
        return False

    url = f"{API_URL}/api/v4/clients"
    headers = {
        "X-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "legal_name": receptor_db.razon_social.strip(),
        "tax_id": rfc_limpio,
        "tax_system": regimen_limpio,
        "email": receptor_db.email_contacto or "cliente@sinemail.com",
        "phone": "0000000000",
        "address": {
            "zip": zip_code,
            "street": getattr(receptor_db, 'direccion', 'Domicilio Conocido') or "Domicilio Conocido",
            "external_number": "S/N",
            "neighborhood": ".",
            "municipality": "."
        }
    }

    try:
        search_url = f"{url}?tax_id={rfc_limpio}"
        r_search = requests.get(search_url, headers=headers)
        
        client_id_api = None
        if r_search.status_code == 200:
            data = r_search.json()
            if isinstance(data, list) and len(data) > 0:
                client_id_api = data[0].get('id')
            elif isinstance(data, dict) and 'data' in data and len(data['data']) > 0:
                client_id_api = data['data'][0].get('id')

        if client_id_api:
            requests.put(f"{url}/{client_id_api}", json=payload, headers=headers)
        else:
            print(f"🆕 Dando de alta cliente {rfc_limpio} en FiscalAPI...")
            r_post = requests.post(url, json=payload, headers=headers)
            if r_post.status_code >= 400:
                print(f"❌ Error creando {rfc_limpio}: {r_post.text}")
                return False 

        return True

    except Exception as e:
        print(f"⚠️ Excepción en sincronización: {e}")
        return False
    
    
def buscar_en_fiscalapi(tipo, termino):
    if not termino or len(termino) < 3:
        return []

    catalogo = "SatProductCodes" if tipo == "ClaveProdServ" else "SatUnitCodes"
    url = f"{API_URL}/api/v4/catalogs/{catalogo}/search/{termino}"

    headers = {
        "X-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

    try:
        r = requests.get(url, headers=headers, timeout=5)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []
    
def recuperar_cfdi_xml(uuid_or_id):
    """
    Intenta recuperar el XML de una factura o pago desde FiscalAPI
    usando el UUID o el ID interno.
    """
    try:
        # Endpoint para obtener detalles de factura/pago
        url = f"{API_URL}/api/v4/invoices/{uuid_or_id}"
        headers = {
            "X-API-KEY": API_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # FiscalAPI a veces devuelve 'xml' (texto) o 'invoice_base64'
            xml_content = data.get('xml') or data.get('invoice_base64')
            
            # Si viene dentro de 'data' (estructura envolvente)
            if not xml_content and 'data' in data:
                 xml_content = data['data'].get('xml') or data['data'].get('invoice_base64')

            if xml_content:
                return {"success": True, "xml": xml_content}
            else:
                return {"success": False, "error": "La API respondió pero no contiene el XML."}
        else:
            return {"success": False, "error": f"Error API ({response.status_code}): {response.text}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}