# ternium/models.py

import os
from django.db import models, transaction
from django.db.models import Sum
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models.signals import post_save
from django.contrib.auth.forms import AuthenticationForm
from django.dispatch import receiver



# --- FUNCIONES UPLOAD_TO (CENTRALIZADAS) ---

def get_remision_upload_path(instance, filename):
    """
    Genera una ruta de guardado única para los archivos de Remision.
    Ejemplo: remisiones_evidencias/REM-123/evidencia.pdf
    """
    folder_name = instance.remision or str(instance.pk)
    return os.path.join('remisiones_evidencias', folder_name, filename)

def get_registro_logistico_upload_path(instance, filename):
    """
    Genera una ruta de guardado única para los archivos de RegistroLogistico.
    Ejemplo: logistica_docs/REM-ABC/archivo.jpg
    """
    folder_name = instance.remision or "sin_remision"
    return os.path.join('logistica_docs', folder_name, filename)
get_upload_path = get_registro_logistico_upload_path # <-- AÑADE ESTA LÍNEA


def get_entrada_maquila_upload_path(instance, filename):
    """
    Genera una ruta de guardado única para los archivos de EntradaMaquila.
    Ejemplo: entradas_maquila/ID-XYZ/archivo.jpg
    """
    folder_name = instance.c_id_remito or "sin_remito"
    return os.path.join('entradas_maquila', folder_name, filename)

# --- INICIO DE LA MODIFICACIÓN ---
# 1. HEMOS AÑADIDO EL MODELO 'ORIGEN' AQUÍ
# -----------------------------------
class Origen(models.Model):
    """
    Catálogo para definir los orígenes de las empresas.
    (Ej: Nacional, Extranjero, USA, Asia, etc.)
    """
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre del origen (Ej: Nacional)")
    descripcion = models.TextField(blank=True, null=True, help_text="Descripción opcional del origen.")

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Origen"
        verbose_name_plural = "Orígenes"
        ordering = ['nombre']
# --- FIN DE LA MODIFICACIÓN ---


# --- MODELOS ---

class Empresa(models.Model):
    """
    Representa una empresa cliente, proveedora o unidad de negocio.
    Modificado para simplificar y añadir prefijos dinámicos.
    """
    search_fields = ['nombre', 'prefijo'] 
    
    nombre = models.CharField(
        max_length=150, 
        unique=True, 
        help_text="Nombre de la empresa. Ej: MONTERREY", 
        verbose_name="Nombre Completo" 
    )
    
    prefijo = models.CharField(
        max_length=10, 
        unique=True, 
        verbose_name="Prefijo", 
        help_text="Prefijo para folios (Ej. MTY). No incluyas el guión.",
        null=True,  # <-- ¡Importante!
        blank=True  # <-- ¡Importante!
    )
    
    creado_en = models.DateTimeField(auto_now_add=True)

    # --- INICIO DE LA MODIFICACIÓN ---
    # 2. HEMOS AÑADIDO EL CAMPO 'ORIGENES' (Many-to-Many)
    # -----------------------------------
    origenes = models.ManyToManyField(
        Origen,
        blank=True,  # Permite que una empresa no tenga ningún origen asignado
        related_name="empresas",
        help_text="Seleccione uno o más orígenes asociados a esta empresa."
    )
    # --- FIN DE LA MODIFICACIÓN ---

    def __str__(self):
        # Actualizamos esto para que no falle si el prefijo es nulo
        return f"{self.nombre} ({self.prefijo or 'Sin Prefijo'})"

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ['nombre']

