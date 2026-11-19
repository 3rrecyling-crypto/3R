"""Catálogo inicial de Resultados: las cuentas y los renglones del Excel "Vista Resultados_fase1"
de dirección (noviembre 2026). Después se agregan, renombran o desactivan desde la pantalla."""
from django.db import migrations

CUENTAS = [
    '3R RECYCLING', 'ACEROS FDZ', 'BREMBO-ZIKLOA', 'CARRIER-ENVITA', 'LEAR', 'LGMG', 'MEDLINE', 'PROBOCA',
    'HUDSON', 'SEALED AIR', 'OTRAS VENTAS', 'TERNIUM', 'TRANE',
]

# (sección, nombre, moneda, resta)
CONCEPTOS = [
    ('VENTA_ARCHIVO', 'Venta pesos', 'MXN', False),
    ('VENTA_ARCHIVO', 'Venta dólares', 'USD', False),
    ('VENTA_ARCHIVO', 'Venta efectivo', 'MXN', False),
    ('VENTA_EMITIDA', 'Venta pesos', 'MXN', False),
    ('VENTA_EMITIDA', 'Venta dólares', 'USD', False),
    ('VENTA_EMITIDA', 'Venta efectivo', 'MXN', False),
    ('VENTA_EMITIDA', 'Notas de crédito', 'MXN', True),
    ('INGRESO_BANCOS', 'Banco pesos', 'MXN', False),
    ('INGRESO_BANCOS', 'Banco dólares', 'USD', False),
    ('INGRESO_BANCOS', 'Efectivo', 'MXN', False),
    ('INGRESO_BANCOS', 'Otros pagos', 'MXN', False),
    ('COSTO_MATERIAL', 'Compra material pesos', 'MXN', False),
    ('COSTO_MATERIAL', 'Compra material dólares', 'USD', False),
    ('COSTO_MATERIAL', 'Compra material efectivo', 'MXN', False),
] + [('GASTO', nombre, 'MXN', False) for nombre in [
    'Comisiones de cliente',
    'Comisiones de terceros',
    'Moches y multas',
    'Sueldos: nómina, TE, préstamos, taxis, bonos',
    'Finiquitos',
    'IMSS e ISN',
    'Impuesto SAT',
    'EPP',
    'Renta de patio u oficina',
    'Gastos de patio u oficina',
    'Herramientas contables: contabilidad y softwares',
    'Permisos: transporte, ambiente, placas, etc.',
    'Caja chica',
    'Viáticos',
    'Activo fijo equipo',
    'Renta de equipo',
    'Mantenimiento, reparaciones y refacciones',
    'Insumos y herramientas operativos',
    'Fletes o servicios de otros transportistas',
    'Casetas',
    'Diésel',
    'Gasolina',
    'Oxígeno',
    'Gas LP',
    'GPS y cámaras de camiones',
    'Seguro de camiones',
    'Relleno sanitario',
    'Comisiones bancarias',
    'Gastos variables',
    'Gastos extraordinarios',
    'Gastos de eventos',
    'Gastos de exportación e importaciones',
    'Otros gastos de bodegas',
]]


def sembrar(apps, schema_editor):
    Cuenta = apps.get_model('flujo_bancos', 'ResultadoCuenta')
    Concepto = apps.get_model('flujo_bancos', 'ResultadoConcepto')
    Ajustes = apps.get_model('flujo_bancos', 'ResultadoAjustes')
    for orden, nombre in enumerate(CUENTAS, start=1):
        Cuenta.objects.get_or_create(nombre=nombre, defaults={'orden': orden})
    for orden, (seccion, nombre, moneda, resta) in enumerate(CONCEPTOS, start=1):
        Concepto.objects.get_or_create(seccion=seccion, nombre=nombre,
                                       defaults={'moneda': moneda, 'resta': resta, 'orden': orden})
    Ajustes.objects.get_or_create(pk=1)


class Migration(migrations.Migration):

    dependencies = [
        ('flujo_bancos', '0014_resultados'),
    ]

    operations = [
        # Al revertir no se borra nada: las tablas se eliminan con la 0014.
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]
