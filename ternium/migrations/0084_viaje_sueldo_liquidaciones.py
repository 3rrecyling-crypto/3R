# Sueldo del operador en Viaje + módulo de Liquidaciones de Operador
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0083_viaje_numero_viaje'),
        ('RH', '0010_seed_catalogos_operativos'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── sueldo_operador en Viaje ──
        migrations.AddField(
            model_name='viaje',
            name='sueldo_operador',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12,
                                       verbose_name='Sueldo del operador',
                                       help_text='Pago al operador por este viaje'),
        ),

        # ── LiquidacionOperador ──
        migrations.CreateModel(
            name='LiquidacionOperador',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('folio', models.CharField(blank=True, max_length=20, unique=True, verbose_name='Folio')),
                ('fecha_inicio', models.DateField(verbose_name='Periodo desde')),
                ('fecha_fin', models.DateField(verbose_name='Periodo hasta')),
                ('estado', models.CharField(choices=[
                    ('BORRADOR', 'Borrador'),
                    ('APROBADA', 'Aprobada'),
                    ('PAGADA', 'Pagada'),
                    ('CANCELADA', 'Cancelada'),
                ], default='BORRADOR', max_length=20)),
                ('fecha_pago', models.DateField(blank=True, null=True)),
                ('observaciones', models.TextField(blank=True, null=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('modificado_en', models.DateTimeField(auto_now=True)),
                ('operador', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                related_name='liquidaciones', to='RH.empleado',
                                                verbose_name='Operador')),
                ('creado_por', models.ForeignKey(blank=True, null=True,
                                                  on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='liquidaciones_creadas',
                                                  to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Liquidación de Operador',
                'verbose_name_plural': 'Liquidaciones de Operador',
                'ordering': ['-creado_en'],
                'permissions': [
                    ('acceso_liquidaciones', 'Acceso al módulo de Liquidaciones de Operador'),
                ],
            },
        ),

        # ── LiquidacionConcepto ──
        migrations.CreateModel(
            name='LiquidacionConcepto',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[
                    ('VIAJE', 'Viaje'),
                    ('EXTRA', 'Extra / Bono'),
                    ('DESCUENTO', 'Descuento'),
                ], default='VIAJE', max_length=15)),
                ('descripcion', models.CharField(max_length=255)),
                ('monto', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('liquidacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='conceptos', to='ternium.liquidacionoperador')),
                ('viaje', models.ForeignKey(blank=True, null=True,
                                             on_delete=django.db.models.deletion.SET_NULL,
                                             related_name='conceptos_liquidacion', to='ternium.viaje')),
            ],
            options={
                'verbose_name': 'Concepto de Liquidación',
                'verbose_name_plural': 'Conceptos de Liquidación',
                'ordering': ['liquidacion', 'id'],
            },
        ),
    ]
