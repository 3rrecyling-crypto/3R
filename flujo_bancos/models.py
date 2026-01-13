from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError

class Cuenta(models.Model):
    OPCIONES_MONEDA = [('MXN', 'Pesos Mexicanos'), ('USD', 'Dólares Americanos')]
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre de la Cuenta")
    moneda = models.CharField(max_length=3, choices=OPCIONES_MONEDA, default='MXN', verbose_name="Moneda")
    saldo_inicial = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Saldo Inicial")

    def __str__(self): return f"{self.nombre} ({self.moneda})"
    
    @property
    def saldo_actual(self):
        # Calculamos el saldo al vuelo usando Abono (ingreso) y Cargo (egreso)
        ingresos = self.movimientos.aggregate(total=Sum('abono'))['total'] or 0
        egresos = self.movimientos.aggregate(total=Sum('cargo'))['total'] or 0
        return self.saldo_inicial + ingresos - egresos

    class Meta:
        verbose_name = "Cuenta"
        verbose_name_plural = "Cuentas"
        # --- AGREGAR ESTO ---
        permissions = [
            ("acceso_flujo_bancos", "Puede acceder al módulo de Bancos y Flujos"),
        ]

# --- RESTO DE TUS MODELOS (Sin cambios) ---
class UnidadNegocio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class Operacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre Operación")
    def __str__(self): return self.nombre

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class SubCategoria(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='subcategorias')
    nombre = models.CharField(max_length=100)
    def __str__(self): return f"{self.categoria.nombre} - {self.nombre}"

class Movimiento(models.Model):
    ESTATUS_OPCIONES = [
        ('PENDIENTE', 'Pendiente (Incompleto)'),
        ('TERMINADO', 'Terminado (Completo)'),
    ]

    # --- CAMBIOS AQUÍ: AGREGAR null=True, blank=True A LOS CAMPOS OBLIGATORIOS ---
    cuenta = models.ForeignKey(
        Cuenta, 
        on_delete=models.CASCADE, 
        related_name='movimientos', 
        verbose_name="Cuenta",
        null=True,  # Permite guardar sin cuenta en la BD
        blank=True  # Permite dejar el campo vacío en el admin/forms
    )
    
    fecha = models.DateField(
        verbose_name="Fecha",
        null=True,  # Permite guardar sin fecha
        blank=True
    )
    
    concepto = models.CharField(
        max_length=255, 
        verbose_name="Concepto",
        null=True,  # Permite guardar sin concepto
        blank=True
    )
    # -----------------------------------------------------------------------------

    operacion = models.ForeignKey(Operacion, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Operación")
    cargo = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Cargo (Egreso)")
    abono = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Abono (Ingreso)")
    saldo_banco = models.DecimalField(max_digits=15, decimal_places=2, default=0, blank=True, null=True, verbose_name="Saldo")
    iva_total_xml = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="IVA Extraído (XML)")
    
    unidad_negocio = models.ForeignKey(UnidadNegocio, on_delete=models.SET_NULL, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    subcategoria = models.ForeignKey(SubCategoria, on_delete=models.SET_NULL, null=True, blank=True)
    
    comentarios = models.TextField(blank=True, null=True)
    tercero = models.CharField(max_length=200, blank=True, null=True)
    
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ret_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ret_isr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    auditado = models.BooleanField(default=False)
    comprobante = models.FileField(upload_to='comprobantes/', blank=True, null=True)

    estatus = models.CharField(max_length=20, choices=ESTATUS_OPCIONES, default='PENDIENTE')

    def clean(self):
        # Validación opcional: solo si existen valores, valida.
        # Si son 0 o None, no lanza error para permitir el guardado.
        if self.cargo and self.abono and self.cargo > 0 and self.abono > 0:
            raise ValidationError("Un movimiento no puede tener Cargo y Abono simultáneamente.")

    def save(self, *args, **kwargs):
        if self.subcategoria:
            self.estatus = 'TERMINADO'
        else:
            self.estatus = 'PENDIENTE'

        # Cálculo de saldo (Solo si hay cuenta asignada)
        if not self.pk and self.cuenta and self.saldo_banco == 0:
             monto = self.abono if self.abono > 0 else -self.cargo
             self.saldo_banco = self.cuenta.saldo_actual + monto

        # Quitamos self.clean() de aquí para evitar bloqueos estrictos al guardar borradores
        # self.clean() 
        super().save(*args, **kwargs)

    def __str__(self):
        # Manejo seguro de string por si fecha o concepto son nulos
        fecha_str = self.fecha if self.fecha else "Sin fecha"
        concepto_str = self.concepto if self.concepto else "Sin concepto"
        return f"{fecha_str} - {concepto_str} - {self.estatus}"

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
        ordering = ['-fecha', 'id']
        
        
class Tercero(models.Model):
    TIPO_OPCIONES = [
        ('ingreso', 'Cliente (Ingreso)'),
        ('egreso', 'Proveedor (Egreso)'),
    ]
    nombre = models.CharField(max_length=200, unique=True, verbose_name="Nombre / Razón Social")
    tipo = models.CharField(max_length=10, choices=TIPO_OPCIONES, verbose_name="Tipo")
    celular = models.CharField(max_length=20, blank=True, null=True, verbose_name="Celular")

    def __str__(self):
        return self.nombre
    
    
class ComprobanteFiscal(models.Model):
    movimiento = models.ForeignKey(Movimiento, related_name='comprobantes', on_delete=models.CASCADE)
    archivo_xml = models.FileField(upload_to='xmls/%Y/%m/', blank=True, null=True)
    archivo_pdf = models.FileField(upload_to='pdfs/%Y/%m/', blank=True, null=True)
    uuid = models.CharField(max_length=36, blank=True, null=True, verbose_name="Folio Fiscal (UUID)")
    monto_iva = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comprobante {self.uuid} - {self.movimiento}"