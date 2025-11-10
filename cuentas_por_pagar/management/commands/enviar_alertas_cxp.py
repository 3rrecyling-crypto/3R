from django.core.management.base import BaseCommand
from cuentas_por_pagar.alerts import AlertSystem

class Command(BaseCommand):
    help = 'Envía alertas automáticas de cuentas por pagar'
    
    def handle(self, *args, **options):
        alert_system = AlertSystem()
        alert_system.ejecutar_todas_alertas()
        self.stdout.write(
            self.style.SUCCESS('Alertas de cuentas por pagar enviadas correctamente')
        )