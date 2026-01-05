import requests
import json
import sys

# --- CONFIGURACIÓN ---
# Tu llave de pruebas (la que ya funciona)
API_KEY = 'sk_test_5d8ab70a_1385_43d9_9387_33504b568558' 
TENANT_ID = 'f69b8c04-9872-488a-92ce-fc741c728a9d'
PERSON_ID = '3b09d87a-f42c-4122-986e-ba23e18f6f4d' # Tu usuario con saldo

BASE_URL = 'https://test.fiscalapi.com/api/v4'

# --- CERTIFICADOS NUEVOS (Extraídos de tu examples.py) ---
# Serial: ...3446 (Más reciente que el 3293)
CER_BASE64 = "MIIFgDCCA2igAwIBAgIUMzAwMDEwMDAwMDA1MDAwMDM0NDYwDQYJKoZIhvcNAQELBQAwggErMQ8wDQYDVQQDDAZBQyBVQVQxLjAsBgNVBAoMJVNFUlZJQ0lPIERFIEFETUlOSVNUUkFDSU9OIFRSSUJVVEFSSUExGjAYBgNVBAsMEVNBVC1JRVMgQXV0aG9yaXR5MSgwJgYJKoZIhvcNAQkBFhlvc2Nhci5tYXJ0aW5lekBzYXQuZ29iLm14MR0wGwYDVQQJDBQzcmEgY2VycmFkYSBkZSBjYWxpejEOMAwGA1UEEQwFMDYzNzAxCzAJBgNVBAYTAk1YMRkwFwYDVQQIDBBDSVVEQUQgREUgTUVYSUNPMREwDwYDVQQHDAhDT1lPQUNBTjERMA8GA1UELRMIMi41LjQuNDUxJTAjBgkqhkiG9w0BCQITFnJlc3BvbnNhYmxlOiBBQ0RNQS1TQVQwHhcNMjMwNTE4MTQzNTM3WhcNMjcwNTE4MTQzNTM3WjCBpzEdMBsGA1UEAxMUS0FSTEEgRlVFTlRFIE5PTEFTQ08xHTAbBgNVBCkTFEtBUkxBIEZVRU5URSBOT0xBU0NPMR0wGwYDVQQKExRLQVJMQSBGVUVOVEUgTk9MQVNDTzEWMBQGA1UELRMNRlVOSzY3MTIyOFBINjEbMBkGA1UEBRMSRlVOSzY3MTIyOE1DTE5MUjA1MRMwEQYDVQQLEwpTdWN1cnNhbCAxMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAhNXbTSqGX6+/3Urpemyy5vVG2IdP2v7v001+c4BoMxEDFDQ32cOFdDiRxy0Fq9aR+Ojrofq8VeftvN586iyA1A6a0QnA68i7JnQKI4uJy+u0qiixuHu6u3b3BhSpoaVHcUtqFWLLlzr0yBxfVLOqVna/1/tHbQJg9hx57mp97P0JmXO1WeIqi+Zqob/mVZh2lsPGdJ8iqgjYFaFn9QVOQ1Pq74o1PTqwfzqgJSfV0zOOlESDPWggaDAYE4VNyTBisOUjlNd0x7ppcTxSi3yenrJHqkq/pqJsRLKf6VJ/s9p6bsd2bj07hSDpjlDC2lB25eEfkEkeMkXoE7ErXQ5QCwIDAQABox0wGzAMBgNVHRMBAf8EAjAAMAsGA1UdDwQEAwIGwDANBgkqhkiG9w0BAQsFAAOCAgEAHwYpgbClHULXYhK4GNTgonvXh81oqfXwCSWAyDPiTYFDWVfWM9C4ApxMLyc0XvJte75Rla+bPC08oYN3OlhbbvP3twBL/w9SsfxvkbpFn2ZfGSTXZhyiq4vjmQHW1pnFvGelwgU4v3eeRE/MjoCnE7M/Q5thpuog6WGf7CbKERnWZn8QsUaJsZSEkg6Bv2jm69ye57ab5rrOUaeMlstTfdlaHAEkUgLX/NXq7RbGwv82hkHY5b2vYcXeh34tUMBL6os3OdRlooN9ZQGkVIISvxVZpSHkYC20DFNh1Bb0ovjfujlTcka81GnbUhFGZtRuoVQ1RVpMO8xtx3YKBLp4do3hPmnRCV5hCm43OIjYx9Ov2dqICV3AaNXSLV1dW39Bak/RBiIDGHzOIW2+VMPjvvypBjmPv/tmbqNHWPSAWOxTyMx6E1gFCZvi+5F+BgkdC3Lm7U0BU0NfvsXajZd8sXnIllvEMrikCLoI/yurvexNDcF1RW/FhMsoua0eerwczcNm66pGjHm05p9DR6lFeJZrtqeqZuojdxBWy4vH6ghyJaupergoX+nmdG3JYeRttCFF/ITI68TeCES5V3Y0C3psYAg1XxcGRLGd4chPo/4xwiLkijWtgt0/to5ljGBwfK7r62PHZfL1Dp+i7V3w7hmOlhbXzP+zhMZn1GCk7KY="

