import requests
from django.utils import timezone

# === CONFIGURACIÓN DE CONEXIÓN ACTUALIZADA ===
BASE_URL = "https://test.fiscalapi.com/api/v4/invoices/income"
API_KEY = "sk_test_4d2423ab_2305_4b06_a801_9aed2a1ad926" # Nueva llave proporcionada
TENANT_KEY = "6b1d48f4-f36a-468f-a411-8addac954c24"

# IDs DE REFERENCIA EN EL SERVIDOR (Validados anteriormente)
ISSUER_ID = "aff82d34-7e56-4369-bd9c-25ad56c3151a"
CER_ID = "2e24ef06-a8bf-4cf5-8a2e-d39c797d0e36"
KEY_ID = "2757c6e2-43ad-405f-9323-50c51fdaa4ab"

def timbrar_factura_api(factura_obj):
    items_payload = []
    for c in factura_obj.conceptos.all():
        # Nodo de impuestos (IVA 16% si no es el código genérico 01010101)
        tax_obj = "02" if c.clave_prod_serv != '01010101' else "01"
        items_payload.append({
            "itemCode": c.clave_prod_serv,
            "itemSku": c.clave_prod_serv,
            "quantity": float(c.cantidad),
            "unitOfMeasurementCode": c.clave_unidad,
            "description": c.descripcion,
            "unitPrice": float(c.valor_unitario),
            "taxObjectCode": tax_obj,
            "itemTaxes": [{
                "taxCode": "002", "taxTypeCode": "Tasa", "taxRate": 0.16, "taxFlagCode": "T"
            }] if tax_obj == "02" else []
        })

    payload = {
        "versionCode": "4.0",
        "series": factura_obj.serie or "T",
        "date": timezone.localtime(factura_obj.fecha_emision).strftime('%Y-%m-%dT%H:%M:%S'),
        "paymentFormCode": factura_obj.forma_pago or "01",
        "paymentMethodCode": factura_obj.metodo_pago or "PUE",
        "currencyCode": "MXN",
        "typeCode": "I",
        "expeditionZipCode": "06370",
        "exchangeRate": 1,
        "exportCode": "01",
        "issuer": { 
            "id": ISSUER_ID,
            "taxCredentials": [
                {"id": CER_ID},
                {"id": KEY_ID}
            ]
        },
        "recipient": {
            "tin": factura_obj.receptor.rfc,
            "legalName": factura_obj.receptor.razon_social,
            "zipCode": factura_obj.receptor.codigo_postal,
            "taxRegimeCode": factura_obj.receptor.regimen_fiscal,
            "cfdiUseCode": factura_obj.uso_cfdi,
            "email": "facturacion@3r_recycling.com"
        },
        "items": items_payload
    }

    # Requisito CFDI 4.0 para Público en General
    if factura_obj.receptor.rfc == "XAXX010101000":
        fecha = timezone.localtime(factura_obj.fecha_emision)
        payload["globalInformation"] = {
            "periodicityCode": "01", # Diario
            "monthCode": fecha.strftime('%m'),
            "year": int(fecha.strftime('%Y'))
        }

    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': API_KEY,
        'X-TENANT-KEY': TENANT_KEY,
        'X-TIME-ZONE': 'America/Mexico_City'
    }

    try:
        response = requests.post(BASE_URL, headers=headers, json=payload)
        
        # Validación de respuesta técnica
        if response.status_code == 401:
            return {'success': False, 'error': "ERROR 401: Acceso denegado. Llave o Tenant incorrectos."}

        data = response.json()

        if response.status_code == 200 and data.get('succeeded'):
            res_data = data.get('data', {})
            return {
                'success': True, 
                'data': {
                    'uuid': res_data.get('uuid'), 
                    'xml': res_data.get('xml') or (res_data.get('responses', [{}])[0].get('invoiceBase64'))
                }
            }
        else:
            # Imprimimos el error del SAT para corregir datos si es necesario
            print(f"❌ DETALLE TÉCNICO: {data}")
            return {'success': False, 'error': data.get('message', 'Error en timbrado')}

    except Exception as e:
        return {'success': False, 'error': str(e)}