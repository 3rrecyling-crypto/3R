from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta
from django.db.models import Sum  # AÑADE ESTA IMPORTACIÓN
import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)

class Factura(models.Model):
    ESTATUS_CHOICES = (
        ('PENDIENTE', 'Pendiente de Pago'),
        ('PAGADA', 'Pagada'),
        ('VENCIDA', 'Vencida'),
        ('POR_VENCER', 'Por Vencer'),
    )
    
    orden_compra = models.OneToOneField(
        'compras.OrdenCompra',
        on_delete=models.CASCADE, 
        related_name='factura_cxp'
    )
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
    
    # Campos para sincronización con Compras
    archivo_factura = models.FileField(
        upload_to='facturas_cxp/%Y/%m/', 
        null=True, 
        blank=True,
        verbose_name="Archivo de Factura"
    )
    
    def save(self, *args, **kwargs):
        # Primero guardar para obtener un ID si es nuevo
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Sincronizar con la Orden de Compra en Compras
        self._sincronizar_con_compras()
        
        # Solo calcular total_pagado si la factura ya tiene ID (no es nueva)
        if not is_new:
            total_pagado = self.monto_pagado  # Usa la propiedad
            
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
    
    def _sincronizar_con_compras(self):
        """Sincroniza la factura con la Orden de Compra en el módulo de Compras"""
        try:
            # Importación local para evitar circular imports
            from compras.models import OrdenCompra
            
            # Si hay archivo de factura, sincronizar con la OC
            if self.archivo_factura and self.orden_compra:
                # Actualizar la factura en la Orden de Compra
                self.orden_compra.factura = self.archivo_factura
                self.orden_compra.factura_subida = True
                self.orden_compra.factura_subida_por = self.creado_por
                self.orden_compra.fecha_factura_subida = timezone.now()
                
                # Llamar al método de actualización si existe
                if hasattr(self.orden_compra, 'actualizar_estado_auditoria'):
                    self.orden_compra.actualizar_estado_auditoria()
                    
                self.orden_compra.save()
                logger.info(f"Factura sincronizada con OC {self.orden_compra.folio}")
                
        except Exception as e:
            logger.error(f"Error al sincronizar factura con compras: {e}")

    def _generar_resumen_plazos(self):
        """Genera un resumen del estado de los plazos"""
        if not self.es_pago_plazos:
            return {}
        
        plazos_pagados = self.pagos.count()
        plazos_pendientes = self.cantidad_plazos - plazos_pagados
        monto_pagado_total = float(self.monto_pagado)
        monto_pendiente_total = float(self.monto_pendiente)
        
        return {
            'total_plazos': self.cantidad_plazos,
            'plazos_pagados': plazos_pagados,
            'plazos_pendientes': plazos_pendientes,
            'porcentaje_completado': (plazos_pagados / self.cantidad_plazos * 100) if self.cantidad_plazos > 0 else 0,
            'monto_pagado_total': monto_pagado_total,
            'monto_pendiente_total': monto_pendiente_total,
            'proximo_plazo_sugerido': plazos_pagados + 1,
        }
    
    @property
    def monto_por_plazo(self):
        """Calcula el monto por cada plazo"""
        if self.es_pago_plazos and self.cantidad_plazos > 0:
            return float(self.monto) / self.cantidad_plazos
        return float(self.monto)  # Si no es a plazos, devuelve el monto total
    
    @property
    def monto_pagado(self):
        """Total de todos los pagos realizados para esta factura"""
        # Usa aggregate para sumar todos los montos de pagos
        total = self.pagos.aggregate(total=Sum('monto_pagado'))['total']
        return total or 0  # Retorna 0 si no hay pagos
    
    @property
    def monto_pendiente(self):
        return self.monto - self.monto_pagado
    
    @property
    def porcentaje_pagado(self):
        """Porcentaje del monto total que ha sido pagado"""
        if self.monto > 0:
            return (self.monto_pagado / self.monto) * 100
        return 0
    
    @property
    def esta_por_vencer(self):
        return self.dias_restantes_credito <= 3 and self.dias_restantes_credito > 0
    
    @property
    def esta_vencida(self):
        return self.dias_restantes_credito < 0
    
    def __str__(self):
        return f"Factura {self.numero_factura} - OC {self.orden_compra.folio}"
    
    # En models.py de CXP - Añadir al modelo Factura
    @property
    def es_pago_plazos(self):
        """Detecta si la OC asociada es a plazos"""
        return (hasattr(self.orden_compra, 'es_pago_plazos') and 
                self.orden_compra.es_pago_plazos)
    
    @property
    def monto_minimo_permitido(self):
        """Monto mínimo permitido para pagos a plazos (±10%)"""
        if not self.es_pago_plazos:
            return 0
        monto_sugerido = float(self.monto_por_plazo)
        return monto_sugerido * 0.9  # 10% menos

    @property
    def monto_maximo_permitido(self):
        """Monto máximo permitido para pagos a plazos (±10%)"""
        if not self.es_pago_plazos:
            return float(self.monto)
        monto_sugerido = float(self.monto_por_plazo)
        return monto_sugerido * 1.1  # 10% más

    @property
    def cantidad_plazos(self):
        """Número total de plazos programados"""
        if self.es_pago_plazos:
            return self.orden_compra.cantidad_plazos or 1
        return 1  # Una sola exhibición
    
    @property
    def plazos_pendientes(self):
        """Calcula los plazos pendientes de pago"""
        if not self.es_pago_plazos:
            return 0
        total_plazos = self.cantidad_plazos or 0
        plazos_pagados = self.pagos.count()
        return max(0, total_plazos - plazos_pagados)

    @property
    def plazos_programados(self):
        """Genera las fechas programadas de los plazos"""
        if not self.es_pago_plazos:
            return []
        
        plazos = []
        monto_por_plazo = self.monto / self.cantidad_plazos
        
        for i in range(1, self.cantidad_plazos + 1):
            fecha_plazo = self.fecha_emision + timedelta(days=30 * i)
              # Verificar si ya existe un pago para este plazo
            pago_existente = self.pagos.filter(numero_plazo=i).first()
            
            plazos.append({
                'numero_plazo': i,
                'fecha_programada': fecha_plazo,
                'monto_programado': monto_por_plazo,
                'esta_pagado': pago_existente is not None,
                'pago': pago_existente,
                'esta_vencido': fecha_plazo < timezone.now().date() and pago_existente is None,
                'esta_por_vencer': (fecha_plazo - timezone.now().date()).days <= 3 and pago_existente is None,
            })
        
        return plazos
    
    class Meta:
        permissions = [
            ("acceso_cxp", "Acceso al Módulo Cuentas por Pagar"),
            ("autorizar_pagos", "Puede autorizar pagos"),
            ("ver_reportes_cxp", "Puede ver reportes de CXP"),
        ]

    def _get_estado_plazo(self, numero_plazo):
        """Determina el estado de un plazo específico"""
        try:
            pago_existente = self.pagos.get(numero_plazo=numero_plazo)
            return 'PAGADO'
        except Pago.DoesNotExist:
            hoy = timezone.now().date()
            plazo_programado = self.fecha_emision + timedelta(days=30 * numero_plazo)
            
            if hoy > plazo_programado:
                return 'VENCIDO'
            elif (plazo_programado - hoy).days <= 3:
                return 'POR_VENCER'
            else:
                return 'PENDIENTE'


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
    referencia = models.CharField(max_length=100, blank=True)
    notas = models.TextField(blank=True)
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    archivo_comprobante = models.FileField(
        upload_to='comprobantes_pago/%Y/%m/', 
        null=True, 
        blank=True,
        verbose_name="Comprobante de Pago"
    )
    
    # NUEVO: Campo para identificar el plazo
    numero_plazo = models.PositiveIntegerField(
        default=1,
        verbose_name="Número de Plazo",
        help_text="Número del plazo (1 para primer plazo, 2 para segundo, etc.)"
    )
    
    # NUEVO: Campo para fecha programada del plazo
    fecha_plazo_programado = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Fecha Programada del Plazo"
    )
    
    def __str__(self):
        return f"Pago #{self.numero_plazo} de {self.monto_pagado} para Factura {self.factura.numero_factura}"

    class Meta:
        ordering = ['factura', 'numero_plazo']