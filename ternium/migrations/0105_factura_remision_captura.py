from django.db import migrations, models


def numerar_capturas(apps, schema_editor):
    """Las facturas que ya estaban dadas de alta toman su número de captura en el orden en que se capturaron."""
    FacturaRemision = apps.get_model('ternium', 'FacturaRemision')
    for n, pk in enumerate(FacturaRemision.objects.order_by('creado_en', 'pk').values_list('pk', flat=True), 1):
        FacturaRemision.objects.filter(pk=pk).update(captura=n)


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0104_historial_factura_remision'),
    ]

    operations = [
        migrations.AddField(
            model_name='facturaremision',
            name='captura',
            field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True, verbose_name='Número de captura'),
        ),
        migrations.RunPython(numerar_capturas, migrations.RunPython.noop),
    ]
