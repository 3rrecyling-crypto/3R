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


def es_3r_nombre(nombre):
    """¿El nombre es el de 3R RECYCLING (flota propia)? Sin importar mayúsculas ni lo que siga.
    Solo la flota propia maneja rendimiento; los permisionarios son unidades ajenas."""
    return ' '.join((nombre or '').upper().split()).startswith('3R RECYCLING')


class Permisionario(models.Model):
    """Titular del permiso de una o varias unidades. Al registrar una carga, la
    unidad elegida trae su permisionario."""
    nombre = models.CharField(max_length=150, verbose_name="Nombre / Razón social")
    rfc = models.CharField(max_length=13, blank=True, verbose_name="RFC")
    telefono = models.CharField(max_length=20, blank=True)
    # A estos correos les llega el detalle de cada carga de sus unidades o thermos.
    correo = models.CharField(max_length=500, blank=True, verbose_name="Correos (separados por coma)")
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Permisionario"
        verbose_name_plural = "Permisionarios"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class PermisionarioUnidad(models.Model):
    """Unidad de Catálogos (la misma de remisiones) asignada a un permisionario.
    El vínculo vive aquí para no tocar el modelo ni los datos de remisiones; una
    unidad tiene a lo más un permisionario."""
    unidad = models.OneToOneField('ternium.Unidad', on_delete=models.CASCADE, related_name='permisionario_diesel')
    permisionario = models.ForeignKey(Permisionario, on_delete=models.CASCADE, related_name='unidades_asignadas')

    class Meta:
        verbose_name = "Unidad del permisionario"
        verbose_name_plural = "Unidades de permisionarios"

    def __str__(self):
        return f"{self.unidad} → {self.permisionario}"


class Thermo(models.Model):
    """Equipo de refrigeración que se carga de diésel por su cuenta. Es un
    catálogo propio: no depende de una unidad."""
    identificador = models.CharField(max_length=50, unique=True, verbose_name="Identificador / Número económico")
    descripcion = models.CharField(max_length=150, blank=True, verbose_name="Marca / Modelo")
    numero_serie = models.CharField(max_length=100, blank=True, verbose_name="Número de serie")
    permisionario = models.ForeignKey(
        Permisionario, on_delete=models.SET_NULL, null=True, blank=True, related_name='thermos',
    )
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Thermo"
        verbose_name_plural = "Thermos"
        ordering = ['identificador']

    def __str__(self):
        return self.identificador


