from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal


class Patio(models.Model):
    """Cada patio/sucursal tiene su propia bomba y gestión independiente."""
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Patio")
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código (ej: MTY, CHI)")
    direccion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Patio / Sucursal"
        verbose_name_plural = "Patios / Sucursales"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class PerfilUsuarioDiesel(models.Model):
    """Vincula un usuario a uno o más patios. Si es_global=True puede ver todo."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_diesel')
    patios = models.ManyToManyField(Patio, blank=True, related_name='usuarios')
    es_global = models.BooleanField(default=False, verbose_name="Acceso Global (ve todos los patios)")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"

    def get_patios_permitidos(self):
        if self.es_global:
            return Patio.objects.filter(activo=True)
        return self.patios.filter(activo=True)


class ProveedorDiesel(models.Model):
    nombre = models.CharField(max_length=150, verbose_name="Nombre del Proveedor")
    rfc = models.CharField(max_length=13, blank=True, verbose_name="RFC")
    contacto = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proveedor de Combustible"
        verbose_name_plural = "Proveedores de Combustible"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Unidad(models.Model):
    numero_economico = models.CharField(max_length=50, unique=True, verbose_name="Número Económico")
    descripcion = models.CharField(max_length=255, blank=True, null=True, verbose_name="Descripción / Alias")
    tipo = models.CharField(max_length=50, blank=True, verbose_name="Tipo de Unidad")
    patio = models.ForeignKey(Patio, on_delete=models.SET_NULL, null=True, blank=True, related_name='unidades')
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Unidad"
        verbose_name_plural = "Unidades"
        ordering = ['numero_economico']

    def __str__(self):
        return self.numero_economico

    def ultimo_rendimiento(self):
        ultima = self.cargas.order_by('-fecha_carga').first()
        if ultima and ultima.rendimiento:
            return float(ultima.rendimiento)
        return None

    def total_litros_consumidos(self):
        from django.db.models import Sum
        result = self.cargas.aggregate(total=Sum('litros_diesel'))
        return float(result['total'] or 0)


class Totem(models.Model):
    """Cada patio tiene su propio tótem con niveles de diésel y urea."""
    nombre = models.CharField(max_length=100, default="Tótem Principal")
    patio = models.OneToOneField(Patio, on_delete=models.CASCADE, related_name='totem')

    # Diésel
    capacidad_diesel = models.DecimalField(
        max_digits=10, decimal_places=2, default=14000,
        validators=[MinValueValidator(Decimal('1'))],
        verbose_name="Capacidad Total Diésel (L)"
    )
    cantidad_diesel = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Diésel Disponible (L)"
    )
    alerta_diesel = models.DecimalField(
        max_digits=10, decimal_places=2, default=2000,
        verbose_name="Alerta Diésel (L)"
    )

    # Urea
    capacidad_urea = models.DecimalField(
        max_digits=10, decimal_places=2, default=1000,
        validators=[MinValueValidator(Decimal('1'))],
        verbose_name="Capacidad Total Urea (L)"
    )
    cantidad_urea = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Urea Disponible (L)"
    )
    alerta_urea = models.DecimalField(
        max_digits=10, decimal_places=2, default=200,
        verbose_name="Alerta Urea (L)"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tótem de Combustible"
        verbose_name_plural = "Tótems de Combustible"

    def __str__(self):
        return f"{self.nombre} - {self.patio.nombre}"

    def porcentaje_diesel(self):
        if self.capacidad_diesel > 0:
            return round(float(self.cantidad_diesel / self.capacidad_diesel) * 100, 1)
        return 0

    def porcentaje_urea(self):
        if self.capacidad_urea > 0:
            return round(float(self.cantidad_urea / self.capacidad_urea) * 100, 1)
        return 0

    def estado_diesel(self):
        pct = self.porcentaje_diesel()
        if pct >= 70:
            return 'optimo'
        elif pct >= 40:
            return 'moderado'
        elif pct >= 15:
            return 'bajo'
        return 'critico'

    def estado_urea(self):
        pct = self.porcentaje_urea()
        if pct >= 70:
            return 'optimo'
        elif pct >= 40:
            return 'moderado'
        elif pct >= 15:
            return 'bajo'
        return 'critico'

    def alerta_activa_diesel(self):
        return self.cantidad_diesel <= self.alerta_diesel

    def alerta_activa_urea(self):
        return self.cantidad_urea <= self.alerta_urea


class CompraCombustible(models.Model):
    TIPO_CHOICES = [('diesel', 'Diésel'), ('urea', 'Urea')]

    patio = models.ForeignKey(Patio, on_delete=models.PROTECT, related_name='compras')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='diesel')
    proveedor = models.ForeignKey(ProveedorDiesel, on_delete=models.SET_NULL, null=True, related_name='compras')
    proveedor_nombre = models.CharField(max_length=150, editable=False)

    litros = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(Decimal('0.01'))])
    total = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)

    factura_pdf = models.FileField(upload_to='diesel/facturas/%Y/%m/', null=True, blank=True, verbose_name="Factura PDF")
    numero_factura = models.CharField(max_length=50, blank=True, verbose_name="Número de Factura")
    notas = models.TextField(blank=True)

    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Compra de Combustible"
        verbose_name_plural = "Compras de Combustible"
        ordering = ['-fecha']

    def __str__(self):
        return f"Compra {self.tipo} - {self.litros}L @ ${self.precio_unitario}"

    def save(self, *args, **kwargs):
        if self.proveedor:
            self.proveedor_nombre = self.proveedor.nombre
        self.total = self.litros * self.precio_unitario
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Actualizar tótem al crear
        if is_new:
            totem = self.patio.totem
            if self.tipo == 'diesel':
                totem.cantidad_diesel = min(
                    totem.cantidad_diesel + self.litros,
                    totem.capacidad_diesel
                )
            else:
                totem.cantidad_urea = min(
                    totem.cantidad_urea + self.litros,
                    totem.capacidad_urea
                )
            totem.save()


class AjusteInventario(models.Model):
    TIPO_COMBUSTIBLE = [('diesel', 'Diésel'), ('urea', 'Urea')]
    TIPO_MOVIMIENTO = [('entrada', 'Entrada (+)'), ('salida', 'Salida (-)')]

    patio = models.ForeignKey(Patio, on_delete=models.PROTECT, related_name='ajustes')
    tipo_combustible = models.CharField(max_length=10, choices=TIPO_COMBUSTIBLE, default='diesel')
    tipo_movimiento = models.CharField(max_length=10, choices=TIPO_MOVIMIENTO)
    litros = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    motivo = models.CharField(max_length=255, verbose_name="Motivo del Ajuste")

    cantidad_anterior = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    cantidad_posterior = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)

    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Ajuste de Inventario"
        verbose_name_plural = "Ajustes de Inventario"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.tipo_movimiento} {self.litros}L {self.tipo_combustible}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        totem = self.patio.totem

        if is_new:
            if self.tipo_combustible == 'diesel':
                self.cantidad_anterior = totem.cantidad_diesel
                if self.tipo_movimiento == 'entrada':
                    totem.cantidad_diesel = min(totem.cantidad_diesel + self.litros, totem.capacidad_diesel)
                else:
                    totem.cantidad_diesel = max(totem.cantidad_diesel - self.litros, Decimal('0'))
                self.cantidad_posterior = totem.cantidad_diesel
            else:
                self.cantidad_anterior = totem.cantidad_urea
                if self.tipo_movimiento == 'entrada':
                    totem.cantidad_urea = min(totem.cantidad_urea + self.litros, totem.capacidad_urea)
                else:
                    totem.cantidad_urea = max(totem.cantidad_urea - self.litros, Decimal('0'))
                self.cantidad_posterior = totem.cantidad_urea
            totem.save()

        super().save(*args, **kwargs)


class CargaDiesel(models.Model):
    patio = models.ForeignKey(Patio, on_delete=models.PROTECT, related_name='cargas')
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name='cargas')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Despachador")

    fecha_carga = models.DateTimeField(auto_now_add=True)
    odometro = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Odómetro (km)")
    hrs_thermo = models.DecimalField(max_digits=10, decimal_places=1, default=0, verbose_name="Horas Thermo")

    litros_diesel = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    litros_thermo = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    litros_urea = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    costo_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    precio_litro = models.DecimalField(max_digits=10, decimal_places=4, default=0, editable=False)

    # Fotos clásicas (mantienen compatibilidad). Ahora son opcionales para
    # facilitar el registro en campo cuando el usuario no alcanza a tomar todas.
    foto_bomba    = models.ImageField(upload_to='diesel/bombas/%Y/%m/',    verbose_name="Foto Bomba",    blank=True, null=True)
    foto_odometro = models.ImageField(upload_to='diesel/odometros/%Y/%m/', verbose_name="Foto Odómetro", blank=True, null=True)

    # ── NUEVO: trazabilidad operativa por carga ──────────────────────────
    cinchos_anteriores = models.CharField("Cinchos anteriores", max_length=120, blank=True, default='')
    cinchos_actuales   = models.CharField("Cinchos actuales",   max_length=120, blank=True, default='')
    # Persona que estuvo presente / llenó el equipo. Si no se especifica,
    # la view lo llena con el usuario logueado.
    persona_relleno = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='diesel_cargas_realizadas',
        verbose_name="Persona que realizó el llenado",
    )

    # Fotos opcionales adicionales (igual que el formulario operativo en campo).
    foto_sticker      = models.ImageField(upload_to='diesel/stickers/%Y/%m/',      verbose_name="Foto Sticker",       blank=True, null=True)
    foto_motor        = models.ImageField(upload_to='diesel/motor/%Y/%m/',         verbose_name="Foto Motor",         blank=True, null=True)
    foto_thermo       = models.ImageField(upload_to='diesel/thermo/%Y/%m/',        verbose_name="Foto Thermo",        blank=True, null=True)
    foto_horas_thermo = models.ImageField(upload_to='diesel/horas_thermo/%Y/%m/',  verbose_name="Foto Horas Thermo",  blank=True, null=True)

    rendimiento = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Rendimiento Km/L")

    class Meta:
        verbose_name = "Carga de Diésel"
        verbose_name_plural = "Cargas de Diésel"
        ordering = ['-fecha_carga']

    def __str__(self):
        return f"Carga {self.unidad} - {self.litros_diesel}L ({self.fecha_carga:%d/%m/%Y})"

    def calcular_rendimiento(self):
        """Calcula rendimiento basado en la carga anterior de la misma unidad."""
        ultima = CargaDiesel.objects.filter(
            unidad=self.unidad,
            fecha_carga__lt=self.fecha_carga if self.fecha_carga else None
        ).exclude(pk=self.pk).order_by('-fecha_carga').first()

        if not ultima:
            # Intentar con la última sin fecha (nuevo registro)
            ultima = CargaDiesel.objects.filter(
                unidad=self.unidad
            ).exclude(pk=self.pk).order_by('-fecha_carga').first()

        if ultima and ultima.odometro < self.odometro and self.litros_diesel > 0:
            km = float(self.odometro - ultima.odometro)
            return round(km / float(self.litros_diesel), 2)
        return None

    def calcular_costo(self):
        """Calcula el costo basado en último precio de compra."""
        ultima_compra = CompraCombustible.objects.filter(
            patio=self.patio, tipo='diesel'
        ).order_by('-fecha').first()
        if ultima_compra:
            self.precio_litro = ultima_compra.precio_unitario
            self.costo_total = self.litros_diesel * self.precio_litro
        total = self.litros_diesel
        if self.litros_thermo > 0:
            total += self.litros_thermo
        if ultima_compra:
            self.costo_total = total * self.precio_litro
