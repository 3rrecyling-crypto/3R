from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0077_add_module_access_perms'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionAlertaMerma',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('porcentaje_umbral', models.DecimalField(decimal_places=2, default=1.0, max_digits=5, verbose_name='Umbral de merma (%)')),
                ('material', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='config_alerta_merma',
                    to='ternium.material',
                    verbose_name='Material',
                )),
            ],
            options={
                'verbose_name': 'Configuración Alerta Merma',
                'verbose_name_plural': 'Configuraciones Alerta Merma',
                'ordering': ['material__nombre'],
            },
        ),
    ]
