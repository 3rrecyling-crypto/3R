"""
Data migration: agrega las divisiones operativas reales del sistema actual
(Migmar, Marco Morales, Chihuahua). Las divisiones del proyecto antiguo
(Walmart, Autozone, Bafar, Doña Tota, Sam's Club, Bodega Aurrera) se quedan
en la tabla por compatibilidad de datos históricos, pero se filtran en los
endpoints `api_rh_divisiones` y `api_rh_empleados` mediante una whitelist.
"""
from django.db import migrations


# Nombres exactos como deben mostrarse en la UI.
# Coinciden con `Empleado.EMPRESA_CHOICES` ya existentes.
DIVISIONES_SISTEMA = [
    "Migmar",
    "Marco Morales",
    "Chihuahua",
]


def seed_divisiones_sistema(apps, schema_editor):
    DivisionOperativa = apps.get_model("RH", "DivisionOperativa")
    for nombre in DIVISIONES_SISTEMA:
        DivisionOperativa.objects.get_or_create(nombre=nombre)


def reverse_seed(apps, schema_editor):
    # No-op: no borramos las divisiones porque pueden tener empleados
    # asignados. La whitelist en código se encarga de filtrarlas si hace falta.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('RH', '0012_empleado_lugar'),
    ]

    operations = [
        migrations.RunPython(seed_divisiones_sistema, reverse_seed),
    ]
