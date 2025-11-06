from django.core.management.base import BaseCommand
from compras.models import OrdenCompra
from cuentas_por_pagar.models import Factura
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Crea facturas automáticas para Órdenes de Compra aprobadas sin factura'
    
    def handle(self, *args, **options):
        self.stdout.write('Buscando OCs aprobadas sin factura...')
        
        # Encuentra OCs aprobadas que no tengan factura asociada
        ocs_sin_factura = OrdenCompra.objects.filter(
            estatus='APROBADA'
        ).exclude(
            factura_cxp__isnull=False
        )
        
        facturas_creadas = 0
        
        for oc in ocs_sin_factura:
            try:
                # Método más seguro: usar el ID de la orden de compra directamente
                self.crear_factura_segura(oc)
                facturas_creadas += 1
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error creando factura para OC {oc.folio}: {str(e)}')
                )
                logger.error(f"Error detallado para OC {oc.folio}: {str(e)}", exc_info=True)
        
        self.stdout.write(
            self.style.SUCCESS(f'Proceso completado: {facturas_creadas} facturas creadas')
        )
    
    def crear_factura_segura(self, oc):
        """Método seguro para crear facturas evitando problemas de relación"""
        
        # Verificar si ya existe una factura para esta OC
        if hasattr(oc, 'factura_cxp'):
            self.stdout.write(
                self.style.WARNING(f'⚠ OC {oc.folio} ya tiene factura, saltando...')
            )
            return
        
        # Calcular fechas
        dias_credito = getattr(oc.proveedor, 'dias_credito', 30)
        fecha_vencimiento = oc.fecha_emision + timedelta(days=dias_credito)
        
        # Generar número de factura único
        numero_factura = f"FACT-{oc.folio}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        # Crear la factura usando create (más seguro)
        factura = Factura.objects.create(
            orden_compra_id=oc.id,  # Usar el ID directamente en lugar de la instancia
            numero_factura=numero_factura,
            fecha_emision=oc.fecha_emision,
            fecha_vencimiento=fecha_vencimiento,
            monto=oc.total_general,
            notas=f"Factura generada automáticamente para OC {oc.folio}. Días crédito: {dias_credito}",
            creado_por=oc.creado_por,
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Factura {factura.numero_factura} creada para OC {oc.folio}')
        )