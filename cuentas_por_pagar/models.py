from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Factura(models.Model):
    ESTATUS_CHOICES = (
        ('PENDIENTE', 'Pendiente de Pago'),
        ('PAGADA', 'Pagada'),
        ('VENCIDA', 'Vencida'),
        ('POR_VENCER', 'Por Vencer'),
    )
    
    # 1. Folio Interno Automático
    folio_cxp = models.CharField(
        max_length=20, 
        unique=True,
        editable=False, 
        verbose_name="Folio Interno CXP"
    )

    # 2. Folio Fiscal del Proveedor
    numero_factura = models.CharField(
        max_length=50, 
        verbose_name="Folio Fiscal / Factura del Proveedor"
    )

    # --- RELACIONES ---
    orden_compra = models.OneToOneField(
        'compras.OrdenCompra',
        on_delete=models.SET_NULL,
        related_name='factura_cxp',
        null=True,
        blank=True
    )

    proveedor = models.ForeignKey(
        'compras.Proveedor', 
        on_delete=models.CASCADE,
        related_name='facturas_cxp',
        null=True,
        blank=True,
        verbose_name="Proveedor"
    )

    # --- DATOS FINANCIEROS ---
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    
    cantidad_plazos = models.PositiveIntegerField(
        default=1, 
        verbose_name="Cantidad de Pagos (Plazos)",
        help_text="1 para pago único, más de 1 para parcialidades"
    )

    # --- ESTADO Y SEGUIMIENTO ---
    pagada = models.BooleanField(default=False)
    estatus = models.CharField(max_length=20, choices=ESTATUS_CHOICES, default='PENDIENTE')
    notas = models.TextField(blank=True)
    
    dias_restantes_credito = models.IntegerField(default=0)
    ultima_alerta_enviada = models.DateTimeField(null=True, blank=True)
    alertas_enviadas = models.IntegerField(default=0)
    
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    
    archivo_factura = models.FileField(
        upload_to='facturas_cxp/%Y/%m/', 
        null=True, 
        blank=True,
        verbose_name="Archivo de Factura"
    )
    
    def save(self, *args, **kwargs):
        # 1. GENERACIÓN DE FOLIO INTERNO
        if not self.folio_cxp:
            ultimo = Factura.objects.all().order_by('id').last()
            if not ultimo:
                self.folio_cxp = 'CXP-00001'
            else:
                try:
                    ultimo_num = int(ultimo.folio_cxp.split('-')[1])
                    nuevo_num = ultimo_num + 1
                    self.folio_cxp = f'CXP-{nuevo_num:05d}'
                except (IndexError, ValueError, AttributeError):
                    self.folio_cxp = f'CXP-{timezone.now().strftime("%Y%m%d%H%M")}'

        # 2. HERENCIA DE DATOS DE LA OC
        if self.orden_compra:
            self.proveedor = self.orden_compra.proveedor
            if self.pk is None and hasattr(self.orden_compra, 'cantidad_plazos'):
                if self.orden_compra.cantidad_plazos:
                    self.cantidad_plazos = self.orden_compra.cantidad_plazos

        # Aseguramos que cantidad_plazos sea al menos 1
        if not self.cantidad_plazos or self.cantidad_plazos < 1:
            self.cantidad_plazos = 1

        is_new = self.pk is None
        
        # Guardamos primero para tener ID
        super().save(*args, **kwargs)
        
        # 3. AUTOMATIZACIÓN DE PAGOS Y SYNC
        if self.orden_compra:
            self._sincronizar_con_compras()
            
            # --- AUTO-REGISTRO DE PAGOS ---
            # Si viene de OC y aún no tiene pagos, los creamos automáticamente
            if not self.pagos.exists() and self.monto and self.monto > 0:
                self._generar_pagos_automaticos_desde_oc()
        
        # 4. ACTUALIZAR ESTATUS (Importante después de generar pagos)
        self.actualizar_estatus_pago()

    def _generar_pagos_automaticos_desde_oc(self):
        """Genera pagos automáticamente asumiendo validación por OC"""
        try:
            # Importación local para evitar dependencias circulares si Pago está abajo
            # from .models import Pago 
            
            monto_total = float(self.monto)
            cantidad = self.cantidad_plazos
            monto_por_plazo = monto_total / cantidad
            
            # Referencia por defecto
            ref = f"Auto-Generado OC {self.orden_compra.folio}"
            
            for i in range(1, cantidad + 1):
                # Calcular fecha teórica (ej. hoy o diferida)
                fecha_pago = timezone.now().date()
                
                Pago.objects.create(
                    factura=self,
                    numero_plazo=i,
                    monto_pagado=monto_por_plazo,
                    fecha_pago=fecha_pago,
                    metodo_pago='TRANSFERENCIA', # Método por defecto
                    referencia=ref,
                    notas="Pago registrado automáticamente por sistema (Vinculación OC).",
                    registrado_por=self.creado_por
                )
            logger.info(f"Pagos automáticos generados para factura {self.folio_cxp}")
        except Exception as e:
            logger.error(f"Error generando pagos automáticos: {e}")

    def actualizar_estatus_pago(self):
        total_pagado = self.monto_pagado
        # Tolerancia de 10 centavos
        if total_pagado >= (float(self.monto) - 0.10):
            self.pagada = True
            self.estatus = 'PAGADA'
        else:
            self.pagada = False
            hoy = timezone.now().date()
            if self.fecha_vencimiento:
                self.dias_restantes_credito = (self.fecha_vencimiento - hoy).days
                if self.dias_restantes_credito < 0:
                    self.estatus = 'VENCIDA'
                elif self.dias_restantes_credito <= 3:
                    self.estatus = 'POR_VENCER'
                else:
                    self.estatus = 'PENDIENTE'
        
        super().save(update_fields=['pagada', 'estatus', 'dias_restantes_credito'])
    
    def _sincronizar_con_compras(self):
        try:
            from compras.models import OrdenCompra
            if self.archivo_factura and self.orden_compra:
                self.orden_compra.factura = self.archivo_factura
                self.orden_compra.factura_subida = True
                self.orden_compra.factura_subida_por = self.creado_por
                self.orden_compra.fecha_factura_subida = timezone.now()
                if hasattr(self.orden_compra, 'actualizar_estado_auditoria'):
                    self.orden_compra.actualizar_estado_auditoria()
                self.orden_compra.save()
        except Exception as e:
            logger.error(f"Error sync compras: {e}")

    @property
    def es_pago_plazos(self):
        return self.cantidad_plazos > 1
    
    @property
    def monto_pagado(self):
        total = self.pagos.aggregate(total=Sum('monto_pagado'))['total']
        return float(total or 0)
    
    @property
    def monto_pendiente(self):
        return float(self.monto) - self.monto_pagado
    
    @property
    def porcentaje_pagado(self):
        if self.monto > 0:
            return (self.monto_pagado / float(self.monto)) * 100
        return 0
    
    @property
    def esta_por_vencer(self):
        return self.dias_restantes_credito <= 3 and self.dias_restantes_credito >= 0 and not self.pagada
    
    @property
    def esta_vencida(self):
        return self.dias_restantes_credito < 0 and not self.pagada
    
    @property
    def nombre_proveedor(self):
        if self.proveedor:
            return self.proveedor.razon_social
        elif self.orden_compra and self.orden_compra.proveedor:
            return self.orden_compra.proveedor.razon_social
        return "Proveedor No Especificado"
    
    @property
    def monto_por_plazo(self):
        if self.cantidad_plazos > 0:
            return float(self.monto) / self.cantidad_plazos
        return float(self.monto)

    @property
    def monto_minimo_permitido(self):
        return self.monto_por_plazo * 0.9

    @property
    def monto_maximo_permitido(self):
        return self.monto_por_plazo * 1.1

    @property
    def plazos_programados(self):
        """
        Retorna la estructura unificada de plazos.
        Funciona para pago único (lista de 1 elemento) o múltiples plazos.
        """
        plazos = []
        # Aseguramos mínimo 1 plazo
        cantidad = self.cantidad_plazos if self.cantidad_plazos > 0 else 1
        monto_por_plazo = float(self.monto) / cantidad
        
        for i in range(1, cantidad + 1):
            # Fecha teórica (ej. cada 30 días)
            fecha_teorica = self.fecha_emision + timedelta(days=30 * i) if self.fecha_emision else timezone.now().date()
            
            # Buscar si ya existe el pago real
            pago_real = self.pagos.filter(numero_plazo=i).first()
            
            plazos.append({
                'numero_plazo': i,
                'fecha_programada': fecha_teorica,
                'monto_programado': monto_por_plazo,
                'esta_pagado': pago_real is not None,
                'pago': pago_real, # Objeto Pago o None
                'esta_vencido': (not pago_real and fecha_teorica < timezone.now().date()),
                'esta_por_vencer': (not pago_real and 0 <= (fecha_teorica - timezone.now().date()).days <= 3)
            })
        return plazos

    def __str__(self):
        return f"{self.folio_cxp} | {self.proveedor} (${self.monto})"
    
    class Meta:
        permissions = [("acceso_cxp", "Acceso al Módulo Cuentas por Pagar")]

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
    archivo_comprobante = models.FileField(upload_to='comprobantes_pago/%Y/%m/', null=True, blank=True, verbose_name="Comprobante de Pago")
    numero_plazo = models.PositiveIntegerField(default=1, verbose_name="Número de Plazo")
    fecha_plazo_programado = models.DateField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar la factura padre cada vez que se guarda un pago
        self.factura.actualizar_estatus_pago()
        
    def __str__(self):
        return f"Pago {self.monto_pagado} - {self.factura.folio_cxp}"

    class Meta:
        ordering = ['factura', 'numero_plazo']

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
    archivo_comprobante = models.FileField(upload_to='comprobantes_pago/%Y/%m/', null=True, blank=True, verbose_name="Comprobante de Pago")
    numero_plazo = models.PositiveIntegerField(default=1, verbose_name="Número de Plazo")
    fecha_plazo_programado = models.DateField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.factura.actualizar_estatus_pago()
        
    def __str__(self):
        return f"Pago {self.monto_pagado} - {self.factura.folio_cxp}"

    class Meta:
        ordering = ['factura', 'numero_plazo']