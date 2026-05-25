from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0089_alerta'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatMensaje',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rol', models.CharField(
                    choices=[('user', 'Usuario'), ('bot', 'Asistente')],
                    max_length=10,
                )),
                ('contenido', models.TextField()),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='chat_mensajes',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Mensaje del Chat IA',
                'verbose_name_plural': 'Mensajes del Chat IA',
                'ordering': ['creado_en'],
            },
        ),
        migrations.AddIndex(
            model_name='chatmensaje',
            index=models.Index(fields=['user', 'creado_en'], name='ternium_cha_user_id_creado__idx'),
        ),
    ]
