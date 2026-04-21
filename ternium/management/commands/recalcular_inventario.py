# ternium/management/commands/recalcular_inventario.py

import decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from ternium.models import Remision, InventarioPatio

class Command(BaseCommand):
    help = 'Recalcula el inventario de todos los patios basado en las remisiones existentes (TODO EN KG).'

    def handle(self, *args, **kwargs):
        try:
            with transaction.atomic():
                self.stdout.write(self.style.WARNING('Iniciando el recálculo de inventario (MODO 100% KG)...'))

                # 1. Limpiar inventario
                self.stdout.write('-> Poniendo todo el inventario en patios a CERO.')
                InventarioPatio.objects.all().update(cantidad=decimal.Decimal('0.0'))

                # 2. Procesar remisiones
                # Usamos select_related para optimizar la velocidad
                remisiones_activas = Remision.objects.filter(
                    status__in=['PENDIENTE', 'TERMINADO', 'AUDITADO']
                ).select_related('origen', 'destino').prefetch_related('detalles__material')

                count = 0
                for remision in remisiones_activas:
                    # Verificar si toca algún patio
                    es_salida_patio = (remision.origen and remision.origen.es_patio)
                    es_entrada_patio = (remision.destino and remision.destino.es_patio)

                    if not es_salida_patio and not es_entrada_patio:
                        continue

                    for detalle in remision.detalles.all():
                        if not detalle.material:
                            continue

                        # --- CORRECCIÓN: USAR VALOR DIRECTO (YA ESTÁ EN KG) ---
                        peso_ld_kg = (detalle.peso_ld or 0)
                        peso_dlv_kg = (detalle.peso_dlv or 0)

                        # Restar del Origen (si es patio)
                        if es_salida_patio and peso_ld_kg > 0:
                            inv, _ = InventarioPatio.objects.get_or_create(
                                patio=remision.origen,
                                material=detalle.material
                            )
                            inv.cantidad -= peso_ld_kg
                            inv.save()

                        # Sumar al Destino (si es patio)
                        if es_entrada_patio and peso_dlv_kg > 0:
                            inv, _ = InventarioPatio.objects.get_or_create(
                                patio=remision.destino,
                                material=detalle.material
                            )
                            inv.cantidad += peso_dlv_kg
                            inv.save()
                    
                    count += 1
                    if count % 500 == 0:
                        self.stdout.write(f'   Procesadas {count} remisiones...')

                self.stdout.write(self.style.SUCCESS(f'¡Listo! Se procesaron {count} remisiones usando KG directos.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            raise e