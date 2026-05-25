from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0086_viaje_eco_remolque'),
        ('RH', '0011_documentooperador_archivo_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='empleado',
            name='lugar',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='empleados_asignados',
                to='ternium.lugar',
                verbose_name='Lugar de operación',
            ),
        ),
    ]
