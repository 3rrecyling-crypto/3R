# compras/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal # <-- AÑADE ESTA LÍNEA
from ternium.models import Empresa # <-- IMPORTAMOS TU MODELO EXISTENTE


# --- 1. CATÁLOGOS BASE ---

class Proveedor(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="proveedores", help_text="Empresa a la que pertenece este proveedor")
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
        # CAMBIO 1: Evita que una categoría sea su propia categoría padre.
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
    nombre = models.CharField(max_length=50, unique=True) # Ej: "Pieza", "Kg", "Litro", "Servicio"
    abreviatura = models.CharField(max_length=10, unique=True) # Ej: "pz", "kg", "L", "serv"

    def __str__(self):
        return f"{self.nombre} ({self.abreviatura})"

# --- INICIO DEL CÓDIGO A AGREGAR ---

@receiver(post_migrate)
def poblar_unidades_medida(sender, **kwargs):
    """
    Esta función se ejecuta después de cada migración y puebla la tabla 
    UnidadMedida con datos iniciales si y solo si la tabla está vacía.
    """
    # Se asegura de que el código solo se ejecute para la app 'compras'
    if sender.name == 'compras':
        UnidadMedida = sender.get_model('UnidadMedida')
        
        # Condición clave: Solo se ejecuta si no hay registros en la tabla.
        if not UnidadMedida.objects.exists():
            unidades_a_crear = [
                # Unidades de conteo
                UnidadMedida(nombre='Pieza', abreviatura='PZA'),
                UnidadMedida(nombre='Unidad', abreviatura='UNID'),
                UnidadMedida(nombre='Paquete', abreviatura='PAQ'),
                UnidadMedida(nombre='Caja', abreviatura='CJA'),
                UnidadMedida(nombre='Docena', abreviatura='DOC'),
                UnidadMedida(nombre='Par', abreviatura='PAR'),
                
                # Unidades de peso
                UnidadMedida(nombre='Kilogramo', abreviatura='KG'),
                UnidadMedida(nombre='Gramo', abreviatura='GR'),
                UnidadMedida(nombre='Tonelada', abreviatura='TON'),
                UnidadMedida(nombre='Libra', abreviatura='LB'),

                # Unidades de volumen
                UnidadMedida(nombre='Litro', abreviatura='LT'),
                UnidadMedida(nombre='Mililitro', abreviatura='ML'),
                UnidadMedida(nombre='Galón', abreviatura='GAL'),
                
                # Unidades de longitud
                UnidadMedida(nombre='Metro', abreviatura='M'),
                UnidadMedida(nombre='Centímetro', abreviatura='CM'),
                UnidadMedida(nombre='Milímetro', abreviatura='MM'),
                UnidadMedida(nombre='Pulgada', abreviatura='IN'),

                # Unidades para servicios y tiempo
                UnidadMedida(nombre='Servicio', abreviatura='SERV'),
                UnidadMedida(nombre='Hora', abreviatura='HR'),
                UnidadMedida(nombre='Día', abreviatura='DIA'),
                UnidadMedida(nombre='Mes', abreviatura='MES'),
                UnidadMedida(nombre='Lote', abreviatura='LOTE'),

                # Otras unidades comunes
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
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    sku = models.CharField(max_length=100, blank=True, null=True, help_text="Identificador único del producto o servicio por empresa")
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    unidad_medida = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, null=True, blank=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='PRODUCTO')
    
    # Impuestos
    lleva_iva = models.BooleanField(default=True, verbose_name="¿Aplica IVA?")
    lleva_retencion_iva = models.BooleanField(default=False, verbose_name="¿Aplica retención de IVA?")
    
    proveedores = models.ManyToManyField(Proveedor, through='ArticuloProveedor', related_name='articulos_provistos')
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.sku or 'Sin SKU'}) - {self.empresa.nombre}"
    
    def clean(self):
        # CAMBIO 2: Asegura que el SKU no se repita dentro de la misma empresa.
        # Esta validación a nivel de aplicación es más flexible que una restricción de base de datos,
        # ya que maneja correctamente los valores nulos (múltiples artículos pueden tener SKU nulo).
        super().clean()
        if self.sku: # Solo valida si se proporciona un SKU
            qs = Articulo.objects.filter(empresa=self.empresa, sku=self.sku)
            if self.pk:
                qs = qs.exclude(pk=self.pk) # Excluir el propio objeto al editar
            if qs.exists():
                raise ValidationError({
                    'sku': f"Ya existe otro artículo con el SKU '{self.sku}' en la empresa '{self.empresa.nombre}'."
                })
    
    class Meta:
        # Un artículo tiene un nombre único por empresa. La unicidad del SKU se valida en el método clean().
        unique_together = ('empresa', 'nombre') 


