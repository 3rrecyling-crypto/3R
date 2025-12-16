# compras/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from ternium.models import Empresa, Lugar
from django.utils import timezone
from datetime import timedelta
from django.apps import apps  # <-- AÑADIR ESTE IMPORT

# --- 1. CATÁLOGOS BASE ---

class Proveedor(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="proveedores", help_text="Empresa a la que pertenece este proveedor")
    lugar = models.ForeignKey(
        Lugar, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True, 
        related_name="proveedores",
        limit_choices_to={'tipo': 'ORIGEN'},
        help_text="Empresa (Lugar de Origen) asociada al proveedor"
    )
    razon_social = models.CharField(max_length=255)
    rfc = models.CharField(max_length=13, unique=True)
    direccion = models.TextField(blank=True, null=True)
    contacto_principal = models.CharField(max_length=150, blank=True, null=True)
    email_contacto = models.EmailField(blank=True, null=True)
    telefono_contacto = models.CharField(max_length=20, blank=True, null=True)
    cuentas_bancarias = models.TextField(blank=True, null=True, help_text="Añadir una cuenta por línea")
    dias_credito = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.razon_social

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ['razon_social']


class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategorias', verbose_name="Categoría Padre")

    def __str__(self):
        path = [self.nombre]
        p = self.parent
        while p is not None:
            path.insert(0, p.nombre)
            p = p.parent
        return ' -> '.join(path)

    def clean(self):
        if self.parent and self.parent.id == self.id:
            raise ValidationError("Una categoría no puede ser su propia categoría padre.")
        super().clean()

    class Meta:
        verbose_name = "Categoría de Producto"
        verbose_name_plural = "Categorías de Productos"
        unique_together = ('nombre', 'parent')
        
from django.db.models.signals import post_migrate
from django.dispatch import receiver

class UnidadMedida(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    abreviatura = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return f"{self.nombre} ({self.abreviatura})"

@receiver(post_migrate)
def poblar_unidades_medida(sender, **kwargs):
    if sender.name == 'compras':
        UnidadMedida = sender.get_model('UnidadMedida')
        
        if not UnidadMedida.objects.exists():
            unidades_a_crear = [
                UnidadMedida(nombre='Pieza', abreviatura='PZA'),
                UnidadMedida(nombre='Unidad', abreviatura='UNID'),
                UnidadMedida(nombre='Paquete', abreviatura='PAQ'),
                UnidadMedida(nombre='Caja', abreviatura='CJA'),
                UnidadMedida(nombre='Docena', abreviatura='DOC'),
                UnidadMedida(nombre='Par', abreviatura='PAR'),
                UnidadMedida(nombre='Kilogramo', abreviatura='KG'),
                UnidadMedida(nombre='Gramo', abreviatura='GR'),
                UnidadMedida(nombre='Tonelada', abreviatura='TON'),
                UnidadMedida(nombre='Libra', abreviatura='LB'),
                UnidadMedida(nombre='Litro', abreviatura='LT'),
                UnidadMedida(nombre='Mililitro', abreviatura='ML'),
                UnidadMedida(nombre='Galón', abreviatura='GAL'),
                UnidadMedida(nombre='Metro', abreviatura='M'),
                UnidadMedida(nombre='Centímetro', abreviatura='CM'),
                UnidadMedida(nombre='Milímetro', abreviatura='MM'),
                UnidadMedida(nombre='Pulgada', abreviatura='IN'),
                UnidadMedida(nombre='Servicio', abreviatura='SERV'),
                UnidadMedida(nombre='Hora', abreviatura='HR'),
                UnidadMedida(nombre='Día', abreviatura='DIA'),
                UnidadMedida(nombre='Mes', abreviatura='MES'),
                UnidadMedida(nombre='Lote', abreviatura='LOTE'),
                UnidadMedida(nombre='Rollo', abreviatura='ROLLO'),
                UnidadMedida(nombre='Kit', abreviatura='KIT'),
                UnidadMedida(nombre='Metro Cuadrado', abreviatura='M2'),
                UnidadMedida(nombre='Metro Cúbico', abreviatura='M3'),
            ]
            
            UnidadMedida.objects.bulk_create(unidades_a_crear)
            print("\n✅ Se han cargado las unidades de medida iniciales.")


# --- 2. GESTIÓN DE ARTÍCULOS ---

class Articulo(models.Model):
    TIPO_CHOICES = (('PRODUCTO', 'Producto'), ('SERVICIO', 'Servicio'))
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="articulos")  
    
    origen = models.ForeignKey(
        Lugar,
        on_delete=models.PROTECT, 
        null=True, 
        blank=True, 
        related_name="articulos",
        limit_choices_to={'tipo': 'ORIGEN'}, 
        help_text="Origen del artículo (filtrado por empresa y tipo)"
    )
    nombre = models.CharField(max_length=200)   
    descripcion = models.TextField(blank=True, null=True)
    sku = models.CharField(max_length=100, blank=True, null=True, help_text="Identificador único del producto o servicio por empresa")
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    unidad_medida = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, null=True, blank=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='PRODUCTO')
    
    porcentaje_iva = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00, 
        verbose_name="% IVA",
        help_text="Ej: 16.00"
    )
    porcentaje_retencion_iva = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00, 
        verbose_name="% Retención IVA",
        help_text="Ej: 4.00"
    )
    # -
    
    proveedores = models.ManyToManyField(Proveedor, through='ArticuloProveedor', related_name='articulos_provistos')
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.sku or 'Sin SKU'}) - {self.empresa.nombre}"
    
    def clean(self):
        super().clean()
        if self.sku:
            qs = Articulo.objects.filter(empresa=self.empresa, sku=self.sku)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({
                    'sku': f"Ya existe otro artículo con el SKU '{self.sku}' en la empresa '{self.empresa.nombre}'."
                })
    
    class Meta:
        unique_together = ('empresa', 'nombre') 