KEY_BASE64 = "MIIFDjBABgkqhkiG9w0BBQ0wMzAbBgkqhkiG9w0BBQwwDgQIAgEAAoIBAQACAggAMBQGCCqGSIb3DQMHBAgwggS9AgEAMASCBMh4EHl7aNSCaMDA1VlRoXCZ5UUmqErAbucRBAKNQXH8t8gVCl/ItHMI2hMJ76QOECOqEi1Y89cDpegDvh/INXyMsXbzi87tfFzgq1O+9ID6aPWGg+bNGADXyXxDVdy7Nq/SCdoXvo66MTYwq8jyJeUHDHEGMVBcmZpD44VJCvLBxDcvByuevP4Wo2NKqJCwK+ecAdZc/8Rvd947SjbMHuS8BppfQWARVUqA5BLOkTAHNv6tEk/hncC7O2YOGSShart8fM8dokgGSyewHVFe08POuQ+WDHeVpvApH/SP29rwktSoiHRoL6dK+F2YeEB5SuFW9LQgYCutjapmUP/9TC3Byro9Li6UrvQHxNmgMFGQJSYjFdqlGjLibfuguLp7pueutbROoZaSxU8HqlfYxLkpJUxUwNI1ja/1t3wcivtWknVXBd13R06iVfU1HGe8Kb4u5il4a4yP4p7VT4RE3b1SBLJeG+BxHiE8gFaaKcX/Cl6JV14RPTvk/6VnAtEQ66qHJex21KKuiJo2JoOmDXVHmvGQlWXNjYgoPx28Xd5WsofL+n7HDR2Ku8XgwJw6IXBJGuoday9qWN9v/k7DGlNGB6Sm4gdVUmycMP6EGhB1vFTiDfOGQO42ywmcpKoMETPVQ5InYKE0xAOckgcminDgxWjtUHjBDPEKifEjYudPwKmR6Cf4ZdGvUWwY/zq9pPAC9bu423KeBCnSL8AQ4r5SVsW6XG0njamwfNjpegwh/YG7sS7sDtZ8gi7r6tZYjsOqZlCYU0j7QTBpuQn81Yof2nQRCFxhRJCeydmIA8+z0nXrcElk7NDPk4kYQS0VitJ2qeQYNENzGBglROkCl2y6GlxAG80IBtReCUp/xOSdlwDR0eim+SNkdStvmQM5IcWBuDKwGZc1A4v/UoLl7niV9fpl4X6bUX8lZzY4gidJOafoJ30VoY/lYGkrkEuz3GpbbT5v8fF3iXVRlEqhlpe8JSGu7Rd2cPcJSkQ1Cuj/QRhHPhFMF2KhTEf95c9ZBKI8H7SvBi7eLXfSW2Y0ve6vXBZKyjK9whgCU9iVOsJjqRXpAccaWOKi420CjmS0+uwj/Xr2wLZhPEjBA/G6Od30+eG9mICmbp/5wAGhK/ZxCT17ZETyFmOMo49jl9pxdKocJNuzMrLpSz7/g5Jwp8+y8Ck5YP7AX0R/dVA0t37DO7nAbQT5XVSYpMVh/yvpYJ9WR+tb8Yg1h2lERLR2fbuhQRcwmisZR2W3Sr2b7hX9MCMkMQw8y2fDJrzLrqKqkHcjvnI/TdzZW2MzeQDoBBb3fmgvjYg07l4kThS73wGX992w2Y+a1A2iirSmrYEm9dSh16JmXa8boGQAONQzQkHh7vpw0IBs9cnvqO1QLB1GtbBztUBXonA4TxMKLYZkVrrd2RhrYWMsDp7MpC4M0p/DA3E/qscYwq1OpwriewNdx6XXqMZbdUNqMP2viBY2VSGmNdHtVfbN/rnaeJetFGX7XgTVYD7wDq8TW9yseCK944jcT+y/o0YiT9j3OLQ2Ts0LDTQskpJSxRmXEQGy3NBDOYFTvRkcGJEQJItuol8NivJN1H9LoLIUAlAHBZxfHpUYx66YnP4PdTdMIWH+nxyekKPFfAT7olQ="

def actualizar_sellos():
    print(f"🔄 Actualizando sellos para el usuario {PERSON_ID}...")

    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': API_KEY,
        'X-TENANT-KEY': TENANT_ID
    }

    # 1. Obtenemos la persona
    try:
        # Nota: Usamos PUT directo con los taxCredentials en Base64
        # Según la documentación v4, se pueden enviar así en el objeto taxCredentials
        
        payload = {
            "id": PERSON_ID,
            # Forzamos los datos de prueba correctos
            "tin": "FUNK671228PH6", # RFC de PRUEBA NUEVO (Asociado a estos sellos)
            "legalName": "KARLA FUENTE NOLASCO", # Nombre asociado a estos sellos
            "taxRegimeCode": "621", # Incorporación Fiscal (compatible con prueba)
            "zipCode": "42501", # CP de prueba
            "taxCredentials": [
                {
                    "base64File": CER_BASE64,
                    "fileType": 0, # 0 = CER
                    "password": "12345678a"
                },
                {
                    "base64File": KEY_BASE64,
                    "fileType": 1, # 1 = KEY
                    "password": "12345678a"
                }
            ]
        }

        print("📡 Enviando nuevos certificados...")
        resp = requests.put(f"{BASE_URL}/people/{PERSON_ID}", json=payload, headers=headers)

        if resp.status_code == 200:
            print("\n✅ ¡CERTIFICADOS ACTUALIZADOS CON ÉXITO!")
            print("Ahora tu usuario tiene los sellos de 'KARLA FUENTE NOLASCO' (RFC: FUNK671228PH6)")
            print("Estos sellos SÍ están vigentes en el entorno de pruebas.")
        else:
            print(f"\n❌ Error al actualizar: {resp.status_code}")
            print(resp.text)

    except Exception as e:
        print(f"Error crítico: {e}")

if __name__ == '__main__':
    actualizar_sellos()