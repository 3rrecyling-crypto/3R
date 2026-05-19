# Módulo de Viajes / Carta de Traslado (sin timbrar)
# - Campos SCT en Unidad
# - id_ubicacion en Lugar (auto-rellenado)
# - Modelos: Viaje, ItinerarioParada, ViajeMercancia
# - Permisos: acceso_viajes, exportar_viajes_pdf

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def backfill_id_ubicacion(apps, schema_editor):
    """Genera id_ubicacion para los Lugares existentes que no lo tengan."""
    Lugar = apps.get_model('ternium', 'Lugar')
    counters = {'OR': 0, 'DE': 0, 'AM': 0}
    for l in Lugar.objects.order_by('id'):
        if l.id_ubicacion:
            continue
        prefix = 'OR' if l.tipo == 'ORIGEN' else ('DE' if l.tipo == 'DESTINO' else 'AM')
        counters[prefix] += 1
        l.id_ubicacion = f"{prefix}{counters[prefix]:06d}"
        l.save(update_fields=['id_ubicacion'])


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0080_add_dashboard_perms'),
        ('RH', '0010_seed_catalogos_operativos'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Campos SCT en Unidad ──────────────────────────────────────────────
        migrations.AddField(model_name='unidad', name='permiso_sct',
                            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Permiso SCT (Tipo)')),
        migrations.AddField(model_name='unidad', name='no_permiso_sct',
                            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='No. Permiso SCT')),
        migrations.AddField(model_name='unidad', name='nombre_aseguradora',
                            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Nombre Aseguradora')),
        migrations.AddField(model_name='unidad', name='no_poliza_seguro',
                            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='No. Póliza Seguro')),
        migrations.AddField(model_name='unidad', name='eco_remolque_1',
                            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Eco. Remolque 1')),
        migrations.AddField(model_name='unidad', name='placa_remolque_1',
                            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Placa Remolque 1')),
        migrations.AddField(model_name='unidad', name='eco_remolque_2',
                            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Eco. Remolque 2')),
        migrations.AddField(model_name='unidad', name='placa_remolque_2',
                            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Placa Remolque 2')),

        # ── id_ubicacion en Lugar ─────────────────────────────────────────────
        migrations.AddField(
            model_name='lugar', name='id_ubicacion',
            field=models.CharField(blank=True, max_length=15, null=True, unique=True, verbose_name='ID Ubicación'),
        ),
        migrations.RunPython(backfill_id_ubicacion, reverse_code=migrations.RunPython.noop),

        # ── Modelo Viaje ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Viaje',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('id_viaje', models.CharField(blank=True, max_length=20, unique=True, verbose_name='ID Viaje')),
                ('folio_carga', models.CharField(blank=True, max_length=50, null=True, verbose_name='Folio de Carga')),
                ('fecha_viaje', models.DateField(verbose_name='Fecha del Viaje')),
                ('estado', models.CharField(choices=[
                    ('PLANIFICADO', 'Planificado'), ('EN_RUTA', 'En Ruta'),
                    ('ENTREGADO', 'Entregado'), ('CANCELADO', 'Cancelado'),
                ], default='PLANIFICADO', max_length=20)),
                ('observaciones', models.TextField(blank=True, null=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('modificado_en', models.DateTimeField(auto_now=True)),
                ('operador', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                               related_name='viajes', to='RH.empleado', verbose_name='Operador')),
                ('unidad', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                             related_name='viajes', to='ternium.unidad', verbose_name='Unidad')),
                ('origen', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                             related_name='viajes_origen', to='ternium.lugar', verbose_name='Lugar de Origen')),
                ('destino', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                              related_name='viajes_destino', to='ternium.lugar', verbose_name='Lugar de Destino')),
                ('empresa', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              related_name='viajes', to='ternium.empresa', verbose_name='Empresa')),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='viajes_creados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Viaje',
                'verbose_name_plural': 'Viajes',
                'ordering': ['-fecha_viaje', '-creado_en'],
                'permissions': [
                    ('acceso_viajes', 'Acceso al módulo de Viajes / Cartas de Traslado'),
                    ('exportar_viajes_pdf', 'Puede exportar Cartas de Traslado a PDF'),
                ],
            },
        ),

        # ── ItinerarioParada ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='ItinerarioParada',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('orden', models.PositiveSmallIntegerField(default=1)),
                ('fecha_hora', models.DateTimeField(blank=True, null=True, verbose_name='Fecha y hora')),
                ('kms', models.DecimalField(decimal_places=3, default=0, max_digits=10, verbose_name='Kilómetros')),
                ('observaciones', models.CharField(blank=True, max_length=255, null=True)),
                ('lugar', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                            related_name='paradas', to='ternium.lugar')),
                ('viaje', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='paradas', to='ternium.viaje')),
            ],
            options={
                'verbose_name': 'Parada del Itinerario',
                'verbose_name_plural': 'Paradas del Itinerario',
                'ordering': ['viaje', 'orden'],
            },
        ),

        # ── ViajeMercancia ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='ViajeMercancia',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('clave_producto', models.CharField(blank=True, max_length=20, null=True,
                                                     verbose_name='Clave SAT del Producto')),
                ('descripcion', models.CharField(max_length=255, verbose_name='Descripción')),
                ('cantidad', models.DecimalField(decimal_places=2, default=1, max_digits=12, verbose_name='Cantidad')),
                ('peso_kg', models.DecimalField(decimal_places=3, default=0, max_digits=12, verbose_name='Peso (kg)')),
                ('unidad_medida', models.CharField(default='H87', max_length=10, verbose_name='Unidad de medida')),
                ('material_peligroso', models.BooleanField(default=False, verbose_name='¿Material peligroso?')),
                ('notas', models.CharField(blank=True, max_length=255, null=True)),
                ('viaje', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='mercancias', to='ternium.viaje')),
                ('parada_origen', models.ForeignKey(blank=True, null=True,
                                                     on_delete=django.db.models.deletion.SET_NULL,
                                                     related_name='mercancias_origen', to='ternium.itinerarioparada')),
                ('parada_destino', models.ForeignKey(blank=True, null=True,
                                                      on_delete=django.db.models.deletion.SET_NULL,
                                                      related_name='mercancias_destino', to='ternium.itinerarioparada')),
            ],
            options={
                'verbose_name': 'Mercancía del Viaje',
                'verbose_name_plural': 'Mercancías del Viaje',
                'ordering': ['viaje', 'id'],
            },
        ),
    ]