class ArticuloProveedor(models.Model):
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.articulo.nombre} - {self.proveedor.razon_social}: ${self.precio_unitario}"

    class Meta:
        unique_together = ('articulo', 'proveedor')


# --- 3. PROCESO DE COMPRA ---

class SolicitudCompra(models.Model):
    PRIORIDAD_CHOICES = (('URGENTE', 'Urgente'), ('PROGRAMADO', 'Programado'), ('STOCK', 'Stock de Seguridad'))
    ESTATUS_CHOICES = (('BORRADOR', 'Borrador'), ('PENDIENTE_APROBACION', 'Pendiente de Aprobación'), ('APROBADA', 'Aprobada'), ('RECHAZADA', 'Rechazada'), ('CERRADA', 'Cerrada'))

    folio = models.CharField(max_length=20, unique=True, editable=False)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, verbose_name="Operación")
    
    lugar = models.ForeignKey(
        Lugar, 
        on_delete=models.PROTECT,
        related_name="solicitudes", 
        help_text="Empresa (Lugar de Origen) de la solicitud",
        verbose_name="Empresa (Lugar de Origen)"
    )

    solicitante = models.ForeignKey(User, on_delete=models.PROTECT, related_name="solicitudes_creadas")
    motivo = models.TextField()
    prioridad = models.CharField(max_length=20, choices=PRIORIDAD_CHOICES, default='PROGRAMADO')
    estatus = models.CharField(max_length=25, choices=ESTATUS_CHOICES, default='BORRADOR')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True, help_text="Proveedor seleccionado para esta solicitud (opcional)")
    cotizacion = models.FileField(upload_to='cotizaciones/%Y/%m/', null=True, blank=True, verbose_name="Archivo de Cotización")
    aprobado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="solicitudes_aprobadas")
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.folio:
            last_id = SolicitudCompra.objects.all().order_by('id').last()
            next_id = (last_id.id + 1) if last_id else 1
            self.folio = f"SC-{self.empresa.id}-{next_id:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Solicitud {self.folio} - {self.empresa.nombre}"


class DetalleSolicitud(models.Model):
    solicitud = models.ForeignKey(SolicitudCompra, on_delete=models.CASCADE, related_name='detalles')
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    
    def __str__(self):
        return f"{self.cantidad} x {self.articulo.nombre}"


