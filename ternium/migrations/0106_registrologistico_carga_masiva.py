from django.db import migrations, models


def marcar_cargados(apps, schema_editor):
    """Los que ya se subieron con la carga masiva (antes de existir este campo) llevan esa nota en Comentarios."""
    RegistroLogistico = apps.get_model('ternium', 'RegistroLogistico')
    RegistroLogistico.objects.filter(comentario__contains='Carga masiva desde Excel (').update(carga_masiva=True)


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0105_factura_remision_captura'),
    ]

    operations = [
        migrations.AddField(
            model_name='registrologistico',
            name='carga_masiva',
            field=models.BooleanField(default=False, editable=False, verbose_name='Desde carga masiva (Excel)'),
        ),
        migrations.RunPython(marcar_cargados, migrations.RunPython.noop),
    ]
