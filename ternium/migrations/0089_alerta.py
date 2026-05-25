from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0088_anchor_medline_146'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Alerta',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(
                    choices=[
                        ('alert',   'Crítica'),
                        ('warning', 'Advertencia'),
                        ('info',    'Informativa'),
                        ('success', 'Éxito'),
                        ('neural',  'Neural'),
                    ],
                    default='info', max_length=10,
                )),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('desc', models.TextField(verbose_name='Mensaje')),
                ('creada_en', models.DateTimeField(auto_now_add=True)),
                ('creada_por', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='alertas_creadas',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Creada por',
                )),
                ('leida_por', models.ManyToManyField(
                    blank=True,
                    related_name='alertas_leidas',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Leída por',
                )),
            ],
            options={
                'verbose_name': 'Alerta',
                'verbose_name_plural': 'Alertas',
                'ordering': ['-creada_en'],
            },
        ),
    ]
