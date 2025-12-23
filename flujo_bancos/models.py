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
        ingresos = self.movimientos.aggregate(total=Sum('abono'))['total'] or 0
        egresos = self.movimientos.aggregate(total=Sum('cargo'))['total'] or 0
        return self.saldo_inicial + ingresos - egresos

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

    cuenta = models.ForeignKey(Cuenta, on_delete=models.CASCADE, related_name='movimientos', verbose_name="Cuenta")
    fecha = models.DateField(verbose_name="Fecha")
    concepto = models.CharField(max_length=255, verbose_name="Concepto")
    operacion = models.ForeignKey(Operacion, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Operación")
    cargo = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Cargo (Egreso)")
    abono = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Abono (Ingreso)")
    saldo_banco = models.DecimalField(max_digits=15, decimal_places=2, default=0, blank=True, null=True, verbose_name="Saldo")

    # Relaciones Opcionales (para permitir guardar borradores/importados)
    unidad_negocio = models.ForeignKey(UnidadNegocio, on_delete=models.SET_NULL, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    subcategoria = models.ForeignKey(SubCategoria, on_delete=models.SET_NULL, null=True, blank=True)
    
    comentarios = models.TextField(blank=True, null=True)
    tercero = models.CharField(max_length=200, blank=True, null=True)
    
    # Impuestos
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ret_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ret_isr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    auditado = models.BooleanField(default=False)
    comprobante = models.FileField(upload_to='comprobantes/', blank=True, null=True)

    # NUEVO CAMPO ESTATUS
    estatus = models.CharField(max_length=20, choices=ESTATUS_OPCIONES, default='PENDIENTE')

    def clean(self):
        if self.cargo > 0 and self.abono > 0:
            raise ValidationError("Un movimiento no puede tener Cargo y Abono simultáneamente.")

    def save(self, *args, **kwargs):
        # LÓGICA AUTOMÁTICA DE ESTATUS
        # Si tiene subcategoría se considera completo/terminado, si no, pendiente.
        if self.subcategoria:
            self.estatus = 'TERMINADO'
        else:
            self.estatus = 'PENDIENTE'

        # Cálculo simple de saldo histórico (snapshot) si es nuevo
        if not self.pk and self.cuenta and self.saldo_banco == 0:
             monto = self.abono if self.abono > 0 else -self.cargo
             # Nota: Esto toma el saldo actual total, para contabilidad estricta se requiere recálculo cronológico
             self.saldo_banco = self.cuenta.saldo_actual + monto

        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.fecha} - {self.concepto} - {self.estatus}"

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
        ordering = ['-fecha', '-id']
        
        
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