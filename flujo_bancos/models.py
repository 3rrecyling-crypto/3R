from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError

class Cuenta(models.Model):
    OPCIONES_MONEDA = [
        ('MXN', 'Pesos Mexicanos'),
        ('USD', 'Dólares Americanos'),
    ]
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre de la Cuenta")
    moneda = models.CharField(max_length=3, choices=OPCIONES_MONEDA, default='MXN', verbose_name="Moneda")
    saldo_inicial = models.DecimalField(max_digits=15, decimal_places=3, default=0.00, verbose_name="Saldo Inicial")

    def __str__(self):
        return f"{self.nombre} ({self.moneda})"

    @property
    def saldo_actual(self):
        # Calculamos el saldo al vuelo usando Abono (ingreso) y Cargo (egreso)
        ingresos = self.movimientos.aggregate(total=Sum('abono'))['total'] or 0
        egresos = self.movimientos.aggregate(total=Sum('cargo'))['total'] or 0
        return self.saldo_inicial + ingresos - egresos

    class Meta:
        verbose_name = "Cuenta"
        verbose_name_plural = "Cuentas"

# --- RESTO DE TUS MODELOS (Sin cambios) ---
class UnidadNegocio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class Operacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class SubCategoria(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='subcategorias')
    nombre = models.CharField(max_length=100)
    def __str__(self): return f"{self.categoria.nombre} - {self.nombre}"

class Movimiento(models.Model):
    cuenta = models.ForeignKey(Cuenta, on_delete=models.CASCADE, related_name='movimientos', verbose_name="Cuenta")
    fecha = models.DateField(verbose_name="Fecha")
    concepto = models.CharField(max_length=255, verbose_name="Concepto / Referencia")
    
    cargo = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Cargo (Egreso)")
    abono = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Abono (Ingreso)")
    saldo_banco = models.DecimalField(max_digits=15, decimal_places=2, default=0, blank=True, null=True, verbose_name="Saldo")

    unidad_negocio = models.ForeignKey(UnidadNegocio, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Unidad de Negocio")
    operacion = models.ForeignKey(Operacion, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Operación")
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Categoría")
    subcategoria = models.ForeignKey(SubCategoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Subcategoría")
    
    comentarios = models.TextField(blank=True, null=True, verbose_name="Comentarios")
    tercero = models.CharField(max_length=200, blank=True, null=True, verbose_name="A quién se pagó / De quién se recibió")
    
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="IVA")
    ret_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Retención IVA")
    ret_isr = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Retención ISR")
    auditado = models.BooleanField(
        default=False, 
        help_text="Indica si el movimiento ha sido revisado y no puede ser modificado ni eliminado."
    )
    comprobante = models.FileField(upload_to='comprobantes/', blank=True, null=True, verbose_name="Adjuntar Comprobante")

    def clean(self):
        if self.cargo > 0 and self.abono > 0:
            raise ValidationError("Un movimiento no puede tener Cargo y Abono simultáneamente.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        tipo = "Egreso" if self.cargo > 0 else "Ingreso"
        monto = self.cargo if self.cargo > 0 else self.abono
        return f"{self.fecha} - {tipo} - ${monto}"

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
        ordering = ['-fecha']
        
        
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