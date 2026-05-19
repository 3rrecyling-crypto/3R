from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0085_alter_liquidacionconcepto_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='viaje',
            name='eco_remolque',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Eco. Remolque'),
        ),
        migrations.AddField(
            model_name='viaje',
            name='placa_remolque',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Placa Remolque'),
        ),
    ]