class LineaTransporte(models.Model):
    """Representa una línea de transporte y su unidad de negocio asociada."""
    search_fields = ['nombre']
    nombre = models.CharField(max_length=150, unique=True, help_text="Nombre de la línea de transporte")
    empresas = models.ManyToManyField(
        Empresa,
        related_name="lineas_transporte",
        verbose_name="Unidades de Negocio (Empresas)"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Línea de Transporte"
        verbose_name_plural = "Líneas de Transporte"
        ordering = ['nombre']


class Operador(models.Model):
    """Representa a un operador o conductor."""
    search_fields = ['nombre']
    nombre = models.CharField(max_length=200, unique=True, help_text="Nombre completo del operador")
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Operador"
        verbose_name_plural = "Operadores"
        ordering = ['nombre']


class Material(models.Model):
    """Representa un tipo de material y su unidad de negocio."""
    search_fields = ['nombre']
    
    # --- CAMBIO AQUÍ ---
    # Quitamos el default y permitimos que esté vacío
    clave_sat = models.CharField(
        max_length=15, 
        blank=True, 
        null=True, 
        help_text="Clave de producto servicio del SAT"
    )
    # -------------------

    clave_unidad_sat = models.CharField(max_length=20, default="KGM", help_text="Clave de unidad SAT (ej. KGM, H87)")
    nombre = models.CharField(max_length=150, unique=True, help_text="Nombre o descripción del material")
    empresas = models.ManyToManyField(
        Empresa,
        related_name="materiales",
        verbose_name="Unidades de Negocio (Empresas)"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Material"
        verbose_name_plural = "Materiales"
        ordering = ['nombre']
        
def get_unidad_upload_path(instance, filename):
    """
    Genera una ruta de guardado única para los archivos de Unidades.
    Ejemplo: activos_unidades/T-01/foto_T-01.jpg
    """
    folder_name = instance.internal_id or str(instance.pk)
    return os.path.join('activos_unidades', folder_name, filename)

class Unidad(models.Model):
    """
    Representa un activo de la empresa (Tracto, Plana, Carro, etc.)
    con su documentación y control de vigencias.
    """
    search_fields = ['internal_id', 'license_plate', 'make_model', 'vin']

    # --- Opciones para campos de selección ---
    class AssetType(models.TextChoices):
        TRACTOR = 'TRACTOR', 'Tracto'
        PLANA = 'PLANA', 'Plana'
        MAQUINARIA = 'MAQUINARIA', 'Maquinaria'
        CARRO = 'CARRO', 'Carro'
        OTRO = 'OTRO', 'Otro'

    class OwnershipType(models.TextChoices):
        PROPIA = 'PROPIA', 'Propia'
        ARRENDADA = 'ARRENDADA', 'Arrendada'

    class OperationalStatus(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        FUERA_DE_SERVICIO = 'FUERA_DE_SERVICIO', 'Fuera de Servicio'
        EN_REPARACION = 'EN_REPARACION', 'En Reparación'

    # --- 1. Identificación del Activo ---
    # CORREGIDO: Se añade unique=True para garantizar que no haya IDs duplicados.
    internal_id = models.CharField("ID Interno (Nombre)", max_length=100, unique=True, help_text="Ej: T-01, PL-04, VOLVO-23")
    license_plate = models.CharField("Placa o Matrícula", max_length=50, blank=True, null=True)
    make_model = models.CharField("Marca y Modelo", max_length=200, blank=True, null=True)
    year = models.PositiveIntegerField("Año", blank=True, null=True)
    vin = models.CharField("Número de Serie / VIN", max_length=100, unique=True, blank=True, null=True)
    asset_type = models.CharField("Tipo de Activo", max_length=20, choices=AssetType.choices, default=AssetType.TRACTOR)
    color = models.CharField("Color", max_length=50, blank=True, null=True)
    
    # --- 2. Propiedad y Estatus ---
    ownership = models.CharField("Propiedad", max_length=20, choices=OwnershipType.choices, default=OwnershipType.PROPIA)
    acquisition_date = models.DateField("Fecha de Adquisición", blank=True, null=True)
    operational_status = models.CharField("Estatus Operativo", max_length=20, choices=OperationalStatus.choices, default=OperationalStatus.ACTIVO)
    
    # --- 3. Documentación y Vigencias ---
    insurance_policy = models.CharField("Póliza de Seguro", max_length=255, blank=True, null=True, help_text="Compañía y número de póliza")
    insurance_due_date = models.DateField("Vencimiento de Póliza", blank=True, null=True)
    circulation_license = models.CharField("Tarjeta de Circulación", max_length=255, blank=True, null=True)
    license_due_date = models.DateField("Vencimiento de Tarjeta", blank=True, null=True)
    
    # --- 4. Archivos y Evidencias ---
    display_photo = models.ImageField(
        "Foto de Visualización",
        upload_to=get_unidad_upload_path,
        max_length=255, blank=True, null=True
    )
    unit_documents = models.FileField(
        "Documentos de la Unidad",
        upload_to=get_unidad_upload_path,
        max_length=255, blank=True, null=True,
        help_text="PDF con factura, pedimento u otros documentos importantes."
    )
    
    # --- 5. Relaciones y Auditoría ---
    empresas = models.ManyToManyField(
        Empresa,
        related_name="unidades",
        verbose_name="Asignado a Empresa(s)"
    )
    notes = models.TextField("Notas Adicionales", blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.internal_id} ({self.license_plate or 'Sin Placa'})"

    class Meta:
        verbose_name = "Activo (Unidad)"
        verbose_name_plural = "Activos (Unidades)"
        ordering = ['internal_id']
        
class Contenedor(models.Model):
    """Representa un contenedor con sus placas."""
    search_fields = ['nombre', 'placas']
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre o identificador del contenedor (Ej: CAJA-SECA-04)")
    placas = models.CharField(max_length=20, unique=True, help_text="Placas o número de identificación del contenedor")
    empresas = models.ManyToManyField(
        Empresa,
        related_name="contenedores",
        verbose_name="Unidades de Negocio (Empresas)"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.placas})"

    class Meta:
        verbose_name = "Contenedor"
        verbose_name_plural = "Contenedores"
        ordering = ['nombre']


class Lugar(models.Model):
    # ==============================================================================
    # 1. CATÁLOGOS SAT (LISTAS OFICIALES COMPLETAS)
    # ==============================================================================
    
    REGIMEN_FISCAL_CHOICES = [
        ('601', '601 - General de Ley Personas Morales'),
        ('603', '603 - Personas Morales con Fines no Lucrativos'),
        ('605', '605 - Sueldos y Salarios e Ingresos Asimilados a Salarios'),
        ('606', '606 - Arrendamiento'),
        ('607', '607 - Régimen de Enajenación o Adquisición de Bienes'),
        ('608', '608 - Demás ingresos'),
        ('610', '610 - Residentes en el Extranjero sin Establecimiento Permanente en México'),
        ('611', '611 - Ingresos por Dividendos (socios y accionistas)'),
        ('612', '612 - Personas Físicas con Actividades Empresariales y Profesionales'),
        ('614', '614 - Ingresos por intereses'),
        ('615', '615 - Régimen de los ingresos por obtención de premios'),
        ('616', '616 - Sin obligaciones fiscales'),
        ('620', '620 - Sociedades Cooperativas de Producción que optan por diferir sus ingresos'),
        ('621', '621 - Incorporación Fiscal'),
        ('622', '622 - Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras'),
        ('623', '623 - Opcional para Grupos de Sociedades'),
        ('624', '624 - Coordinados'),
        ('625', '625 - Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas'),
        ('626', '626 - Régimen Simplificado de Confianza'),
    ]

    USO_CFDI_CHOICES = [
        ('G01', 'G01 - Adquisición de mercancías'),
        ('G02', 'G02 - Devoluciones, descuentos o bonificaciones'),
        ('G03', 'G03 - Gastos en general'),
        ('I01', 'I01 - Construcciones'),
        ('I02', 'I02 - Mobiliario y equipo de oficina por inversiones'),
        ('I03', 'I03 - Equipo de transporte'),
        ('I04', 'I04 - Equipo de computo y accesorios'),
        ('I05', 'I05 - Dados, troqueles, moldes, matrices y herramental'),
        ('I06', 'I06 - Comunicaciones telefónicas'),
        ('I07', 'I07 - Comunicaciones satelitales'),
        ('I08', 'I08 - Otra maquinaria y equipo'),
        ('D01', 'D01 - Honorarios médicos, dentales y gastos hospitalarios'),
        ('D02', 'D02 - Gastos médicos por incapacidad o discapacidad'),
        ('D03', 'D03 - Gastos funerales'),
        ('D04', 'D04 - Donativos'),
        ('D05', 'D05 - Intereses reales efectivamente pagados por créditos hipotecarios'),
        ('D06', 'D06 - Aportaciones voluntarias al SAR'),
        ('D07', 'D07 - Primas por seguros de gastos médicos'),
        ('D08', 'D08 - Gastos de transportación escolar obligatoria'),
        ('D09', 'D09 - Depósitos en cuentas para el ahorro, primas que tengan como base planes de pensiones'),
        ('D10', 'D10 - Pagos por servicios educativos (colegiaturas)'),
        ('S01', 'S01 - Sin efectos fiscales'),
        ('CP01', 'CP01 - Pagos'),
        ('CN01', 'CN01 - Nómina'),
    ]

    TIPO_CHOICES = [
        ('ORIGEN', 'Origen'),
        ('DESTINO', 'Destino'),
        ('AMBOS', 'Ambos'),
    ]

    # ==============================================================================
    # 2. DATOS OPERATIVOS
    # ==============================================================================
    
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre corto o alias operativo del lugar")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='DESTINO')
    es_patio = models.BooleanField(
        default=False,
        verbose_name="¿Es un patio de inventario?",
        help_text="Marcar si este lugar funciona como un almacén temporal (patio)."
    )
    empresas = models.ManyToManyField(
        Empresa,
        blank=True,
        related_name="lugares",
        verbose_name="Empresas Asociadas"
    )

    # ==============================================================================
    # 3. DATOS FISCALES (FACTURACIÓN)
    # ==============================================================================
    
    razon_social = models.CharField("Razón Social", max_length=200, blank=True, null=True, help_text="Nombre legal tal cual aparece en la Constancia de Situación Fiscal")
    rfc = models.CharField("RFC", max_length=13, blank=True, null=True, help_text="Registro Federal de Contribuyentes (Sin guiones)")
    
    regimen_fiscal = models.CharField(
        "Régimen Fiscal", 
        max_length=5, 
        choices=REGIMEN_FISCAL_CHOICES, 
        blank=True, null=True
    )
    
    uso_cfdi = models.CharField(
        "Uso de CFDI", 
        max_length=5, 
        choices=USO_CFDI_CHOICES, 
        default='G03', 
        blank=True, null=True
    )

    # ==============================================================================
    # 4. DIRECCIÓN FISCAL DESGLOSADA
    # ==============================================================================
    
    calle = models.CharField("Calle", max_length=150, blank=True, null=True)
    numero_exterior = models.CharField("No. Exterior", max_length=20, blank=True, null=True)
    numero_interior = models.CharField("No. Interior", max_length=20, blank=True, null=True)
    colonia = models.CharField("Colonia", max_length=100, blank=True, null=True)
    codigo_postal = models.CharField("Código Postal (CP)", max_length=10, blank=True, null=True)
    
    localidad = models.CharField("Localidad / Ciudad", max_length=100, blank=True, null=True)
    municipio = models.CharField("Municipio / Alcaldía", max_length=100, blank=True, null=True)
    estado = models.CharField("Estado", max_length=50, blank=True, null=True)
    pais = models.CharField("País", max_length=50, default="México", blank=True, null=True)
    
    # Campo de búsqueda para el admin
    search_fields = ['nombre', 'rfc', 'razon_social']

    def __str__(self):
        return self.nombre

    def direccion_completa(self):
        """Retorna la dirección formateada en una sola línea."""
        partes = [
            f"{self.calle} {self.numero_exterior}" if self.calle else None,
            f"Int. {self.numero_interior}" if self.numero_interior else None,
            f"Col. {self.colonia}" if self.colonia else None,
            f"CP {self.codigo_postal}" if self.codigo_postal else None,
            f"{self.municipio}, {self.estado}" if self.municipio else None
        ]
        return ", ".join(filter(None, partes))

    class Meta:
        verbose_name = "Lugar (Cliente/Origen)"
        verbose_name_plural = "Lugares"
        ordering = ['nombre']


class Remision(models.Model):
    STATUS_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('TERMINADO', 'Terminado'),
        ('AUDITADO', 'Auditado'),
        ('CANCELADO', 'Cancelado'), # <--- NUEVO ESTATUS
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDIENTE', verbose_name="Estatus")
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="remisiones", verbose_name="Unidad de Negocio (Empresa)")
    remision = models.CharField(max_length=100, verbose_name="Remisión", unique=True)
    fecha = models.DateField(verbose_name="Fecha")
    operador = models.ForeignKey(Operador, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Operador")
    linea_transporte = models.ForeignKey(LineaTransporte, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Línea de Transporte")
    unidad = models.ForeignKey(Unidad, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Unidad")
    contenedor = models.ForeignKey(Contenedor, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Contenedor")
    origen = models.ForeignKey(Lugar, on_delete=models.SET_NULL, null=True, blank=True, related_name="remisiones_origen", verbose_name="Lugar de Origen")
    destino = models.ForeignKey(Lugar, on_delete=models.SET_NULL, null=True, blank=True, related_name="remisiones_destino", verbose_name="Lugar de Destino")
    
    # --- AQUÍ ESTÁ EL CAMBIO (con comillas para evitar errores) ---
    cliente = models.ForeignKey('Cliente', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Cliente Destino")
    
    inicia_ld = models.DateTimeField(verbose_name="Inicia Carga", null=True, blank=True)
    termina_ld = models.DateTimeField(verbose_name="Termina Carga", null=True, blank=True)
    folio_ld = models.CharField(max_length=50, verbose_name="Folio Carga", blank=True)
    descripcion = models.TextField(verbose_name="Descripción", blank=True)
    inicia_dlv = models.DateTimeField(verbose_name="Inicia Descarga", null=True, blank=True)
    termina_dlv = models.DateTimeField(verbose_name="Termina Descarga", null=True, blank=True)
    folio_dlv = models.CharField(max_length=50, verbose_name="Folio Descarga", blank=True)
    
    evidencia_carga = models.FileField(upload_to='remisiones/cargas/', blank=True, null=True)
    evidencia_descarga = models.FileField(upload_to='remisiones/descargas/', blank=True, null=True)

    comentario = models.TextField(verbose_name="Comentario Adicional", blank=True)
    auditado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='remisiones_auditadas', verbose_name="Auditado por")
    auditado_en = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Auditoría")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    

    @property
    def total_peso_ld(self):
        return self.detalles.aggregate(total=Sum('peso_ld'))['total'] or 0

    @property
    def total_peso_dlv(self):
        return self.detalles.aggregate(total=Sum('peso_dlv'))['total'] or 0

    @property
    def diff(self):
        return self.total_peso_ld - self.total_peso_dlv

    def _is_terminado(self):
        if not self.pk:
            return False

        campos_requeridos = [
            self.remision, self.fecha, self.linea_transporte, self.operador,
            self.unidad, self.origen, self.destino,
            self.folio_ld, self.folio_dlv
        ]
        
        if not all(campos_requeridos):
            return False

        detalles_completos = self.detalles.filter(peso_ld__gt=0, peso_dlv__gt=0).exists()
        if not detalles_completos:
            return False

        patios_exentos = ["PATIO MONTERREY", "PATIO NUEVO LAREDO"]
        
        carga_evidence_ok = True
        if self.origen and self.origen.nombre.upper() not in patios_exentos:
            if not self.evidencia_carga:
                carga_evidence_ok = False

        descarga_evidence_ok = True
        if self.destino and self.destino.nombre.upper() not in patios_exentos:
            if not self.evidencia_descarga:
                descarga_evidence_ok = False
        
        return carga_evidence_ok and descarga_evidence_ok

    def save(self, *args, **kwargs):
        if self.pk and self.status == 'AUDITADO':
            old_instance = Remision.objects.get(pk=self.pk)
            if old_instance.status == 'AUDITADO':
                raise PermissionDenied("No se puede modificar una remisión auditada.")

        if self.status != 'AUDITADO':
            if self._is_terminado():
                self.status = 'TERMINADO'
            else:
                self.status = 'PENDIENTE'
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == 'AUDITADO':
            raise PermissionDenied("No se puede eliminar una remisión auditada.")
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Remisión {self.remision} del {self.fecha}"

    class Meta:
        verbose_name = "Remisión"
        verbose_name_plural = "Remisiones"
        ordering = ['-fecha', '-creado_en']
        indexes = [models.Index(fields=['status']), models.Index(fields=['fecha'])]
        
        # DEFINICIÓN DE PERMISOS PERSONALIZADOS
        permissions = [
            ("can_audit_remision", "Puede auditar remisiones"),
            ("view_ternium_module", "Puede acceder al módulo Ternium"), # Equivale a Acceso_ternium
            
            # --- TUS NUEVOS PERMISOS ---
            ("acceso_ia", "Acceso a Inteligencia Artificial"),
            ("acceso_remisiones", "Acceso a Módulo Remisiones"),
            ("acceso_dashboard_patio", "Acceso a Dashboard Patios"),
            ("acceso_catalogos", "Acceso a Catálogos"),
            ("acceso_reportes_kpi", "Acceso a Reportes y KPIs"), # Para el Dashboard de Análisis
        ]
        
class Cliente(models.Model):
    """
    Catálogo de Clientes comerciales para asignar en las remisiones.
    """
    search_fields = ['nombre']
    nombre = models.CharField(max_length=200, unique=True, verbose_name="Nombre del Cliente")
    empresas = models.ManyToManyField(
        'Empresa',  # Usamos comillas por si acaso
        blank=True,
        related_name="clientes_asociados",
        verbose_name="Unidades de Negocio (Empresas)"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombre']


class DetalleRemision(models.Model):
    remision = models.ForeignKey(Remision, on_delete=models.CASCADE, related_name='detalles')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name="Material")
    cliente = models.ForeignKey(
        Lugar,
        on_delete=models.PROTECT,
        related_name='detalles_cliente',
        verbose_name="Cliente",
        help_text="Cliente o destino específico para esta línea de material",
        null=True, blank=True
    )
    peso_ld = models.DecimalField(verbose_name="Peso Carga (Ton)", max_digits=10, decimal_places=3, default=0)
    peso_dlv = models.DecimalField(verbose_name="Peso Descarga (Ton)", max_digits=10, decimal_places=3, default=0)

    def __str__(self):
        return f"{self.material.nombre} en remisión {self.remision.remision}"

    class Meta:
        verbose_name = "Detalle de Remisión"
        verbose_name_plural = "Detalles de Remisión"


class InventarioPatio(models.Model):
    patio = models.ForeignKey(Lugar, on_delete=models.CASCADE, limit_choices_to={'es_patio': True}, related_name='inventario')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='inventario')
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0.000, validators=[MinValueValidator(0.0)])
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.material.nombre} en {self.patio.nombre}: {self.cantidad} kg"

    class Meta:
        verbose_name = "Inventario en Patio"
        verbose_name_plural = "Inventarios en Patios"
        unique_together = ('patio', 'material')
        ordering = ['patio', 'material']


class Descarga(models.Model):
    origen = models.ForeignKey(Lugar, on_delete=models.PROTECT, related_name='descargas_origen', verbose_name="Origen del Material")
    destino = models.ForeignKey(Lugar, on_delete=models.PROTECT, related_name='descargas_destino', verbose_name="Destino del Material")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name="Material Descargado")
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0.001)], verbose_name="Cantidad Descargada (kg)")
    fecha_descarga = models.DateTimeField(default=timezone.now, verbose_name="Fecha y Hora de Descarga")
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.origen == self.destino:
            raise ValidationError("El origen y el destino no pueden ser el mismo lugar.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.origen.es_patio:
                inventario_origen, created = InventarioPatio.objects.get_or_create(patio=self.origen, material=self.material)
                if inventario_origen.cantidad < self.cantidad:
                    raise ValidationError(f"No hay suficiente inventario de {self.material.nombre} en {self.origen.nombre}. Disponible: {inventario_origen.cantidad} kg.")
                inventario_origen.cantidad -= self.cantidad
                inventario_origen.save()
            if self.destino.es_patio:
                inventario_destino, created = InventarioPatio.objects.get_or_create(patio=self.destino, material=self.material)
                inventario_destino.cantidad += self.cantidad
                inventario_destino.save()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Descarga de {self.cantidad} kg de {self.material.nombre} a {self.destino.nombre}"

    class Meta:
        verbose_name = "Descarga de Material"
        verbose_name_plural = "Descargas de Materiales"
        ordering = ['-fecha_descarga']


class RegistroLogistico(models.Model):
    STATUS_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('TERMINADO', 'Terminado'),
        ('AUDITADO', 'Auditado'),
    ]
    
    remision = models.CharField(max_length=100, unique=True, verbose_name="Número de Remisión")
    fecha_carga = models.DateField(verbose_name="Fecha de Carga")
    boleta_bascula = models.CharField(max_length=100, verbose_name="# Boleta Báscula")
    fecha_envio = models.DateField(verbose_name="Fecha de Envío a Ternium", null=True, blank=True)
    
    transportista = models.ForeignKey(
        LineaTransporte, on_delete=models.SET_NULL, verbose_name="Transportista", null=True, blank=True
    )
    chofer = models.ForeignKey(
        Operador, on_delete=models.SET_NULL, verbose_name="Nombre del Chofer", null=True, blank=True
    )
    tractor = models.ForeignKey(
        Unidad, on_delete=models.SET_NULL, verbose_name="Tractor", related_name="registros_como_tractor", null=True, blank=True
    )
    tolva = models.ForeignKey(
        Contenedor, on_delete=models.SET_NULL, verbose_name="Tolva/Caja", related_name="registros_como_tolva", null=True, blank=True
    )
    
    material = models.ForeignKey(
        Material, on_delete=models.SET_NULL, verbose_name="Material", null=True, blank=True
    )
    toneladas_remisionadas = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Toneladas Remisionadas")
    toneladas_recibidas = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Toneladas Recibidas Ternium", null=True, blank=True)
    
    pdf_registro_camion_remision = models.FileField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="1. PDF: Registro de Camión y Remisión")
    pdf_remision_permiso = models.FileField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="2. PDF: Remisión y Permiso")
    foto_superior_vacia = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Superior (Vacía)")
    foto_frontal = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Frontal")
    foto_superior_llena = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Superior (Llena)")
    foto_trasera = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Trasera")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDIENTE', verbose_name="Estatus")
    auditado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='registros_logisticos_auditados', verbose_name="Auditado por")
    auditado_en = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Auditoría")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Registro Logístico"
        verbose_name_plural = "Registros Logísticos"
        ordering = ['-fecha_carga', '-creado_en']
        indexes = [models.Index(fields=['remision']), models.Index(fields=['status'])]
        # --- NUEVO ---
        permissions = [
            ("can_audit_logistica", "Puede auditar logística"),
        ]

    def __str__(self):
        return f"Registro {self.remision} del {self.fecha_carga}"

    @property
    def merma_absoluta(self):
        if self.toneladas_recibidas is not None and self.toneladas_remisionadas is not None:
            return self.toneladas_remisionadas - self.toneladas_recibidas
        return None

    @property
    def merma_porcentaje(self):
        if self.merma_absoluta is not None and self.toneladas_remisionadas > 0:
            merma_percent = (self.merma_absoluta / self.toneladas_remisionadas) * 100
            return merma_percent
        return None
        
    @property
    def documentos_completos(self):
        return all([
            self.pdf_registro_camion_remision,
            self.pdf_remision_permiso,
            self.foto_superior_vacia,
            self.foto_frontal,
            self.foto_superior_llena,
            self.foto_trasera
        ])

    def _is_terminado(self):
        if not self.pk:
            return False

        campos_principales_requeridos = [
            self.remision, self.fecha_carga, self.boleta_bascula, self.transportista,
            self.chofer, self.tractor, self.tolva, self.material,
            self.toneladas_remisionadas, self.toneladas_recibidas
        ]

        if not all(campos_principales_requeridos):
            return False
            
        return self.documentos_completos

    def save(self, *args, **kwargs):
        if self.pk and self.status == 'AUDITADO':
            old_instance = RegistroLogistico.objects.get(pk=self.pk)
            if old_instance.status == 'AUDITADO':
                raise PermissionDenied("No se puede modificar un registro logístico que ya ha sido auditado.")

        if self.status != 'AUDITADO':
            if self._is_terminado():
                self.status = 'TERMINADO'
            else:
                self.status = 'PENDIENTE'
                
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == 'AUDITADO':
            raise PermissionDenied("No se puede eliminar un registro logístico auditado.")
        super().delete(*args, **kwargs)
        

