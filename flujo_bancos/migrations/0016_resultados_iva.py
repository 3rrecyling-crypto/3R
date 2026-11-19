from django.db import migrations, models

# Gastos del catálogo inicial que no llevan IVA: si los montos se capturan con IVA, estos se dejan como están.
# Es solo el punto de partida; cada renglón se cambia en Catálogos.
SIN_IVA = [
    'Moches y multas',
    'Sueldos: nómina, TE, préstamos, taxis, bonos',
    'Finiquitos',
    'IMSS e ISN',
    'Impuesto SAT',
    'Permisos: transporte, ambiente, placas, etc.',
]


def marcar(apps, schema_editor):
    Concepto = apps.get_model('flujo_bancos', 'ResultadoConcepto')
    Concepto.objects.filter(seccion='GASTO', nombre__in=SIN_IVA).update(lleva_iva=False)


class Migration(migrations.Migration):

    dependencies = [
        ('flujo_bancos', '0015_resultados_catalogo'),
    ]

    operations = [
        migrations.AddField(
            model_name='resultadoajustes',
            name='montos_con_iva',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='resultadoajustes',
            name='tasa_iva',
            field=models.DecimalField(decimal_places=2, default=16, max_digits=5),
        ),
        migrations.AddField(
            model_name='resultadoconcepto',
            name='lleva_iva',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(marcar, migrations.RunPython.noop),
    ]
