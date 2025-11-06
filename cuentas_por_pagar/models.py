from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import logging


logger = logging.getLogger(__name__)

# Importación condicional para evitar problemas de importación circular
try:
    from compras.models import OrdenCompra
except ImportError:
    # Fallback para cuando la app compras no esté disponible
    OrdenCompra = None
    logger.warning("No se pudo importar OrdenCompra desde compras.models")

try:
    from ternium.models import Empresa
except ImportError:
    # Fallback para cuando la app ternium no esté disponible
    Empresa = None
    logger.warning("No se pudo importar Empresa desde ternium.models")

class Factura(models.Model):
    ESTATUS_CHOICES = (
        ('PENDIENTE', 'Pendiente de Pago'),
        ('PAGADA', 'Pagada'),
        ('VENCIDA', 'Vencida'),
        ('POR_VENCER', 'Por Vencer'),
    )
    
    orden_compra = models.OneToOneField(OrdenCompra, on_delete=models.CASCADE, related_name='factura_cxp')
    numero_factura = models.CharField(max_length=50, unique=True)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    pagada = models.BooleanField(default=False)
    estatus = models.CharField(max_length=20, choices=ESTATUS_CHOICES, default='PENDIENTE')
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    
    # Nuevos campos para tracking
    dias_restantes_credito = models.IntegerField(default=0)
    ultima_alerta_enviada = models.DateTimeField(null=True, blank=True)
    alertas_enviadas = models.IntegerField(default=0)
    
    def save(self, *args, **kwargs):
        # Primero guardar para obtener un ID si es nuevo
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Solo calcular total_pagado si la factura ya tiene ID (no es nueva)
        if not is_new:
            total_pagado = sum(pago.monto_pagado for pago in self.pagos.all())
            
            # Actualizar estatus basado en pagos
            if total_pagado >= self.monto:
                self.pagada = True
                self.estatus = 'PAGADA'
            else:
                # Calcular días restantes y estatus basado en fecha
                hoy = timezone.now().date()
                if self.fecha_vencimiento:
                    self.dias_restantes_credito = (self.fecha_vencimiento - hoy).days
                    
                    if self.dias_restantes_credito < 0:
                        self.estatus = 'VENCIDA'
                    elif self.dias_restantes_credito <= 3:
                        self.estatus = 'POR_VENCER'
                    else:
                        self.estatus = 'PENDIENTE'
            
            # Guardar nuevamente si hubo cambios
            super().save(update_fields=['pagada', 'estatus', 'dias_restantes_credito'])
    
    @property
    def monto_pendiente(self):
        total_pagado = sum(pago.monto_pagado for pago in self.pagos.all())
        return self.monto - total_pagado
    
    @property
    def esta_por_vencer(self):
        return self.dias_restantes_credito <= 3 and self.dias_restantes_credito > 0
    
    @property
    def esta_vencida(self):
        return self.dias_restantes_credito < 0
    
    def __str__(self):
        return f"Factura {self.numero_factura} - OC {self.orden_compra.folio}"

class Pago(models.Model):
    METODO_CHOICES = (
        ('TRANSFERENCIA', 'Transferencia'),
        ('CHEQUE', 'Cheque'),
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
    )
    
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name='pagos')
    fecha_pago = models.DateField()
    monto_pagado = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_CHOICES)
    referencia = models.CharField(max_length=100, blank=True)  # Ej. número de cheque
    notas = models.TextField(blank=True)
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Pago de {self.monto_pagado} para Factura {self.factura.numero_factura}"

# Signal para crear factura automáticamente
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=OrdenCompra)
def crear_factura_automatica(sender, instance, created, **kwargs):
    if instance.estatus == 'APROBADA' and not hasattr(instance, 'factura_cxp'):
        # Calcular fecha de vencimiento basada en días de crédito del proveedor
        dias_credito = instance.proveedor.dias_credito
        fecha_vencimiento = instance.fecha_emision + timedelta(days=dias_credito)
        
        # Generar número de factura único
        numero_factura = f"FACT-{instance.folio}-{instance.fecha_emision.strftime('%Y%m%d')}"
        
        Factura.objects.create(
            orden_compra=instance,
            numero_factura=numero_factura,
            fecha_emision=instance.fecha_emision,
            fecha_vencimiento=fecha_vencimiento,
            monto=instance.total_general,
            notas=f"Factura generada automáticamente para OC {instance.folio}. Días crédito: {dias_credito}",
            creado_por=instance.creado_por,
        )
        logger.info(f"Factura automática creada para OC {instance.folio}")