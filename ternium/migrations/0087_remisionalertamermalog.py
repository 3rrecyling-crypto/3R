from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0086_viaje_eco_remolque'),
    ]

    operations = [
        migrations.CreateModel(
            name='RemisionAlertaMermaLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enviada_en', models.DateTimeField(auto_now_add=True, verbose_name='Enviada en')),
                ('materiales_alertados', models.PositiveSmallIntegerField(default=0, verbose_name='Cantidad de materiales que superaron el umbral')),
                ('detalle', models.TextField(blank=True, default='', verbose_name='Resumen de la alerta enviada')),
                ('remision', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='alerta_merma_log',
                    to='ternium.remision',
                    verbose_name='Remisión',
                )),
            ],
            options={
                'verbose_name': 'Log de Alerta Merma',
                'verbose_name_plural': 'Logs de Alertas Merma',
                'ordering': ['-enviada_en'],
            },
        ),
    ]
