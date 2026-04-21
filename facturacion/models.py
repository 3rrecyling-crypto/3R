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
    direccion = models.TextField(verbose_name="Dirección Completa", blank=True, null=True)
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
    
    TIPO_COMPROBANTE_CHOICES = [
        ('I', 'I - Ingreso (Factura)'),
        ('E', 'E - Egreso (Nota de Crédito)'),
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
    id_fiscalapi = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name="ID Interno FiscalAPI"
    )
    tipo_relacion = models.CharField(max_length=5, blank=True, null=True, verbose_name="Tipo Relación")
    uuid_relacionado = models.CharField(max_length=100, blank=True, null=True, verbose_name="UUID Relacionado")
    tipo_comprobante = models.CharField(
        max_length=1, 
        choices=TIPO_COMPROBANTE_CHOICES, 
        default='I',
        verbose_name="Tipo de Comprobante"
    )
    # ===
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
    
    objeto_impuesto = models.CharField(
        max_length=5, 
        default='02', 
        verbose_name="Objeto Impuesto",
        help_text="01: No objeto, 02: Sí objeto"
    )
    
    # --- MONTOS (Suma total en pesos) ---
    iva_importe = models.DecimalField(max_digits=14, decimal_places=2, default=0)     # Total Traslados
    iva_ret_importe = models.DecimalField(max_digits=14, decimal_places=2, default=0) # Total Retenciones

    # --- NUEVOS CAMPOS: IDENTIDAD DEL IMPUESTO ---
    # Guardan QUÉ impuesto es (001, 002, 003) y CUÁL es su tasa exacta
    
    # Traslado (Cobrado)
    traslado_impuesto_clave = models.CharField(max_length=3, default="002") # 002=IVA, 003=IEPS
    traslado_tasa = models.DecimalField(max_digits=8, decimal_places=6, default=0.160000)
    
    # Retención (Descontado)
    retencion_impuesto_clave = models.CharField(max_length=3, default="002") # 001=ISR, 002=IVA
    retencion_tasa = models.DecimalField(max_digits=8, decimal_places=6, default=0.000000)

    def __str__(self):
        return f"{self.descripcion} - ${self.importe}"
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
    

# facturacion/models.py

class CatalogoSAT(models.Model):
    TIPO_CHOICES = [
        ('ClaveProdServ', 'Clave Producto/Servicio'),
        ('ClaveUnidad', 'Clave Unidad'),
        ('UsoCFDI', 'Uso CFDI'),
        ('FormaPago', 'Forma de Pago'),
        ('MetodoPago', 'Método de Pago'),
    ]
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    clave = models.CharField(max_length=20, db_index=True) # Indexado para búsqueda rápida
    descripcion = models.CharField(max_length=255)
    
    # Opcional: Palabras clave para búsqueda (ej. "computadora" para la clave de "equipos informáticos")
    palabras_clave = models.TextField(blank=True, null=True) 

    def __str__(self):
        return f"{self.clave} - {self.descripcion}"

    class Meta:
        verbose_name = "Catálogo SAT"
        verbose_name_plural = "Catálogos SAT"
        # Garantiza que no haya duplicados de clave por tipo
        unique_together = ('tipo', 'clave')
        
class SatRegimenFiscal(models.Model):
    clave = models.CharField(max_length=10, primary_key=True, verbose_name="Clave")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    
    def __str__(self):
        return f"{self.clave} - {self.descripcion}"

class SatUsoCFDI(models.Model):
    clave = models.CharField(max_length=10, primary_key=True, verbose_name="Clave")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    
    def __str__(self):
        return f"{self.clave} - {self.descripcion}"

class SatTipoComprobante(models.Model):
    clave = models.CharField(max_length=5, primary_key=True, verbose_name="Clave")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")

    def __str__(self):
        return f"{self.clave} - {self.descripcion}"

