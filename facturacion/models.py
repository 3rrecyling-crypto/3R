# facturacion/models.py

from django.db import models
from ternium.models import Empresa, Cliente, Remision
from django.contrib.auth.models import User
from django.utils import timezone

# === OPCIONES SAT ===
REGIMEN_FISCAL_CHOICES = [
    ('601', '601 - General de Ley Personas Morales'),
    ('612', '612 - Personas Físicas con Actividades Empresariales'),
    ('626', '626 - Régimen Simplificado de Confianza'),
]

USO_CFDI_CHOICES = [
    ('G01', 'G01 - Adquisición de mercancías'),
    ('G03', 'G03 - Gastos en general'),
    ('I01', 'I01 - Construcciones'),
    ('P01', 'P01 - Por definir'),
    ('S01', 'S01 - Sin efectos fiscales'),
    ('I04', 'I04 - Equipo de computo y accesorios'),
]

class DatosFiscales(models.Model):
    """
    Información fiscal para facturación.
    """
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='facturacion_datos')
    rfc = models.CharField(max_length=13, verbose_name="RFC")
    razon_social = models.CharField(max_length=255, verbose_name="Razón Social")
    regimen_fiscal = models.CharField(max_length=100, verbose_name="Régimen Fiscal", blank=True, null=True)
    codigo_postal = models.CharField(max_length=10, verbose_name="Código Postal")
    direccion = models.TextField(verbose_name="Dirección Fiscal", blank=True, null=True)
    email_contacto = models.EmailField(verbose_name="Email para envío de factura", blank=True, null=True)
    
    uso_cfdi = models.CharField(
        max_length=5, 
        default='G03', 
        choices=USO_CFDI_CHOICES,
        verbose_name="Uso de CFDI Preferido"
    )

    # Campos internos para relacionar con tu sistema
    es_emisor = models.BooleanField(default=False, help_text="Marcar si estos son TUS datos fiscales")
    cliente_interno = models.OneToOneField(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='datos_fiscales')

    def __str__(self):
        return f"{self.rfc} - {self.razon_social}"

    class Meta:
        verbose_name = "Datos Fiscales"
        verbose_name_plural = "Datos Fiscales"

class Factura(models.Model):
    """
    Modelo para almacenar las facturas generadas.
    """
    ESTADOS = [
        ('pendiente', 'Pendiente de Pago/Timbrado'),
        ('pagada', 'Pagada'),
        ('timbrado', 'Timbrado (Emitida)'),
        ('cancelada', 'Cancelada'),
        ('error', 'Error al Timbrar'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='facturas_usuario', null=True, blank=True)
    
    # Relaciones Fiscales
    emisor = models.ForeignKey(DatosFiscales, on_delete=models.PROTECT, related_name='facturas_emitidas', null=True)
    receptor = models.ForeignKey(DatosFiscales, on_delete=models.PROTECT, related_name='facturas_recibidas', null=True)
    
    # Relación con Ternium (Remisiones que ampara esta factura)
    remisiones = models.ManyToManyField(Remision, blank=True, related_name='facturas')

    # Archivos
    archivo_pdf = models.FileField(upload_to='facturas_emitidas/pdf/', verbose_name="PDF Factura", blank=True, null=True)
    archivo_xml = models.FileField(upload_to='facturas_emitidas/xml/', verbose_name="XML Factura", blank=True, null=True)
    
    # Datos del SAT
    folio_fiscal = models.CharField(max_length=100, blank=True, null=True, verbose_name="Folio Fiscal (UUID)")
    serie = models.CharField(max_length=10, blank=True, null=True, verbose_name="Serie")
    folio = models.CharField(max_length=20, blank=True, null=True, verbose_name="Folio Interno")
    
    # Importes
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    impuestos_trasladados = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) # IVA
    impuestos_retenidos = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)   # Retenciones
    monto_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Total")
    
    fecha_emision = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Emisión")
    fecha_timbrado = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    
    # Conceptos básicos para CFDI 4.0
    moneda = models.CharField(max_length=5, default='MXN')
    tipo_cambio = models.DecimalField(max_digits=10, decimal_places=4, default=1.0) # <--- AGREGADO
    forma_pago = models.CharField(max_length=5, default='99')
    metodo_pago = models.CharField(max_length=5, default='PPD')
    uso_cfdi = models.CharField(max_length=5, default='G03') # <--- AGREGADO

    def __str__(self):
        return f"Factura {self.folio or self.id} - {self.monto_total}"

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"

class ConceptoFactura(models.Model):
    factura = models.ForeignKey(Factura, related_name='conceptos', on_delete=models.CASCADE)
    clave_prod_serv = models.CharField(max_length=15, default="01010101")
    clave_unidad = models.CharField(max_length=5, default="H87")
    cantidad = models.DecimalField(max_digits=12, decimal_places=4)
    unidad = models.CharField(max_length=50)
    descripcion = models.TextField()
    valor_unitario = models.DecimalField(max_digits=14, decimal_places=4)
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    
    iva_importe = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    iva_ret_importe = models.DecimalField(max_digits=14, decimal_places=2, default=0)

class ComplementoPago(models.Model):
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name='complementos_pago')
    fecha_pago = models.DateTimeField(default=timezone.now)
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto Pagado")
    forma_pago = models.CharField(max_length=5, default='03', verbose_name="Forma de Pago SAT")
    num_operacion = models.CharField(max_length=100, blank=True, null=True, verbose_name="Número de Operación")
    archivo_pdf = models.FileField(upload_to='pagos/pdf/', blank=True, null=True)
    archivo_xml = models.FileField(upload_to='pagos/xml/', blank=True, null=True)
    uuid_pago = models.CharField(max_length=100, blank=True, null=True, verbose_name="UUID del Complemento")

    def __str__(self):
        return f"Pago de ${self.monto} para Factura {self.factura.id}"

    class Meta:
        verbose_name = "Complemento de Pago"
        verbose_name_plural = "Complementos de Pago"