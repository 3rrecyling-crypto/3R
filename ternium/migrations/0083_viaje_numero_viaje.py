# Agrega numero_viaje (entero autoincremental) al modelo Viaje.
# Se hace en 3 pasos para soportar tabla con datos existentes:
#   1) Crear la columna como nullable.
#   2) Backfill con un secuencial por orden de creación.
#   3) Marcar como unique + not-null.

from django.db import migrations, models


def backfill_numero_viaje(apps, schema_editor):
    Viaje = apps.get_model('ternium', 'Viaje')
    qs = Viaje.objects.order_by('creado_en', 'id')
    for idx, v in enumerate(qs, start=1):
        if v.numero_viaje is None:
            v.numero_viaje = idx
            v.save(update_fields=['numero_viaje'])


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0082_alter_itinerarioparada_id_alter_lugar_id_ubicacion_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='viaje',
            name='numero_viaje',
            field=models.PositiveIntegerField(blank=True, null=True, db_index=True,
                                              help_text='ID interno secuencial autoincremental',
                                              verbose_name='Número de viaje'),
        ),
        migrations.RunPython(backfill_numero_viaje, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='viaje',
            name='numero_viaje',
            field=models.PositiveIntegerField(blank=True, null=True, db_index=True, unique=True,
                                              help_text='ID interno secuencial autoincremental',
                                              verbose_name='Número de viaje'),
        ),
        migrations.AlterModelOptions(
            name='viaje',
            options={
                'verbose_name': 'Viaje',
                'verbose_name_plural': 'Viajes',
                'ordering': ['-numero_viaje'],
                'permissions': [
                    ('acceso_viajes', 'Acceso al módulo de Viajes / Cartas de Traslado'),
                    ('exportar_viajes_pdf', 'Puede exportar Cartas de Traslado a PDF'),
                ],
            },
        ),
    ]
