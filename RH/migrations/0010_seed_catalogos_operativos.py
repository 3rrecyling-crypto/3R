"""
Data migration: Seed initial data for TipoViaje, TipoCarga and DivisionOperativa.
This ensures these catalog tables are populated on every environment (local and production).
"""
from django.db import migrations


TIPOS_VIAJE = [
    "Local",
    "Foraneo",
    "Mixto",
]

TIPOS_CARGA = [
    "Seca",
    "Refrigerada",
    "Congelada",
]

DIVISIONES_OPERATIVAS = [
    "Walmart",
    "Autozone",
    "Bodega Aurrera",
    "Bafar",
    "Doña Tota",
    "Sam's Club",
]


def seed_catalogos(apps, schema_editor):
    TipoViaje = apps.get_model("RH", "TipoViaje")
    TipoCarga = apps.get_model("RH", "TipoCarga")
    DivisionOperativa = apps.get_model("RH", "DivisionOperativa")

    for nombre in TIPOS_VIAJE:
        TipoViaje.objects.get_or_create(nombre=nombre)

    for nombre in TIPOS_CARGA:
        TipoCarga.objects.get_or_create(nombre=nombre)

    for nombre in DIVISIONES_OPERATIVAS:
        DivisionOperativa.objects.get_or_create(nombre=nombre)


def reverse_seed(apps, schema_editor):
    # Reversible: only delete what we created if they have no related employees
    TipoViaje = apps.get_model("RH", "TipoViaje")
    TipoCarga = apps.get_model("RH", "TipoCarga")
    DivisionOperativa = apps.get_model("RH", "DivisionOperativa")

    TipoViaje.objects.filter(nombre__in=TIPOS_VIAJE).delete()
    TipoCarga.objects.filter(nombre__in=TIPOS_CARGA).delete()
    DivisionOperativa.objects.filter(nombre__in=DIVISIONES_OPERATIVAS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("RH", "0009_alter_vacacion_tipo_vacacion"),
    ]

    operations = [
        migrations.RunPython(seed_catalogos, reverse_seed),
    ]
