from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0078_configuracionalertamerma'),
    ]

    operations = [
        migrations.CreateModel(
            name='DestinatarioAlertaMerma',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, unique=True, verbose_name='Correo electrónico')),
            ],
            options={
                'verbose_name': 'Destinatario Alerta Merma',
                'verbose_name_plural': 'Destinatarios Alerta Merma',
                'ordering': ['email'],
            },
        ),
    ]