class Unidad(models.Model):
    numero_economico = models.CharField(max_length=50, unique=True, verbose_name="Número Económico")
    descripcion = models.CharField(max_length=255, blank=True, null=True, verbose_name="Descripción / Alias")
    tipo = models.CharField(max_length=50, blank=True, verbose_name="Tipo de Unidad")
    patio = models.ForeignKey(Patio, on_delete=models.SET_NULL, null=True, blank=True, related_name='unidades')
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Unidad de Catálogos que representa: la captura desde el celular elige
    # unidades de Catálogos y la carga se registra contra esta.
    unidad_catalogo = models.OneToOneField(
        'ternium.Unidad', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='unidad_diesel', verbose_name="Unidad de Catálogos",
    )

    class Meta:
        verbose_name = "Unidad"
        verbose_name_plural = "Unidades"
        ordering = ['numero_economico']

    def __str__(self):
        return self.numero_economico

    @classmethod
    def para_unidad_catalogo(cls, unidad_cat):
        """Unidad de diesel de una unidad de Catálogos. Si no hay, liga la que ya
        tenga el mismo número económico o crea una nueva."""
        ligada = cls.objects.filter(unidad_catalogo=unidad_cat).first()
        if ligada:
            return ligada
        numero = unidad_cat.internal_id[:50]
        existente = cls.objects.filter(numero_economico__iexact=numero).first()
        if existente and existente.unidad_catalogo_id is None:
            existente.unidad_catalogo = unidad_cat
            existente.save(update_fields=['unidad_catalogo'])
            return existente
        if existente:  # el número ya es de otra unidad de Catálogos
            numero = f"{numero[:40]}-{unidad_cat.pk}"
        return cls.objects.create(
            numero_economico=numero, descripcion=unidad_cat.license_plate or '',
            tipo=unidad_cat.get_asset_type_display(), unidad_catalogo=unidad_cat,
        )

    def ultimo_rendimiento(self):
        # Solo las cargas de Unidad tienen rendimiento; las de Thermo no lo pisan.
        ultima = self.cargas.filter(tipo_carga='unidad', rendimiento__isnull=False).order_by('-fecha_carga', '-pk').first()
        if ultima:
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
    # Desde el celular cada carga es de una Unidad (km y litros) o de un Thermo
    # del catálogo de thermos (horas y litros), nunca de los dos. Las anteriores
    # quedan como 'unidad'.
    TIPO_CARGA = [('unidad', 'Unidad'), ('thermo', 'Thermo')]

    patio = models.ForeignKey(Patio, on_delete=models.PROTECT, related_name='cargas')
    # Vacía en las cargas de Thermo (esas llevan `thermo`).
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, null=True, blank=True, related_name='cargas')
    thermo = models.ForeignKey(Thermo, on_delete=models.PROTECT, null=True, blank=True, related_name='cargas')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Despachador")
    tipo_carga = models.CharField("Tipo de carga", max_length=10, choices=TIPO_CARGA, default='unidad')
    # Permisionario de la unidad al momento de la carga (el nombre se guarda por
    # si después cambia o se da de baja).
    permisionario = models.ForeignKey(
        Permisionario, on_delete=models.SET_NULL, null=True, blank=True, related_name='cargas',
    )
    permisionario_nombre = models.CharField(max_length=150, blank=True, default='', editable=False)
    # Correo con el detalle de la carga que se le mandó al permisionario (vacío = no se mandó).
    correo_enviado_a = models.CharField(max_length=500, blank=True, default='', editable=False)
    correo_enviado_en = models.DateTimeField(null=True, blank=True, editable=False)

    fecha_carga = models.DateTimeField(auto_now_add=True)
    # Vacío en las cargas de Thermo (no llevan kilometraje).
    odometro = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Odómetro (km)")
    hrs_thermo = models.DecimalField(max_digits=10, decimal_places=1, default=0, verbose_name="Horas Thermo")

    # En 0 cuando la carga es de Thermo (esos litros van en litros_thermo).
    litros_diesel = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
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
    # Operador (chofer) de la unidad o del thermo al momento de la carga: texto
    # libre en MAYÚSCULAS. Va en el mensaje de WhatsApp y en el correo.
    operador_nombre = models.CharField("Operador", max_length=150, blank=True, default='')
    persona_relleno = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='diesel_cargas_realizadas',
        verbose_name="Persona que realizó el llenado",
    )
    # Carga que se le pasó registrar al despachador y se capturó después desde el sistema
    # (Cargas de diésel › Nueva carga): quién la capturó y cuándo. Vacíos si la capturó él.
    registrada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                                       related_name='+', verbose_name="Registrada por")
    registrada_en = models.DateTimeField("Registrada el", null=True, blank=True, editable=False)

    # Fotos opcionales adicionales (igual que el formulario operativo en campo).
    foto_sticker      = models.ImageField(upload_to='diesel/stickers/%Y/%m/',      verbose_name="Foto Sticker",       blank=True, null=True)
    foto_motor        = models.ImageField(upload_to='diesel/motor/%Y/%m/',         verbose_name="Foto Motor",         blank=True, null=True)
    foto_thermo       = models.ImageField(upload_to='diesel/thermo/%Y/%m/',        verbose_name="Foto Thermo",        blank=True, null=True)
    foto_horas_thermo = models.ImageField(upload_to='diesel/horas_thermo/%Y/%m/',  verbose_name="Foto Horas Thermo",  blank=True, null=True)

    rendimiento = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Rendimiento Km/L")

    # Diésel del tótem antes y después de esta carga y su capacidad en ese momento (van en el
    # mensaje de WhatsApp). Vacíos en las cargas registradas antes de guardarlos.
    totem_antes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False, verbose_name="Tótem antes (L)")
    totem_despues = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False, verbose_name="Tótem después (L)")
    totem_capacidad = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False, verbose_name="Capacidad del tótem (L)")

    # Auditoría con IA de la foto de la bomba (botón "Auditar con IA"). La IA solo lee la foto y
    # deja el estatus; nunca cambia los litros ni otro dato. Vacío = todavía no se audita.
    AUDITORIA = [('verificado', 'Verificado'), ('alerta', 'Alerta')]
    auditoria_estado = models.CharField("Auditoría IA", max_length=12, choices=AUDITORIA, blank=True, default='', editable=False)
    auditoria_litros_foto = models.DecimalField("Litros según la foto", max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    auditoria_totalizador = models.DecimalField("Totalizador según la foto", max_digits=14, decimal_places=2, null=True, blank=True, editable=False)
    auditoria_nota = models.CharField("Nota de la auditoría", max_length=255, blank=True, default='', editable=False)
    auditoria_fecha = models.DateTimeField("Auditada el", null=True, blank=True, editable=False)
    auditoria_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                                      related_name='+', verbose_name="Auditó")

    class Meta:
        verbose_name = "Carga de Diésel"
        verbose_name_plural = "Cargas de Diésel"
        ordering = ['-fecha_carga']
        permissions = [
            # Captura desde el celular (PWA): el usuario que lo tiene es despachador.
            ('acceso_carga_diesel', 'Acceso carga diesel'),
        ]

    @property
    def equipo(self):
        """Lo que se cargó: el número de la unidad o el identificador del thermo."""
        if self.unidad_id:
            return self.unidad.numero_economico
        return self.thermo.identificador if self.thermo_id else ''

    def __str__(self):
        litros = self.litros_thermo if self.tipo_carga == 'thermo' else self.litros_diesel
        return f"Carga {self.equipo} - {litros}L ({self.fecha_carga:%d/%m/%Y})"

    def calcular_rendimiento(self):
        """Km/L desde la carga de Unidad anterior de la misma unidad. Las cargas
        de Thermo no llevan kilometraje: ni se calculan ni cuentan como anterior."""
        if self.tipo_carga != 'unidad' or self.odometro is None or not self.litros_diesel:
            return None
        anteriores = CargaDiesel.objects.filter(
            unidad=self.unidad, tipo_carga='unidad', odometro__isnull=False,
        ).exclude(pk=self.pk)
        if self.fecha_carga:  # al crear todavía no tiene fecha
            anteriores = anteriores.filter(fecha_carga__lt=self.fecha_carga)
        # pk desempata dos cargas con la misma hora exacta.
        ultima = anteriores.order_by('-fecha_carga', '-pk').first()

        if ultima and ultima.odometro < self.odometro:
            km = float(self.odometro - ultima.odometro)
            return round(km / float(self.litros_diesel), 2)
        return None

    def descontar_del_totem(self):
        """Saca del tótem del patio lo cargado: el diésel del motor y el del thermo
        salen de la misma bomba; la urea, de su propio depósito."""
        totem = self.patio.totem
        antes = totem.cantidad_diesel
        totem.cantidad_diesel = max(antes - self.litros_diesel - self.litros_thermo, Decimal('0'))
        if self.litros_urea > 0:
            totem.cantidad_urea = max(totem.cantidad_urea - self.litros_urea, Decimal('0'))
        totem.save()
        # Cómo quedó el tótem con esta carga (para el mensaje de WhatsApp).
        nivel = {'totem_antes': antes, 'totem_despues': totem.cantidad_diesel, 'totem_capacidad': totem.capacidad_diesel}
        for campo, valor in nivel.items():
            setattr(self, campo, valor)
        if self.pk:
            CargaDiesel.objects.filter(pk=self.pk).update(**nivel)

    def calcular_costo(self):
        """Calcula el costo basado en último precio de compra (a la fecha de la carga, si ya la
        tiene: una carga que se registra después lleva el precio de ese día)."""
        compras = CompraCombustible.objects.filter(patio=self.patio, tipo='diesel')
        if self.fecha_carga:
            compras = compras.filter(fecha__lte=self.fecha_carga)
        ultima_compra = compras.order_by('-fecha').first()
        if ultima_compra:
            self.precio_litro = ultima_compra.precio_unitario
            self.costo_total = self.litros_diesel * self.precio_litro
        total = self.litros_diesel
        if self.litros_thermo > 0:
            total += self.litros_thermo
        if ultima_compra:
            self.costo_total = total * self.precio_litro


class FotoComplementaria(models.Model):
    """Fotos extra que el despachador anexa a una carga si aplican (además de
    las fijas: bomba, odómetro, thermo). Se capturan desde el celular."""
    MAXIMO = 6  # por carga

    carga = models.ForeignKey(CargaDiesel, on_delete=models.CASCADE, related_name='fotos_complementarias')
    foto = models.ImageField(upload_to='diesel/complementarias/%Y/%m/', verbose_name="Foto")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Foto complementaria"
        verbose_name_plural = "Fotos complementarias"
        ordering = ['pk']

    def __str__(self):
        return f"Foto complementaria de la carga {self.carga_id}"
