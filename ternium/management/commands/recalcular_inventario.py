# ternium/management/commands/recalcular_inventario.py

import decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from ternium.models import Remision, InventarioPatio

class Command(BaseCommand):
    help = 'Recalcula el inventario de todos los patios basado en las remisiones existentes.'

    def handle(self, *args, **kwargs):
        try:
            with transaction.atomic():
                self.stdout.write(self.style.WARNING('Iniciando el recálculo de inventario...'))

                # Paso 1: Poner a CERO todo el inventario de los patios.
                # Esto limpia los datos incorrectos anteriores.
                self.stdout.write('-> Poniendo todo el inventario en patios a CERO.')
                InventarioPatio.objects.all().update(cantidad=decimal.Decimal('0.0'))

                self.stdout.write(self.style.SUCCESS('   Inventario limpiado.'))

                # Paso 2: Iterar sobre TODAS las remisiones existentes y aplicar su lógica.
                self.stdout.write('-> Procesando todas las remisiones existentes para reconstruir el inventario...')
                remisiones_activas = Remision.objects.filter(status__in=['PENDIENTE', 'TERMINADO', 'AUDITADO']).prefetch_related('detalles__material', 'origen', 'destino')

                TON_TO_KG = decimal.Decimal('1000.0')

                for remision in remisiones_activas:
                    # Restar del ORIGEN si es un patio
                    if remision.origen and remision.origen.es_patio:
                        for detalle in remision.detalles.all():
                            if detalle.peso_ld > 0:
                                inv, created = InventarioPatio.objects.get_or_create(
                                    patio=remision.origen,
                                    material=detalle.material
                                )
                                inv.cantidad -= (detalle.peso_ld * TON_TO_KG)
                                inv.save()

                    # Sumar al DESTINO si es un patio
                    if remision.destino and remision.destino.es_patio:
                        for detalle in remision.detalles.all():
                            if detalle.peso_dlv > 0:
                                inv, created = InventarioPatio.objects.get_or_create(
                                    patio=remision.destino,
                                    material=detalle.material
                                )
                                inv.cantidad += (detalle.peso_dlv * TON_TO_KG)
                                inv.save()

                self.stdout.write(self.style.SUCCESS(f'   Se procesaron {remisiones_activas.count()} remisiones.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ocurrió un error durante el proceso: {e}'))
            raise e

        self.stdout.write(self.style.SUCCESS('¡Recálculo de inventario completado exitosamente!'))