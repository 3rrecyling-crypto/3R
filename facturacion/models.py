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
    
    # --- CORREGIDO AQUI (De 5 a 50) ---
    uso_cfdi = models.CharField(
        max_length=50,  
        default='G03', 
        choices=USO_CFDI_CHOICES,
        verbose_name="Uso de CFDI Preferido"
    )

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
    emisor = models.ForeignKey(DatosFiscales, on_delete=models.PROTECT, related_name='facturas_emitidas', null=True)
    receptor = models.ForeignKey(DatosFiscales, on_delete=models.PROTECT, related_name='facturas_recibidas', null=True)
    remisiones = models.ManyToManyField(Remision, blank=True, related_name='facturas')

    archivo_pdf = models.FileField(upload_to='facturas_emitidas/pdf/', verbose_name="PDF Factura", blank=True, null=True)
    archivo_xml = models.FileField(upload_to='facturas_emitidas/xml/', verbose_name="XML Factura", blank=True, null=True)
    
    folio_fiscal = models.CharField(max_length=100, blank=True, null=True, verbose_name="Folio Fiscal (UUID)")
    serie = models.CharField(max_length=10, blank=True, null=True, verbose_name="Serie")
    folio = models.CharField(max_length=20, blank=True, null=True, verbose_name="Folio Interno")
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    impuestos_trasladados = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) 
    impuestos_retenidos = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)   
    monto_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Total")
    
    fecha_emision = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Emisión")
    fecha_timbrado = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    
    # --- CORREGIDO AQUI (De 5 a 50) ---
    moneda = models.CharField(max_length=50, default='MXN')
    tipo_cambio = models.DecimalField(max_digits=10, decimal_places=4, default=1.0)
    forma_pago = models.CharField(max_length=50, default='99')
    metodo_pago = models.CharField(max_length=50, default='PPD')
    uso_cfdi = models.CharField(max_length=50, default='G03')

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
    """
    ENCABEZADO DEL PAGO (Nivel CFDI)
    Representa la recepción del dinero (bancario).
    Puede pagar una o muchas facturas.
    """
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    # Cambiamos la relación: El pago se hace a un CLIENTE (Receptor), no a una factura específica
    receptor = models.ForeignKey(DatosFiscales, on_delete=models.PROTECT, verbose_name="Cliente que paga")
    
    # --- Consecutivo Interno (CP-1, CP-2...) ---
    serie = models.CharField(max_length=10, default='CP')
    folio = models.PositiveIntegerField(verbose_name="Folio Interno")
    
    # --- Datos del Pago ---
    fecha_pago = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Pago")
    forma_pago = models.CharField(max_length=50, default='03', verbose_name="Forma de Pago SAT")
    moneda = models.CharField(max_length=10, default='MXN')
    tipo_cambio = models.DecimalField(max_digits=10, decimal_places=4, default=1.0)
    
    # ESTE ES EL CAMPO QUE DABA ERROR (Antes se llamaba 'monto')
    monto_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto Total Recibido")
    
    num_operacion = models.CharField(max_length=100, blank=True, null=True, verbose_name="Número de Operación")
    
    # --- Campos SAT 2025 ---
    version = models.CharField(max_length=10, default='2.0', editable=False)
    tipo_cadena_pago = models.CharField(max_length=2, blank=True, null=True)
    certificado_pago = models.TextField(blank=True, null=True)
    sello_pago = models.TextField(blank=True, null=True)
    
    # --- Timbrado ---
    uuid = models.CharField(max_length=100, blank=True, null=True, verbose_name="Folio Fiscal (UUID)")
    archivo_pdf = models.FileField(upload_to='pagos/pdf/', blank=True, null=True)
    archivo_xml = models.FileField(upload_to='pagos/xml/', blank=True, null=True)
    timbrado = models.BooleanField(default=False)
    fecha_timbrado = models.DateTimeField(blank=True, null=True)
    no_certificado_sat = models.CharField(max_length=20, blank=True, null=True)
    sello_sat = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.serie}-{self.folio} (${self.monto_total})"

    class Meta:
        verbose_name = "Complemento de Pago (REP)"
        verbose_name_plural = "Complementos de Pago (REP)"

class PagoDoctoRelacionado(models.Model):
    """
    DETALLE DEL PAGO (Documentos Relacionados)
    Aquí se desglosa cuánto dinero se va a cada factura.
    """
    complemento = models.ForeignKey(ComplementoPago, on_delete=models.CASCADE, related_name='documentos_relacionados')
    factura = models.ForeignKey(Factura, on_delete=models.PROTECT, related_name='pagos_recibidos')
    
    # --- Cálculos SAT ---
    numero_parcialidad = models.PositiveIntegerField()
    saldo_anterior = models.DecimalField(max_digits=12, decimal_places=2)
    importe_pagado = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Importe aplicado")
    saldo_insoluto = models.DecimalField(max_digits=12, decimal_places=2)
    
    moneda_dr = models.CharField(max_length=10, default='MXN')
    equivalencia_dr = models.DecimalField(max_digits=10, decimal_places=6, default=1.0)

    def __str__(self):
        return f"Pago a F-{self.factura.folio} (${self.importe_pagado})"