from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cargas_diesel', '0005_patio_alter_ajusteinventario_options_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Fotos clásicas pasan a opcionales (registro rápido en campo).
        migrations.AlterField(
            model_name='cargadiesel',
            name='foto_bomba',
            field=models.ImageField(blank=True, null=True, upload_to='diesel/bombas/%Y/%m/', verbose_name='Foto Bomba'),
        ),
        migrations.AlterField(
            model_name='cargadiesel',
            name='foto_odometro',
            field=models.ImageField(blank=True, null=True, upload_to='diesel/odometros/%Y/%m/', verbose_name='Foto Odómetro'),
        ),
        # Cinchos
        migrations.AddField(
            model_name='cargadiesel',
            name='cinchos_anteriores',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Cinchos anteriores'),
        ),
        migrations.AddField(
            model_name='cargadiesel',
            name='cinchos_actuales',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Cinchos actuales'),
        ),
        # Persona que rellenó (FK a User, se llena con el usuario logueado).
        migrations.AddField(
            model_name='cargadiesel',
            name='persona_relleno',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=models.SET_NULL,
                related_name='diesel_cargas_realizadas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Persona que realizó el llenado',
            ),
        ),
        # Fotos adicionales (todas opcionales).
        migrations.AddField(
            model_name='cargadiesel',
            name='foto_sticker',
            field=models.ImageField(blank=True, null=True, upload_to='diesel/stickers/%Y/%m/', verbose_name='Foto Sticker'),
        ),
        migrations.AddField(
            model_name='cargadiesel',
            name='foto_motor',
            field=models.ImageField(blank=True, null=True, upload_to='diesel/motor/%Y/%m/', verbose_name='Foto Motor'),
        ),
        migrations.AddField(
            model_name='cargadiesel',
            name='foto_thermo',
            field=models.ImageField(blank=True, null=True, upload_to='diesel/thermo/%Y/%m/', verbose_name='Foto Thermo'),
        ),
        migrations.AddField(
            model_name='cargadiesel',
            name='foto_horas_thermo',
            field=models.ImageField(blank=True, null=True, upload_to='diesel/horas_thermo/%Y/%m/', verbose_name='Foto Horas Thermo'),
        ),
    ]