class EntradaMaquila(models.Model):
    STATUS_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('TERMINADO', 'Terminado'),
        ('AUDITADO', 'Auditado'),
    ]

    c_id_remito = models.CharField(max_length=255, verbose_name="ID Remito", help_text="Identificador único del remito de entrada")
    num_boleta_remision = models.CharField(max_length=255, verbose_name="Número de Boleta/Remisión", help_text="Número de boleta de remisión de báscula")
    fecha_ingreso = models.DateField(verbose_name="Fecha de Ingreso", help_text="Fecha en que se registra la entrada")
    transporte = models.CharField(max_length=255, verbose_name="Línea de Transporte", help_text="Nombre de la empresa transportista", blank=True, null=True)
    
    peso_remision = models.FloatField(verbose_name="Peso Remisión (Ton)", validators=[MinValueValidator(0)], help_text="Peso indicado en el remito")
    peso_bruto = models.FloatField(verbose_name="Peso Bruto (Ton)", validators=[MinValueValidator(0)], help_text="Peso total con carga")
    peso_tara = models.FloatField(verbose_name="Peso Tara (Ton)", validators=[MinValueValidator(0)], help_text="Peso del vehículo vacío")
    peso_neto = models.FloatField(verbose_name="Peso Neto (Ton)", validators=[MinValueValidator(0)], help_text="Peso calculado (Bruto - Tara)", editable=False)
    calidad = models.CharField(max_length=100, verbose_name="Calidad del Material", help_text="Tipo y calidad del material recibido")
    
    fecha_entrega_ternium = models.DateField(verbose_name="Fecha de Entrega a Ternium", null=True, blank=True)

    foto_frontal = models.ImageField(upload_to=get_entrada_maquila_upload_path, max_length=255, verbose_name="1. Foto Frontal", blank=True, null=True)
    foto_superior_cargada = models.ImageField(upload_to=get_entrada_maquila_upload_path, max_length=255, verbose_name="2. Foto Superior (con Carga)", blank=True, null=True)
    foto_trasera = models.ImageField(upload_to=get_entrada_maquila_upload_path, max_length=255, verbose_name="3. Foto Trasera", blank=True, null=True)
    foto_superior_vacia = models.ImageField(upload_to=get_entrada_maquila_upload_path, max_length=255, verbose_name="4. Foto Superior (Vacía)", blank=True, null=True)
    documento_remision_clientes = models.FileField(upload_to=get_entrada_maquila_upload_path, max_length=255, verbose_name="5. Registro de Camiones y Remisión a Clientes", blank=True, null=True)

    diferencia_toneladas = models.FloatField(verbose_name="Diferencia (Ton)", blank=True, null=True, editable=False)
    porcentaje_faltante = models.FloatField(verbose_name="% Diferencia", blank=True, null=True, editable=False)
    alerta = models.BooleanField(verbose_name="Alerta de Discrepancia", default=False, editable=False)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDIENTE', verbose_name="Estatus")
    auditado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='entradas_auditadas')
    auditado_en = models.DateTimeField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Registro de Entrada de Maquila"
        verbose_name_plural = "Registros de Entradas de Maquila"
        ordering = ['-fecha_ingreso', '-creado_en']
        indexes = [
            models.Index(fields=['c_id_remito']),
            models.Index(fields=['fecha_ingreso']),
            models.Index(fields=['status']),
        ]
        # --- NUEVO ---
        permissions = [
            ("can_audit_entrada", "Puede auditar entradas de maquila"),
        ]

    def __str__(self):
        return f"Entrada #{self.id} - Remito: {self.c_id_remito}"
    
    @property
    def documentos_completos(self):
        return all([
            self.foto_frontal,
            self.foto_superior_cargada,
            self.foto_trasera,
            self.foto_superior_vacia,
            self.documento_remision_clientes,
        ])
        
    def _is_terminado(self):
        if not self.pk:
            return False
        
        campos_requeridos = [
            self.c_id_remito, self.num_boleta_remision, self.fecha_ingreso,
            self.transporte, self.peso_remision, self.peso_bruto, self.peso_tara,
            self.calidad, self.fecha_entrega_ternium
        ]

        if not all(campos_requeridos):
            return False
            
        return self.documentos_completos

    def save(self, *args, **kwargs):
        if self.peso_bruto is not None and self.peso_tara is not None:
            self.peso_neto = self.peso_bruto - self.peso_tara
        if self.peso_remision is not None and self.peso_neto is not None:
            self.diferencia_toneladas = self.peso_remision - self.peso_neto
            if self.peso_remision > 0:
                self.porcentaje_faltante = abs(self.diferencia_toneladas / self.peso_remision) * 100
                self.alerta = self.porcentaje_faltante > 1.0
            else:
                self.porcentaje_faltante = 0
                self.alerta = False

        if self.pk and self.status == 'AUDITADO':
            old_instance = EntradaMaquila.objects.get(pk=self.pk)
            if old_instance.status == 'AUDITADO':
                raise PermissionDenied("No se puede modificar una entrada que ya ha sido auditada.")
        
        if self.status != 'AUDITADO':
            if self._is_terminado():
                self.status = 'TERMINADO'
            else:
                self.status = 'PENDIENTE'
                
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == 'AUDITADO':
            raise PermissionDenied("No se puede eliminar una entrada que ya ha sido auditada.")
        super().delete(*args, **kwargs)


from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ternium_profile')
    area = models.CharField(max_length=100, blank=True, null=True, default='General')
    telefono = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(default='avatars/default-avatar.png', max_length=255)
    
    # --- NUEVO CAMPO DE PERMISOS ---
    empresas_autorizadas = models.ManyToManyField(
        'Empresa', 
        blank=True, 
        related_name='usuarios_autorizados',
        help_text="Empresas con las que este usuario puede generar folios y ver información."
    )
    # -------------------------------

    def __str__(self):
        return f'Perfil de {self.user.username}'

# Estas funciones crean un Perfil automáticamente cuando un nuevo usuario se registra
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Primero, verifica si el usuario tiene un perfil asociado
    if hasattr(instance, 'ternium_profile'):
        instance.ternium_profile.save()
        
        

