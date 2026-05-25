from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0087_remisionalertamermalog'),
        ('RH', '0013_seed_divisiones_reales'),
    ]

    operations = [
        migrations.AddField(
            model_name='empleado',
            name='empresas',
            field=models.ManyToManyField(
                blank=True,
                related_name='empleados',
                to='ternium.empresa',
                verbose_name='Empresas asignadas',
            ),
        ),
    ]
