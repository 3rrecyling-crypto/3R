import requests
import json

# --- CONFIGURACIÓN ---
# Tu llave actual (la que usamos para tener permiso de lectura)
LLAVE_ACTUAL = 'sk_test_5d8ab70a_1385_43d9_9387_33504b568558' 

# El ID del usuario con los 554 Timbres
ID_BUSCADO = '3b09d87a-f42c-4122-986e-ba23e18f6f4d'

# URL para listar llaves (API v4)
URL_API = 'https://test.fiscalapi.com/api/v4/apikeys?pageSize=50'

def buscar_llave():
    print(f"🕵️  Buscando llaves existentes para el usuario: {ID_BUSCADO}...")
    
    headers = {
        'X-API-KEY': LLAVE_ACTUAL,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(URL_API, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get('data', {}).get('items', [])
            
            encontrada = False
            print(f"📋 Se encontraron {len(items)} llaves en total en la cuenta.")

            for k in items:
                # Comparamos si esta llave pertenece al usuario rico (3b09...)
                if k.get('personId') == ID_BUSCADO:
                    status = k.get('apiKeyStatus')
                    estado_texto = "ACTIVA" if status == 1 else "INACTIVA"
                    
                    print("\n" + "✅"*20)
                    print(f" ¡ENCONTRADA! ({estado_texto})")
                    print(f" 🔑 LLAVE: {k.get('apiKeyValue')}")
                    print(f" 👤 PersonID: {k.get('personId')}")
                    print(f" 📝 Descripción: {k.get('description')}")
                    print("✅"*20)
                    encontrada = True
            
            if not encontrada:
                print("\n⚠️ No se encontró ninguna llave asociada a ese ID.")
                print("Tendrás que crearla manualmente en el portal web.")
                
        else:
            print(f"\n❌ Error HTTP {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"\n💀 Error de conexión: {str(e)}")

if __name__ == '__main__':
    buscar_llave()