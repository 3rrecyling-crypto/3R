# ternium/apps.py

from django.apps import AppConfig


class TerniumConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ternium'

    def ready(self):
        # Importa las señales para que se registren
        import ternium.models