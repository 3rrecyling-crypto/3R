from django.db import migrations, models
import RH.models


class Migration(migrations.Migration):

    dependencies = [
        ('RH', '0010_seed_catalogos_operativos'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentooperador',
            name='archivo',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=RH.models.operador_documento_path,
            ),
        ),
    ]