class SatObjetoImpuesto(models.Model):
    clave = models.CharField(max_length=5, primary_key=True, verbose_name="Clave")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")

    def __str__(self):
        return f"{self.clave} - {self.descripcion}"

class SatImpuesto(models.Model):
    clave = models.CharField(max_length=5, primary_key=True, verbose_name="Clave")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    
    def __str__(self):
        return f"{self.clave} - {self.descripcion}"
    
        
class SeriePersonalizada(models.Model):
    nombre = models.CharField(max_length=15, unique=True, verbose_name="Serie / Folio")
    descripcion = models.CharField(max_length=100, blank=True, null=True)
    activa = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Serie Personalizada"
        verbose_name_plural = "Series Personalizadas"
        
class Estado(models.Model):
    # Ejemplo: c_Estado="NLE", Nombre="Nuevo León"
    clave = models.CharField(max_length=10, unique=True) 
    nombre = models.CharField(max_length=100)
    pais = models.CharField(max_length=10, default="MEX")

    def __str__(self):
        return self.nombre

class Municipio(models.Model):
    # Ejemplo: c_Municipio="014", Estado="NLE" -> "Monterrey"
    estado = models.ForeignKey(Estado, on_delete=models.CASCADE, related_name='municipios')
    clave = models.CharField(max_length=10) 
    nombre = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.nombre} ({self.estado.clave})"

class Colonia(models.Model):
    # Ejemplo: c_Colonia="1234", CP="64000", Nombre="Centro"
    clave = models.CharField(max_length=10)
    codigo_postal = models.CharField(max_length=10, db_index=True)
    nombre = models.CharField(max_length=255)

    # Opcional: Relaciones directas si logramos cruzarlas
    # municipio = models.ForeignKey(Municipio, ...) 

    def __str__(self):
        return f"{self.codigo_postal} - {self.nombre}"

class CodigoPostalFiscal(models.Model):
    """
    IMPORTANTE: Esta tabla vincula el CP con el Estado y Municipio.
    Necesitarás la hoja 'c_CodigoPostal' del catálogo del SAT.
    """
    codigo = models.CharField(max_length=10, unique=True, db_index=True)
    estado = models.ForeignKey(Estado, on_delete=models.CASCADE)
    municipio = models.ForeignKey(Municipio, on_delete=models.CASCADE)

    def __str__(self):
        return self.codigo
    
from django.db import models
from django.contrib.auth.models import User