class ArticuloProveedor(models.Model):
    """ Modelo intermedio para asignar múltiples proveedores a un artículo con precios específicos. """
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
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
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
        ('CANCELADA', 'Cancelada'),
        ('AUDITADA', 'Auditada'),
    )
    
    # --- INICIO DE LA MODIFICACIÓN ---
    MONEDA_CHOICES = (
        ('MXN', 'MXN - Pesos Mexicanos'),
        ('USD', 'USD - Dólares Americanos'),
    )
    # --- FIN DE LA MODIFICACIÓN ---

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

    # --- INICIO DE CAMPOS AÑADIDOS ---
    
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


    def save(self, *args, **kwargs):
        if not self.folio:
            last_id = OrdenCompra.objects.all().order_by('id').last()
            next_id = (last_id.id + 1) if last_id else 1
            self.folio = f"OC-{self.empresa.id}-{next_id:05d}"
        
        # --- LÓGICA DE AUDITORÍA AÑADIDA ---
        if self.factura and self.comprobante_pago:
            self.lista_para_auditoria = True
        else:
            self.lista_para_auditoria = False
        # --- FIN LÓGICA DE AUDITORÍA ---

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Orden de Compra {self.folio} - {self.proveedor.razon_social}"

    @property
    def total_subtotal(self):
        return sum(detalle.subtotal for detalle in self.detalles.all())

    @property
    def total_iva(self):
        total = 0
        for detalle in self.detalles.all():
            if detalle.articulo.lleva_iva:
                total += detalle.subtotal * Decimal('0.16')
        return total

    @property
    def total_retenciones(self):
        total = 0
        for detalle in self.detalles.all():
            if detalle.articulo.lleva_retencion_iva:
                total += detalle.subtotal * Decimal('0.106667')
        return total

    @property
    def total_general(self):
        return self.total_subtotal + self.total_iva - self.total_retenciones
 
    @property
    def moneda_simbolo(self):
        """ Devuelve el símbolo común para la moneda. """
        if self.moneda == 'USD':
            return 'US$'
        return '$'

    @property
    def subtotal_bruto(self):
        """ Calcula el subtotal ANTES de aplicar descuentos. """
        return sum(
            (detalle.cantidad or Decimal('0')) * (detalle.precio_unitario or Decimal('0'))
            for detalle in self.detalles.all()
        )

    @property
    def total_descuentos(self):
        """ Calcula el valor monetario total de los descuentos aplicados. """
        return sum(
            (detalle.cantidad or Decimal('0')) * (detalle.precio_unitario or Decimal('0')) * ((detalle.descuento or Decimal('0')) / Decimal('100'))
            for detalle in self.detalles.all()
        )

    @property
    def total_subtotal(self):
        """
        Calcula el subtotal NETO (después de descuentos).
        Este es el valor sobre el cual se calculan los impuestos.
        """
        return sum(detalle.subtotal for detalle in self.detalles.all())

    @property
    def total_iva(self):
        """ Calcula el IVA total basado en el subtotal neto de cada artículo aplicable. """
        total = Decimal('0')
        for detalle in self.detalles.all():
            if detalle.articulo and detalle.articulo.lleva_iva:
                # El IVA se calcula sobre el subtotal ya con descuento.
                total += detalle.subtotal * Decimal('0.16')
        return total.quantize(Decimal('0.01'))

    @property
    def total_retenciones(self):
        """ Calcula las retenciones totales basadas en el subtotal neto. """
        total = Decimal('0')
        for detalle in self.detalles.all():
            if detalle.articulo and detalle.articulo.lleva_retencion_iva:
                total += detalle.subtotal * (Decimal('2') / Decimal('3')) * Decimal('0.16') # 2/3 partes del IVA
        return total.quantize(Decimal('0.01'))

    @property
    def total_general(self):
        """ Calcula el gran total de la orden de compra. """
        return self.total_subtotal + self.total_iva - self.total_retenciones    



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
    
