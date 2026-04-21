import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'r3_recycling.settings') # Ajusta si es necesario
django.setup()

from fiscalapi.models.fiscalapi_models import ItemTax

print("\n🔍 CAMPOS REALES DE ItemTax:")
try:
    # Intenta obtener los campos (Pydantic v1 o v2)
    campos = ItemTax.model_fields.keys() if hasattr(ItemTax, 'model_fields') else ItemTax.__fields__.keys()
    for campo in campos:
        print(f" 👉 {campo}")
except Exception as e:
    print(f"Error inspeccionando: {e}")
    # Fallback: imprimir dict
    print(ItemTax.__dict__)