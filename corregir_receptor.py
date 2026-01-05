import requests

# CONFIGURACIÓN (Tus credenciales reales)
BASE_URL = "https://test.fiscalapi.com/api/v4/people"
API_KEY = "sk_test_ecc5cd95_acae_44ef_9bcb_05372d909482"
TENANT_KEY = "6b1d48f4-f36a-468f-a411-8addac954c24"

headers = {
    'X-API-KEY': API_KEY,
    'X-TENANT-KEY': TENANT_KEY,
    'Content-Type': 'application/json'
}

def corregir_receptor_remoto():
    print(f"🔍 1. Buscando el ID para el RFC genérico XAXX010101000...")
    
    try:
        # Buscamos la persona en tu cuenta de FiscalAPI
        r = requests.get(f"{BASE_URL}?tin=XAXX010101000", headers=headers)
        
        if r.status_code != 200:
            print(f"❌ Error al conectar con FiscalAPI: {r.status_code} {r.text}")
            return

        items = r.json().get('data', {}).get('items', [])
        
        if not items:
            print("❌ No se encontró el receptor genérico en tu cuenta. Intenta timbrar primero para que se cree.")
            return

        person_id = items[0]['id']
        print(f"✅ ID Encontrado: {person_id}")
        
        # 2. Actualizar al régimen 616
        print(f"🛠️ 2. Actualizando datos a: Régimen 616 y Nombre 'PUBLICO EN GENERAL'...")
        payload = {
            "id": person_id,
            "legalName": "PUBLICO EN GENERAL",
            "tin": "XAXX010101000",
            "satTaxRegimeId": "616",  # Requisito CFDI 4.0 para Público en General
            "zipCode": "06370"
        }
        
        # Usamos PUT para actualizar el registro existente
        r_put = requests.put(f"{BASE_URL}/{person_id}", json=payload, headers=headers)
        
        if r_put.status_code == 200:
            print("🎉 ¡ÉXITO! Receptor actualizado correctamente en FiscalAPI.")
        else:
            print(f"❌ Error al actualizar en el servidor: {r_put.text}")

    except Exception as e:
        print(f"❌ Error de Python: {str(e)}")

if __name__ == "__main__":
    corregir_receptor_remoto()