class OrdenCompra(models.Model):
    ESTATUS_CHOICES = (
        ('BORRADOR', 'Borrador'),
        ('APROBADA', 'Aprobada'),
        ('LISTA_PARA_AUDITAR', 'Lista para Auditar'),
        ('CANCELADA', 'Cancelada'),
        ('AUDITADA', 'Auditada'),
    )
    
    MONEDA_CHOICES = (
        ('MXN', 'MXN - Pesos Mexicanos'),
        ('USD', 'USD - Dólares Americanos'),
    )

    folio = models.CharField(max_length=20, unique=True, editable=False)
    solicitud_origen = models.OneToOneField(SolicitudCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name="orden_de_compra")
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_entrega_esperada = models.DateField()
    moneda = models.CharField(max_length=3, choices=MONEDA_CHOICES, default='MXN')
    tipo_cambio = models.DecimalField(max_digits=10, decimal_places=4, default=1.0)
    condiciones_pago = models.CharField(max_length=255)
    estatus = models.CharField(max_length=20, choices=ESTATUS_CHOICES, default='BORRADOR')
    creado_por = models.ForeignKey(User, on_delete=models.PROTECT)
    creado_en = models.DateTimeField(auto_now_add=True)
    MODALIDAD_PAGO_CHOICES = (
        ('UNA_EXHIBICION', 'A una sola exhibición'),
        ('A_PLAZOS', 'A plazos'),
    )
    modalidad_pago = models.CharField(
        max_length=20, 
        choices=MODALIDAD_PAGO_CHOICES, 
        default='UNA_EXHIBICION', 
        verbose_name="Modalidad de Pago"
    )
    cantidad_plazos = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        verbose_name="Cantidad de Plazos", 
        help_text="Solo aplica si la modalidad es 'A plazos'"
    )
    
    # Campos de checklist para auditoría
    factura_subida = models.BooleanField(default=False, verbose_name="Factura subida")
    comprobante_pago_subido = models.BooleanField(default=False, verbose_name="Comprobante de pago subido")
    lista_para_auditar = models.BooleanField(default=False, verbose_name="Lista para auditar")
    
    # Campos para tracking de quién subió los documentos
    factura_subida_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='facturas_subidas'
    )
    comprobante_subido_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='comprobantes_subidos'
    )
    fecha_factura_subida = models.DateTimeField(null=True, blank=True)
    fecha_comprobante_subido = models.DateTimeField(null=True, blank=True)
    
    # Campos para la administración de documentos
    factura = models.FileField(upload_to='ordenes_compra/facturas/%Y/%m/', null=True, blank=True, verbose_name="Factura (PDF/XML)")
    comprobante_pago = models.FileField(upload_to='ordenes_compra/pagos/%Y/%m/', null=True, blank=True, verbose_name="Comprobante de Pago")
    archivo_opcional = models.FileField(upload_to='ordenes_compra/opcionales/%Y/%m/', null=True, blank=True, verbose_name="Archivo Opcional")

    # Campo de auditoría
    lista_para_auditoria = models.BooleanField(default=False, editable=False, help_text="Se marca automáticamente cuando se suben la factura y el comprobante de pago.")
    
    usuario_creacion = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='ordenes_creadas', 
        verbose_name='Usuario Creador'
    )
    usuario_aprobacion = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='ordenes_aprobadas', 
        verbose_name='Usuario Aprobador'
    )

    def actualizar_estado_auditoria(self):
        """Actualiza el estado de lista_para_auditar basado en los documentos subidos"""
        self.lista_para_auditar = self.factura_subida and self.comprobante_pago_subido
        
        if self.lista_para_auditar and self.estatus == 'APROBADA':
            self.estatus = 'LISTA_PARA_AUDITAR'
        elif not self.lista_para_auditar and self.estatus == 'LISTA_PARA_AUDITAR':
            self.estatus = 'APROBADA'
            
        self.save()

    def save(self, *args, **kwargs):
        if not self.folio:
            last_id = OrdenCompra.objects.all().order_by('id').last()
            next_id = (last_id.id + 1) if last_id else 1
            self.folio = f"OC-{self.empresa.id}-{next_id:05d}"
        
        if self.factura and self.comprobante_pago:
            self.lista_para_auditoria = True
        else:
            self.lista_para_auditoria = False

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Orden de Compra {self.folio} - {self.proveedor.razon_social}"

    # --- PROPIEDADES PARA PAGOS A PLAZOS ---
    
    
    @property
    def es_pago_plazos(self):
        return self.modalidad_pago == 'A_PLAZOS'
    
    @property
    def plazos_programados(self):
        """Genera las fechas programadas de los plazos"""
        if not self.es_pago_plazos or not self.cantidad_plazos:
            return []
        
        plazos = []
        monto_por_plazo = self.total_general / self.cantidad_plazos
        
        for i in range(1, self.cantidad_plazos + 1):
            fecha_plazo = self.fecha_emision + timedelta(days=30 * i)
            plazos.append({
                'numero_plazo': i,
                'fecha_programada': fecha_plazo,
                'monto_programado': monto_por_plazo
            })
        
        return plazos
    
    @property
    def plazos_pagados(self):
        """Obtiene los plazos que ya tienen pagos registrados"""
        if hasattr(self, 'factura_cxp') and self.factura_cxp:
            return self.factura_cxp.pagos.all().order_by('numero_plazo')
        # Usar referencia string para evitar importación circular
        Pago = apps.get_model('cuentas_por_pagar', 'Pago')
        return Pago.objects.none()
    
    @property
    def plazos_pendientes(self):
        """Calcula los plazos pendientes de pago"""
        if not self.es_pago_plazos:
            return []
        
        plazos_pagados_ids = self.plazos_pagados.values_list('numero_plazo', flat=True)
        plazos_pendientes = []
        
        for plazo in self.plazos_programados:
            if plazo['numero_plazo'] not in plazos_pagados_ids:
                plazos_pendientes.append(plazo)
        
        return plazos_pendientes

    # --- PROPIEDADES PARA CÁLCULOS FINANCIEROS ---
    @property
    def moneda_simbolo(self):
        if self.moneda == 'USD':
            return 'US$'
        return '$'

    @property
    def subtotal_bruto(self):
        return sum(
            (detalle.cantidad or Decimal('0')) * (detalle.precio_unitario or Decimal('0'))
            for detalle in self.detalles.all()
        )

    @property
    def total_descuentos(self):
        return sum(
            (detalle.cantidad or Decimal('0')) * (detalle.precio_unitario or Decimal('0')) * ((detalle.descuento or Decimal('0')) / Decimal('100'))
            for detalle in self.detalles.all()
        )

    @property
    def total_subtotal(self):
        return sum(detalle.subtotal for detalle in self.detalles.all())

    @property
    def total_iva(self):
        total = Decimal('0')
        for detalle in self.detalles.all():
            # Cálculo basado en el porcentaje del artículo
            if detalle.articulo and detalle.articulo.porcentaje_iva > 0:
                tasa = detalle.articulo.porcentaje_iva / Decimal('100')
                total += detalle.subtotal * tasa
        return total.quantize(Decimal('0.01'))

    @property
    def total_retenciones(self):
        total = Decimal('0')
        for detalle in self.detalles.all():
            # Cálculo basado en el porcentaje del artículo
            if detalle.articulo and detalle.articulo.porcentaje_retencion_iva > 0:
                tasa = detalle.articulo.porcentaje_retencion_iva / Decimal('100')
                total += detalle.subtotal * tasa
        return total.quantize(Decimal('0.01'))

    @property
    def total_general(self):
        return self.total_subtotal + self.total_iva - self.total_retenciones
    
    class Meta:
        # ... (otras configuraciones meta si tienes) ...
        permissions = [
            ("acceso_compras", "Acceso al Módulo de Compras"),
            ("aprobar_solicitudes", "Puede aprobar solicitudes de compra"),
            ("ver_reportes_compras", "Puede ver reportes de compras"),
        ]


class DetalleOrdenCompra(models.Model):
    orden_compra = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name='detalles')
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    
    @property
    def subtotal(self):
        cantidad = self.cantidad if self.cantidad is not None else Decimal('0')
        precio = self.precio_unitario if self.precio_unitario is not None else Decimal('0')
        descuento = self.descuento or Decimal('0')
        return (cantidad * precio) * (Decimal('1') - (descuento / Decimal('100')))

    def __str__(self):
        return f"{self.cantidad} x {self.articulo.nombre} @ ${self.precio_unitario}"