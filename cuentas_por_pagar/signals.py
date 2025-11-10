# cuentas_por_pagar/signals.py

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.files.base import ContentFile
import os
from .models import Factura, Pago
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender='compras.OrdenCompra')
def sincronizar_factura_desde_compras(sender, instance, **kwargs):
    """
    Cuando se sube una factura en Compras, se sincroniza con Cuentas por Pagar
    """
    try:
        if instance.factura and hasattr(instance, 'factura_cxp'):
            factura_cxp = instance.factura_cxp
            
            # Si la factura en CxP no tiene archivo, copiar el de Compras
            if not factura_cxp.archivo_factura:
                # Copiar el archivo de factura
                factura_cxp.archivo_factura.save(
                    instance.factura.name,
                    ContentFile(instance.factura.read()),
                    save=True
                )
                logger.info(f"Factura sincronizada desde Compras a CxP para OC {instance.folio}")
                
    except Exception as e:
        logger.error(f"Error sincronizando factura desde Compras: {e}")

@receiver(post_save, sender='compras.OrdenCompra')
def sincronizar_comprobante_desde_compras(sender, instance, **kwargs):
    """
    Cuando se sube un comprobante en Compras, se sincroniza con Cuentas por Pagar
    """
    try:
        if instance.comprobante_pago and hasattr(instance, 'factura_cxp'):
            factura_cxp = instance.factura_cxp
            
            # Buscar el último pago de esta factura para actualizar su comprobante
            ultimo_pago = factura_cxp.pagos.last()
            if ultimo_pago and not ultimo_pago.archivo_comprobante:
                # Copiar el archivo de comprobante
                ultimo_pago.archivo_comprobante.save(
                    instance.comprobante_pago.name,
                    ContentFile(instance.comprobante_pago.read()),
                    save=True
                )
                logger.info(f"Comprobante sincronizado desde Compras a CxP para OC {instance.folio}")
                
    except Exception as e:
        logger.error(f"Error sincronizando comprobante desde Compras: {e}")