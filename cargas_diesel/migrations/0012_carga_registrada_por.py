import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cargas_diesel', '0011_auditoria_ia'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cargadiesel',
            name='registrada_por',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Registrada por'),
        ),
        migrations.AddField(
            model_name='cargadiesel',
            name='registrada_en',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Registrada el'),
        ),
    ]