class ProductoServicio(models.Model):
    """
    Catálogo de Productos y Servicios con configuración fiscal detallada.
    Permite definir tasas de IVA, Retenciones de IVA e ISR por cada ítem.
    """
    TIPO_CHOICES = [
        ('P', 'Producto'),
        ('S', 'Servicio'),
    ]

    OBJETO_IMPUESTO_CHOICES = [
        ('01', '01 - No objeto de impuesto'),
        ('02', '02 - Sí objeto de impuesto'),
        ('03', '03 - Sí objeto de impuesto y no obligado al desglose'),
    ]

    # --- DATOS GENERALES ---
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='productos_catalogo')
    codigo_interno = models.CharField(max_length=20, blank=True, null=True, verbose_name="Código Interno / SKU")
    nombre = models.CharField(max_length=255, verbose_name="Nombre Corto / Alias")
    tipo = models.CharField(max_length=1, choices=TIPO_CHOICES, default='P', verbose_name="Tipo")
    
    # --- DATOS SAT (REQUERIDOS PARA TIMBRADO) ---
    clave_prod_serv = models.CharField(max_length=20, default="01010101", verbose_name="Clave Prod/Serv SAT", help_text="Ej. 84111506")
    clave_unidad = models.CharField(max_length=10, default="H87", verbose_name="Clave Unidad SAT", help_text="Ej. E48, H87")
    descripcion_sat = models.TextField(verbose_name="Descripción para Factura", help_text="Esta es la descripción que saldrá en el PDF/XML")
    
    # --- PRECIOS ---
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio Unitario")

    # --- CONFIGURACIÓN FISCAL AVANZADA ---
    objeto_impuesto = models.CharField(max_length=5, choices=OBJETO_IMPUESTO_CHOICES, default='02', verbose_name="Objeto Impuesto")

    # 1. IMPUESTOS TRASLADADOS (IVA / IEPS)
    permite_iva = models.BooleanField(default=True, verbose_name="Aplica IVA")
    iva_tasa = models.DecimalField(max_digits=6, decimal_places=4, default=0.1600, verbose_name="Tasa IVA (0.16, 0.08, 0.00)")
    
    permite_ieps = models.BooleanField(default=False, verbose_name="Aplica IEPS")
    ieps_tasa = models.DecimalField(max_digits=6, decimal_places=4, default=0.0000, verbose_name="Tasa IEPS", blank=True, null=True)

    # 2. IMPUESTOS RETENIDOS (IVA / ISR)
    permite_ret_iva = models.BooleanField(default=False, verbose_name="Retener IVA")
    tasa_ret_iva = models.DecimalField(max_digits=6, decimal_places=4, default=0.0000, verbose_name="Tasa Ret. IVA", help_text="Ej. 0.0400 para Fletes, 0.1067 para Honorarios")

    permite_ret_isr = models.BooleanField(default=False, verbose_name="Retener ISR")
    tasa_ret_isr = models.DecimalField(max_digits=6, decimal_places=4, default=0.0000, verbose_name="Tasa Ret. ISR", help_text="Ej. 0.0125 para RESICO, 0.1000 para Honorarios")
    impuesto_traslado = models.ForeignKey(
        'CatalogoImpuesto', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='productos_traslado',
        limit_choices_to={'categoria': 'Traslado', 'activo': True},
        verbose_name="Impuesto Traslado (IVA/IEPS)"
    )
    
    impuesto_retencion = models.ForeignKey(
        'CatalogoImpuesto', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='productos_retencion',
        limit_choices_to={'categoria': 'Retencion', 'activo': True},
        verbose_name="Impuesto Retención (Opcional)"
    )
    # --- CONTROL ---
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.codigo_interno or 'S/C'} - {self.nombre} (${self.precio_unitario})"

    class Meta:
        verbose_name = "Producto / Servicio"
        verbose_name_plural = "Catálogo Productos"
        ordering = ['nombre']
        
class CatalogoImpuesto(models.Model):
    TIPO_IMPUESTO = [
        ('IVA', 'IVA'),
        ('ISR', 'ISR'),
        ('IEPS', 'IEPS'),
    ]
    TIPO_FACTOR = [
        ('Tasa', 'Tasa'),
        ('Cuota', 'Cuota'),
        ('Exento', 'Exento'),
    ]
    CATEGORIA = [
        ('Traslado', 'Traslado (Cobrado)'),
        ('Retencion', 'Retención (Descontado)'),
    ]

    nombre = models.CharField(max_length=50, help_text="Ej. IVA 16%, Retención ISR 1.25%")
    impuesto = models.CharField(max_length=10, choices=TIPO_IMPUESTO, default='IVA')
    tipo_factor = models.CharField(max_length=10, choices=TIPO_FACTOR, default='Tasa')
    tasa_o_cuota = models.DecimalField(max_digits=10, decimal_places=6, default=0.000000, help_text="Para 16% poner 0.160000")
    categoria = models.CharField(max_length=20, choices=CATEGORIA, default='Traslado')
    activo = models.BooleanField(default=True)

    def __str__(self):
        val_str = f"{self.tasa_o_cuota:.4f}" if self.tipo_factor != 'Exento' else 'Exento'
        return f"{self.nombre} ({self.categoria} - {val_str})"

    class Meta:
        verbose_name = "Impuesto / Retención"
        verbose_name_plural = "Catálogo de Impuestos"
        ordering = ['categoria', 'impuesto', 'tasa_o_cuota']