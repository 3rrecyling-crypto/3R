import os
import sys
import django
import requests
import json
from datetime import datetime

# --- CONFIGURACIÓN DJANGO ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'r3_recycling.settings')
django.setup()

from django.conf import settings

def crear_factura_ingreso():
    print("🚀 INICIANDO PRUEBA DE TIMBRADO (CFDI 4.0 - PUBLICO GENERAL)...")

    # DATOS CLAVE
    # Nota: Asegúrate de que API_KEY sea la correcta (la sk_test...)
    API_KEY = getattr(settings, 'FISCALAPI_KEY', 'sk_test_5d8ab70a_1385_43d9_9387_33504b568558') 
    TENANT_ID = 'f69b8c04-9872-488a-92ce-fc741c728a9d' 
    PERSON_ID = '3b09d87a-f42c-4122-986e-ba23e18f6f4d' 
    
    base_url = getattr(settings, 'FISCALAPI_URL', 'https://test.fiscalapi.com/api/v4')
    if base_url.endswith('/'): base_url = base_url[:-1]
    url = f"{base_url}/invoices/income"

    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': API_KEY,
        'X-TENANT-KEY': TENANT_ID 
    }

    mes_actual = datetime.now().strftime("%m")
    anio_actual = datetime.now().year

    payload = {
        "versionCode": "4.0",
        "series": "TEST",
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "paymentFormCode": "01",
        "currencyCode": "MXN",
        "typeCode": "I",
        "expeditionZipCode": "06370",
        "paymentMethodCode": "PUE",
        "exportCode": "01",
        "exchangeRate": 1,
        
        "globalInformation": {
            "periodicityCode": "01", 
            "monthCode": mes_actual, 
            "year": anio_actual
        },

        "issuer": {
            "id": PERSON_ID 
        },

        "recipient": {
            "tin": "XAXX010101000",
            "legalName": "PUBLICO EN GENERAL",
            "zipCode": "06370",
            "taxRegimeCode": "616",
            "cfdiUseCode": "S01",
            "email": "prueba@ejemplo.com"
        },

        "items": [
            {
                "itemCode": "84111506",
                "quantity": 1,
                "unitOfMeasurementCode": "E48",
                "description": "VENTA DEL DIA - PRUEBA DECIMALES",
                "unitPrice": 100.00,
                "discount": 0,
                "taxObjectCode": "02",
                "itemSku": "SKU-01", 
                "itemTaxes": [
                    {
                        "taxCode": "002",
                        "taxTypeCode": "Tasa",
                        # --- CORRECCIÓN AQUÍ ---
                        # Enviamos como STRING para preservar los 6 decimales exactos
                        "taxRate": "0.160000", 
                        # -----------------------
                        "taxFlagCode": "T"
                    }
                ]
            }
        ]
    }

    try:
        print("⏳ Enviando a FiscalAPI...")
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('succeeded'):
                data = result.get('data', {})
                print("\n" + "🎉"*10)
                print(" ¡TIMBRADO EXITOSO!")
                print("🎉"*10)
                print(f"UUID: {data.get('uuid')}")
                print(f"Folio: {data.get('series')}-{data.get('number')}")
                print("\n✅ ¡Felicidades! Ya puedes implementar esto en tu views.py.")
            else:
                print("\n❌ Error Lógico:")
                print(json.dumps(result, indent=2))
        else:
            print(f"\n❌ Error HTTP {response.status_code}:")
            print(response.text)

    except Exception as e:
        print(f"Error de conexión: {e}")

if __name__ == "__main__":
    crear_factura_ingreso()