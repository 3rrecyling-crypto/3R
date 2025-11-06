from django.core.management.base import BaseCommand
from cuentas_por_pagar.models import Factura
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Migra datos existentes de facturas para el nuevo sistema de cuentas por pagar'
    
    def handle(self, *args, **options):
        self.stdout.write('Iniciando migración de datos existentes...')
        
        facturas_actualizadas = 0
        facturas_con_errores = 0
        
        for factura in Factura.objects.all():
            try:
                # 1. Calcular días restantes basado en fecha de vencimiento
                hoy = timezone.now().date()
                if factura.fecha_vencimiento:
                    dias_restantes = (factura.fecha_vencimiento - hoy).days
                    factura.dias_restantes_credito = dias_restantes
                
                # 2. Recalcular estatus basado en la nueva lógica
                if not factura.pagada:
                    if factura.dias_restantes_credito < 0:
                        factura.estatus = 'VENCIDA'
                    elif factura.dias_restantes_credito <= 3:
                        factura.estatus = 'POR_VENCER'
                    else:
                        factura.estatus = 'PENDIENTE'
                else:
                    factura.estatus = 'PAGADA'
                
                # 3. Guardar los cambios
                factura.save()
                facturas_actualizadas += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Factura {factura.numero_factura} actualizada: '
                        f'{factura.estatus} ({factura.dias_restantes_credito} días)'
                    )
                )
                
            except Exception as e:
                facturas_con_errores += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Error en factura {factura.numero_factura}: {str(e)}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Migración completada: {facturas_actualizadas} facturas actualizadas, '
                f'{facturas_con_errores} errores'
            )
        )