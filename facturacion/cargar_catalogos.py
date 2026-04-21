# cargar_catalogos.py
import os
import django

# Configuración para correr script standalone
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'r3_recycling.settings')
django.setup()

from facturacion.models import CatalogoSAT

print("⏳ Cargando catálogos SAT...")

# --- 1. CLAVES DE UNIDAD (Las más usadas) ---
unidades = [
    ('H87', 'Pieza'),
    ('KGM', 'Kilogramo'),
    ('GRM', 'Gramo'),
    ('LTR', 'Litro'),
    ('MTR', 'Metro'),
    ('MTK', 'Metro cuadrado'),
    ('MTQ', 'Metro cúbico'),
    ('E48', 'Unidad de servicio'),
    ('DAY', 'Día'),
    ('HUR', 'Hora'),
    ('XUN', 'Unidad'),
]

for clave, desc in unidades:
    CatalogoSAT.objects.get_or_create(
        tipo='ClaveUnidad', clave=clave, 
        defaults={'descripcion': desc}
    )

# --- 2. CLAVES PROD/SERV (Reciclaje y General) ---
productos = [
    ('01010101', 'No existe en el catálogo'),
    ('11141600', 'Desechos no metálicos (Chatarra)'),
    ('11101500', 'Desperdicios metálicos'),
    ('11191600', 'Desechos de plástico'),
    ('11141500', 'Cartón reciclado'),
    ('76121501', 'Servicio de recolección de basura'),
    ('78101800', 'Transporte de carga por carretera'),
    ('80141600', 'Servicios de comercialización y distribución'),
    ('84111506', 'Servicios de facturación'),
    ('43232600', 'Software de gestión'),
]

for clave, desc in productos:
    CatalogoSAT.objects.get_or_create(
        tipo='ClaveProdServ', clave=clave, 
        defaults={'descripcion': desc}
    )

print("✅ ¡Catálogos actualizados! Ahora el buscador funcionará.")