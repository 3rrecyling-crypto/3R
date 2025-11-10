from django.apps import AppConfig


class CuentasPagarConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cuentas_por_pagar"

# cuentas_por_pagar/apps.py

class CuentasPorPagarConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cuentas_por_pagar'
    
    def ready(self):
        import cuentas_por_pagar.signals