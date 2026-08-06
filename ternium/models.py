# ternium/models.py

import os
from django.db import models, transaction
from django.db.models import Sum
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal # Asegúrate de tener este import arriba
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models.signals import post_save
from django.contrib.auth.forms import AuthenticationForm
from django.dispatch import receiver
from django.contrib.auth.decorators import login_required
from django.contrib import messages



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
    # Agregamos 'folio' a los campos de búsqueda
    search_fields = ['nombre', 'folio'] 
    
    nombre = models.CharField(max_length=200, unique=True, help_text="Nombre completo del operador")
    
    # --- NUEVOS CAMPOS ---
    folio = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="Folio / Licencia",
        help_text="Número de licencia, gafete o ID interno"
    )
    
    empresas = models.ManyToManyField(
        Empresa,
        related_name="operadores",
        verbose_name="Unidades de Negocio (Empresas)",
        blank=True
    )
    # ---------------------

    # Baja lógica: un operador que deja de trabajar se marca como inactivo en
    # vez de borrarlo. Así desaparece de los desplegables al capturar, pero las
    # remisiones que ya lo tenían asignado conservan su nombre. Es reversible.
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Los inactivos no aparecen al capturar remisiones, "
                  "pero se conservan en el historial."
    )

    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Muestra el folio si existe
        if self.folio:
            return f"{self.nombre} ({self.folio})"
        return self.nombre

    class Meta:
        verbose_name = "Operador"
        verbose_name_plural = "Operadores"
        ordering = ['nombre']

    @property
    def tiene_historial(self):
        """Si ya se usó en alguna remisión, borrarlo perdería ese dato."""
        return self.remision_set.exists()


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

    # --- 3.b Datos SCT / Carta Porte (sin timbrar) ---
    permiso_sct = models.CharField("Permiso SCT (Tipo)", max_length=50, blank=True, null=True, help_text="Ej: TPAF01")
    no_permiso_sct = models.CharField("No. Permiso SCT", max_length=100, blank=True, null=True)
    nombre_aseguradora = models.CharField("Nombre Aseguradora", max_length=200, blank=True, null=True)
    no_poliza_seguro = models.CharField("No. Póliza Seguro", max_length=100, blank=True, null=True)
    eco_remolque_1 = models.CharField("Eco. Remolque 1", max_length=50, blank=True, null=True)
    placa_remolque_1 = models.CharField("Placa Remolque 1", max_length=50, blank=True, null=True)
    eco_remolque_2 = models.CharField("Eco. Remolque 2", max_length=50, blank=True, null=True)
    placa_remolque_2 = models.CharField("Placa Remolque 2", max_length=50, blank=True, null=True)
    
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
    
    # El nombre sigue siendo único para identificar el registro internamente
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre o identificador del contenedor (Ej: CAJA-SECA-04)")
    
    # --- CAMBIO REALIZADO AQUÍ ---
    # Se eliminó "unique=True" para permitir placas repetidas en diferentes contenedores
    placas = models.CharField(max_length=20, help_text="Placas o número de identificación del contenedor")
    # -----------------------------

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
        max_length=50, 
        choices=REGIMEN_FISCAL_CHOICES, 
        blank=True, null=True
    )
    
    uso_cfdi = models.CharField(
        "Uso de CFDI", 
        max_length=50, 
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
    
    # Código de ubicación tipo OR000001 / DE000001 (auto-generado en save)
    id_ubicacion = models.CharField("ID Ubicación", max_length=15, unique=True, blank=True, null=True,
                                    help_text="Generado automáticamente: ORnnnnnn para Origen, DEnnnnnn para Destino")

    # Campo de búsqueda para el admin
    search_fields = ['nombre', 'rfc', 'razon_social', 'id_ubicacion']

    def __str__(self):
        return f"{self.id_ubicacion} - {self.nombre}" if self.id_ubicacion else self.nombre

    def save(self, *args, **kwargs):
        if not self.id_ubicacion:
            prefix = 'OR' if self.tipo == 'ORIGEN' else ('DE' if self.tipo == 'DESTINO' else 'AM')
            # Encontrar el siguiente número secuencial con ese prefijo
            from django.db.models import Max
            last = Lugar.objects.filter(id_ubicacion__startswith=prefix).aggregate(
                m=Max('id_ubicacion'))['m']
            try:
                last_num = int(last[2:]) if last else 0
            except (TypeError, ValueError):
                last_num = 0
            self.id_ubicacion = f"{prefix}{last_num + 1:06d}"
        super().save(*args, **kwargs)

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
        ('CANCELADO', 'Cancelado'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDIENTE', verbose_name="Estatus")
    
    # Relaciones
    empresa = models.ForeignKey('Empresa', on_delete=models.PROTECT, related_name="remisiones", verbose_name="Unidad de Negocio (Empresa)")
    
    remision = models.CharField(max_length=100, verbose_name="Remisión") 
    fecha = models.DateField(verbose_name="Fecha")
    
    operador = models.ForeignKey('Operador', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Operador")
    linea_transporte = models.ForeignKey('LineaTransporte', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Línea de Transporte")
    unidad = models.ForeignKey('Unidad', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Unidad")
    contenedor = models.ForeignKey('Contenedor', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Contenedor")
    origen = models.ForeignKey('Lugar', on_delete=models.SET_NULL, null=True, blank=True, related_name="remisiones_origen", verbose_name="Lugar de Origen")
    destino = models.ForeignKey('Lugar', on_delete=models.SET_NULL, null=True, blank=True, related_name="remisiones_destino", verbose_name="Lugar de Destino")
    cliente = models.ForeignKey('Cliente', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Cliente Destino")
    placas_unidad_manual = models.CharField(max_length=50, blank=True, null=True, verbose_name="Placas Unidad (Manual)")
    placas_contenedor_manual = models.CharField(max_length=50, blank=True, null=True, verbose_name="Placas Contenedor (Manual)")
    
    # Datos Operativos (Carga/Descarga)
    inicia_ld = models.DateTimeField(verbose_name="Inicia Carga", null=True, blank=True)
    termina_ld = models.DateTimeField(verbose_name="Termina Carga", null=True, blank=True)
    folio_ld = models.CharField(max_length=50, verbose_name="Folio Carga", blank=True)
    descripcion = models.TextField(verbose_name="Descripción", blank=True)
    
    inicia_dlv = models.DateTimeField(verbose_name="Inicia Descarga", null=True, blank=True)
    termina_dlv = models.DateTimeField(verbose_name="Termina Descarga", null=True, blank=True)
    folio_dlv = models.CharField(max_length=50, verbose_name="Folio Descarga", blank=True)
    operador_manual = models.CharField(max_length=200, blank=True, null=True, verbose_name="Operador (Manual)")
    unidad_manual = models.CharField(max_length=100, blank=True, null=True, verbose_name="Unidad (Manual)")
    contenedor_manual = models.CharField(max_length=100, blank=True, null=True, verbose_name="Contenedor (Manual)")
    
    # Campo para archivo
    evidencia_documento = models.FileField(
        upload_to='remisiones/evidencias/',
        verbose_name="Evidencia (PDF o Foto)",
        blank=True, 
        null=True
    )
    manifiesto = models.FileField(
        upload_to='remisiones/manifiestos/', 
        verbose_name="Manifiesto (PDF o Foto)",
        blank=True, 
        null=True,
        help_text="Documento oficial de manifiesto de carga/descarga"
    )

    comentario = models.TextField(verbose_name="Comentario Adicional", blank=True)
    trazabilidad_notas = models.TextField(
        verbose_name="Notas de Trazabilidad (TRANE)", 
        blank=True, 
        null=True,
        help_text="Apartado exclusivo para el seguimiento de materiales origen TRANE"
    )

    # --- DATOS EXTRAS (BÁSCULA Y FACTURACIÓN) ---
    hora_entrada = models.TimeField(null=True, blank=True, verbose_name="Hora de Entrada")
    hora_salida = models.TimeField(null=True, blank=True, verbose_name="Hora de Salida")
    peso_bascula = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Peso Báscula")
    factura_nombre = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nombre/Folio Factura")

    # --- EVIDENCIAS Y DATOS DE DESTRUCCIÓN FISCAL ---
    fecha_destruccion = models.DateField(null=True, blank=True, verbose_name="Fecha de Destrucción")
    comentarios_destruccion = models.TextField(null=True, blank=True, verbose_name="Comentarios de Destrucción")
    
    foto_ingreso = models.ImageField(upload_to='remisiones/destruccion/', blank=True, null=True, verbose_name="1. Ingreso de la unidad")
    foto_ingreso_2 = models.ImageField(upload_to='remisiones/destruccion/', blank=True, null=True, verbose_name="1.2 Ingreso de la unidad (Extra)")
    
    foto_vertido = models.ImageField(upload_to='remisiones/destruccion/', blank=True, null=True, verbose_name="2. Vertido del material")
    foto_vertido_2 = models.ImageField(upload_to='remisiones/destruccion/', blank=True, null=True, verbose_name="2.2 Vertido del material (Extra)")
    
    foto_destruccion = models.ImageField(upload_to='remisiones/destruccion/', blank=True, null=True, verbose_name="3. Destrucción y Disposición")
    foto_destruccion_2 = models.ImageField(upload_to='remisiones/destruccion/', blank=True, null=True, verbose_name="3.2 Destrucción y Disposición (Extra)")
    
    # Auditoría
    auditado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='remisiones_auditadas', verbose_name="Auditado por")
    auditado_en = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Auditoría")
    
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    folio_medline = models.CharField(max_length=50, blank=True, null=True, verbose_name="Folio Medline")
    
    # --- DATOS SELECCIONADOS DEL MODAL PARA EL REPORTE DE DESTRUCCIÓN ---
    destruccion_material_1 = models.CharField(max_length=150, null=True, blank=True, verbose_name="Material Destrucción 1")
    destruccion_peso_1 = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Peso Destrucción 1")
    destruccion_material_2 = models.CharField(max_length=150, null=True, blank=True, verbose_name="Material Destrucción 2")
    destruccion_peso_2 = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Peso Destrucción 2")
    boleta_salida_medline = models.FileField(
        upload_to='remisiones/medline/', 
        blank=True, 
        null=True, 
        verbose_name="Boleta de Salida MEDLINE"
    )
    @property
    def total_peso_ld(self):
        return self.detalles.aggregate(total=Sum('peso_ld'))['total'] or 0

    @property
    def total_peso_dlv(self):
        return self.detalles.aggregate(total=Sum('peso_dlv'))['total'] or 0

    @property
    def total_peso_rechazado(self):
        return self.detalles.aggregate(total=Sum('peso_rechazado'))['total'] or 0

    @property
    def porcentaje_merma(self):
        """
        Calcula el porcentaje de pérdida con base en la carga, descontando el rechazo.
        Fórmula: ((Carga - (Descarga + Rechazado)) / Carga) * 100
        """
        carga = self.total_peso_ld
        descarga = self.total_peso_dlv
        rechazado = self.total_peso_rechazado
        
        if carga and carga > 0:
            diferencia = carga - (descarga + rechazado)
            return (diferencia / carga) * 100
        return 0.0

    @property
    def peso_neto_standarizado_kg(self):
        """
        Devuelve el peso estandarizado en KG.
        """
        try:
            peso = Decimal(str(self.total_peso_dlv or 0))
        except:
            peso = Decimal("0.00")

        detalle = self.detalles.first()
        
        if detalle and hasattr(detalle, 'unidad_medida') and detalle.unidad_medida:
            u = str(detalle.unidad_medida).strip().upper()
            
            if 'TON' in u or u == 'T' or u == 'TN':
                return peso * 1000
            
            if ('KG' in u or 'KILO' in u) and peso < 100:
                return peso * 1000

        return peso

    @property
    def diff(self):
        """
        Diferencia neta: (Descarga + Rechazado) - Carga
        """
        return (self.total_peso_dlv + self.total_peso_rechazado) - self.total_peso_ld
    
    @property
    def diff_abs(self):
        return abs(self.diff)

    # =====================================================================
    # NUEVA PROPIEDAD: VALIDACIÓN PARA MANIFIESTO DE DESTRUCCIÓN
    # =====================================================================
    @property
    def permite_manifiesto_destruccion(self):
        """Revisa si la remisión cumple con la configuración dinámica para generar el Word"""
        if not self.origen or not self.detalles.exists():
            return False
        
        # Obtenemos el material de la remisión
        material_principal = self.detalles.first().material
        
        # Importación diferida para evitar errores si ConfiguracionManifiesto está abajo
        from django.apps import apps
        ConfiguracionManifiesto = apps.get_model('ternium', 'ConfiguracionManifiesto')
        
        # Validamos si existe esa combinación en la nueva tabla de configuraciones
        return ConfiguracionManifiesto.objects.filter(
            origen=self.origen, 
            material=material_principal
        ).exists()
        
    @property
    def destruccion_fiscal_completa(self):
        """Revisa si la remisión tiene los datos mínimos para el formato de destrucción."""
        tiene_fecha = bool(self.fecha_destruccion)
        tiene_material = bool(self.destruccion_material_1 and str(self.destruccion_material_1).strip() != "")
        tiene_foto1 = bool(self.foto_ingreso and self.foto_ingreso.name)
        tiene_foto2 = bool(self.foto_vertido and self.foto_vertido.name)
        tiene_foto3 = bool(self.foto_destruccion and self.foto_destruccion.name)
        
        return tiene_fecha and tiene_material and tiene_foto1 and tiene_foto2 and tiene_foto3
    # =====================================================================

    def save(self, *args, **kwargs):
        # 1. BLOQUEO DE EDICIÓN SI YA ESTÁ AUDITADO
        if self.pk:
            try:
                old = Remision.objects.get(pk=self.pk)
                if old.status == 'AUDITADO':
                    pass 
            except Remision.DoesNotExist:
                pass

        # 2. LÓGICA DE ESTATUS AUTOMÁTICO
        if self.status != 'AUDITADO' and self.status != 'CANCELADO':
            
            def tiene_datos(valor):
                return valor is not None and str(valor).strip() != ""

            carga_completa = (
                tiene_datos(self.inicia_ld) and 
                tiene_datos(self.termina_ld) and 
                tiene_datos(self.folio_ld)
            )

            descarga_completa = (
                tiene_datos(self.inicia_dlv) and 
                tiene_datos(self.termina_dlv) and 
                tiene_datos(self.folio_dlv)
            )

            nombre_destino = ""
            if self.destino:
                nombre_destino = self.destino.nombre.upper()
            
            if 'PTE' in nombre_destino:
                self.status = 'PENDIENTE'
            elif carga_completa and descarga_completa:
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
        
        unique_together = ('empresa', 'remision')
        
        permissions = [
            ("can_audit_remision", "Puede auditar remisiones"),
            ("view_ternium_module", "Puede acceder al módulo Ternium"),
            ("acceso_ia", "Acceso a Inteligencia Artificial"),
            ("acceso_remisiones", "Acceso a Módulo Remisiones"),
            ("acceso_dashboard_patio", "Acceso a Dashboard Patios"),
            ("acceso_catalogos", "Acceso a Catálogos"),
            ("acceso_reportes_kpi", "Acceso a Reportes y KPIs"),
            ("acceso_trane", "Acceso al Portal Trane"),
        ]

    class Meta:
        verbose_name = "Remisión"
        verbose_name_plural = "Remisiones"
        ordering = ['-fecha', '-creado_en']
        indexes = [models.Index(fields=['status']), models.Index(fields=['fecha'])]

        unique_together = ('empresa', 'remision')

        permissions = [
            ("can_audit_remision", "Puede auditar remisiones"),
            ("view_ternium_module", "Puede acceder al módulo Ternium"),
            ("acceso_ia", "Acceso a Inteligencia Artificial"),
            ("acceso_remisiones", "Acceso a Módulo Remisiones"),
            ("acceso_dashboard_patio", "Acceso a Dashboard Patios"),
            ("acceso_catalogos", "Acceso a Catálogos"),
            ("acceso_reportes_kpi", "Acceso a Reportes y KPIs"),
            ("acceso_trane", "Acceso al Portal Trane"),
            ("acceso_bancos", "Acceso a Flujo Bancario"),
            ("acceso_dashboard", "Acceso a Dashboard Principal"),
            ("acceso_diesel", "Acceso a Control Diésel"),
            ("ver_dashboard_trane", "Puede ver el Dashboard TRANE"),
            ("exportar_dashboard_trane", "Puede exportar reportes del Dashboard TRANE"),
            ("acceso_dashboard_remisiones", "Acceso al Dashboard de Remisiones"),
            ("ver_kpis_remisiones", "Puede ver KPIs y métricas de remisiones"),
            ("exportar_remisiones", "Puede exportar reportes de remisiones a Excel"),
            ("acceso_utilidades", "Acceso al módulo de Utilidades / Herramientas"),
        ]

        # Folio Medline MANUAL y único: la unicidad se valida a NIVEL APLICACIÓN
        # (RemisionForm.clean_folio_medline + api_crear/editar_remision + serializer DRF).
        # NO se usa un UniqueConstraint de BD porque la base de producción (Render) ya
        # tenía folios_medline duplicados y el índice único no podía crearse sin modificar
        # esos datos. Ver migración 0093 (neutralizada).

class Cliente(models.Model):
    """
    Catálogo de Clientes comerciales para asignar en las remisiones.
    """
    search_fields = ['nombre']
    nombre = models.CharField(max_length=200, unique=True, verbose_name="Nombre del Cliente")
    # Domicilio del cliente (para autocompletar el manifiesto al elegirlo). Todo opcional.
    codigo_postal = models.CharField(max_length=10, blank=True, null=True, verbose_name="Código Postal")
    calle = models.CharField(max_length=200, blank=True, null=True)
    no_exterior = models.CharField(max_length=30, blank=True, null=True, verbose_name="No. Exterior")
    no_interior = models.CharField(max_length=30, blank=True, null=True, verbose_name="No. Interior")
    colonia = models.CharField(max_length=150, blank=True, null=True)
    municipio = models.CharField(max_length=150, blank=True, null=True)
    telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    correo = models.CharField(max_length=200, blank=True, null=True, verbose_name="Correo electrónico")
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
    UNIDAD_CHOICES = [
        ('TON', 'Ton'),
        ('KG', 'Kg'),
    ]
    unidad_medida = models.CharField(
        max_length=3, 
        choices=UNIDAD_CHOICES, 
        default='TON',
        verbose_name="Unidad"
    )
    # --- CAMBIO: Agregamos null=True y blank=True ---
    material = models.ForeignKey(
        Material, 
        on_delete=models.PROTECT, 
        verbose_name="Material",
        null=True,  # Permite guardar NULL en la BD
        blank=True  # Permite enviar el formulario vacío
    )
    
    peso_rechazado = models.DecimalField(
        verbose_name="Peso Rechazado (Kg)",
        max_digits=12,
        decimal_places=3,
        default=0
    )
    
    patio_rechazo = models.ForeignKey(
        Lugar,
        on_delete=models.PROTECT,
        related_name='detalles_rechazo',
        verbose_name="Patio de Rechazo",
        limit_choices_to={'es_patio': True},
        null=True, blank=True,
        help_text="Si hay rechazo, indica a qué patio regresará el material."
    )
    # -----------------------------------------------

    cliente = models.ForeignKey(
        Lugar,
        on_delete=models.PROTECT,
        related_name='detalles_cliente',
        verbose_name="Cliente",
        help_text="Cliente o destino específico para esta línea de material",
        null=True, blank=True
    )
    peso_ld = models.DecimalField(
        verbose_name="Peso Carga (Kg)", # <-- CAMBIADO
        max_digits=12,  # Asegura tener espacio para miles de kilos (ej. 45000.000)
        decimal_places=3, 
        default=0
    )
    peso_dlv = models.DecimalField(
        verbose_name="Peso Descarga (Kg)", # <-- CAMBIADO
        max_digits=12, 
        decimal_places=3, 
        default=0
    )
    bultos = models.PositiveIntegerField(
        verbose_name="Bultos", 
        blank=True, 
        null=True
    )

    def __str__(self):
        # --- CAMBIO: Validación para evitar error si no hay material ---
        nombre_mat = self.material.nombre if self.material else "Sin Material"
        return f"{nombre_mat} en remisión {self.remision.remision}"

    class Meta:
        verbose_name = "Detalle de Remisión"
        verbose_name_plural = "Detalles de Remisión"
    @property
    def diferencia(self):
        return (self.peso_dlv + self.peso_rechazado) - self.peso_ld

    @property
    def diferencia_abs(self):
        return abs(self.diferencia)

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
        ('CANCELADO', 'Cancelado'),
        ('RECHAZADO', 'Rechazado'), # <--- AGREGAR ESTA LÍNEA
    ]
    
    remision = models.CharField(max_length=100, unique=True, verbose_name="Número de Remisión")
    fecha_carga = models.DateField(verbose_name="Fecha de Carga")
    boleta_bascula = models.CharField(max_length=100, verbose_name="# Boleta Báscula")
    fecha_envio = models.DateField(verbose_name="Fecha de Envío a Ternium", null=True, blank=True)
    
    transportista = models.ForeignKey(
        LineaTransporte, on_delete=models.SET_NULL, verbose_name="Transportista", null=True, blank=True
    )
    chofer = models.CharField(
        max_length=200, 
        verbose_name="Nombre del Chofer", 
        null=True, 
        blank=True
    )
    tractor = models.CharField(
        max_length=100, 
        verbose_name="Tractor (Eco/Placas)", 
        null=True, 
        blank=True
    )
    tolva = models.CharField(
        max_length=100, 
        verbose_name="Tolva/Caja (Eco/Placas)", 
        null=True, 
        blank=True
    )
    placas_tractor = models.CharField(
        max_length=50, 
        verbose_name="Placas Tractor", 
        null=True, 
        blank=True
    )
    placas_tolva = models.CharField(
        max_length=50, 
        verbose_name="Placas Tolva", 
        null=True, 
        blank=True
    )
    material = models.ForeignKey(
        Material, on_delete=models.SET_NULL, verbose_name="Material", null=True, blank=True
    )
    toneladas_remisionadas = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Toneladas Remisionadas")
    toneladas_recibidas = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Toneladas Recibidas Ternium", null=True, blank=True)
    
    pdf_registro_camion_remision = models.FileField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="1. PDF: Registro de Camión y Remisión")
    #pdf_remision_permiso = models.FileField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="2. PDF: Remisión y Permiso")
    foto_superior_vacia = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Superior (Vacía)")
    foto_frontal = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Frontal")
    foto_superior_llena = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Superior (Llena)")
    foto_trasera = models.ImageField(upload_to=get_registro_logistico_upload_path, max_length=255, null=True, blank=True, verbose_name="Foto Trasera")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDIENTE', verbose_name="Estatus")
    auditado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='registros_logisticos_auditados', verbose_name="Auditado por")
    auditado_en = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Auditoría")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    pdf_hoja_circulacion = models.FileField(
        upload_to=get_registro_logistico_upload_path, 
        max_length=255, 
        null=True, 
        blank=True, 
        verbose_name="2. PDF: Hoja de Circulación"  # <--- CAMBIADO DE 3 A 2
    )
    
    comentario = models.TextField(
        verbose_name="Comentarios Generales", 
        blank=True, 
        null=True
    )
    
    numero_permiso_sct = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="Número de Permiso SCT"
    )
    fecha_correo = models.DateField(
        verbose_name="Fecha de Correo", 
        null=True, 
        blank=True
    )
    pdf_factura = models.FileField(
        upload_to=get_registro_logistico_upload_path, 
        max_length=255, 
        null=True, 
        blank=True, 
        verbose_name="PDF Factura"
    )
    xml_factura = models.FileField(
        upload_to=get_registro_logistico_upload_path, 
        max_length=255, 
        null=True, 
        blank=True, 
        verbose_name="XML Factura"
    )
    acuse_pdf = models.FileField(
        upload_to=get_registro_logistico_upload_path, 
        max_length=255, 
        null=True, 
        blank=True, 
        verbose_name="Acuse (PDF)"
    )

    class Meta:
        verbose_name = "Registro Logístico"
        verbose_name_plural = "Registros Logísticos"
        ordering = ['-fecha_carga', '-creado_en']
        indexes = [models.Index(fields=['remision']), models.Index(fields=['status'])]
        permissions = [
            ("can_audit_logistica", "Puede auditar logística"),
        ]

    def __str__(self):
        return f"Registro {self.remision} del {self.fecha_carga}"

    # --- PROPIEDADES (INDENTADAS DENTRO DE LA CLASE) ---

    @property
    def merma_absoluta(self):
        # LÓGICA 3R: Real (Recibidas) - Documento (Remisionadas)
        # Ejemplo: Recibidas (90) - Remisionadas (100) = -10 (Negativo es Pérdida)
        if self.toneladas_recibidas is not None and self.toneladas_remisionadas is not None:
            return self.toneladas_recibidas - self.toneladas_remisionadas
        return None

    @property
    def merma_porcentaje(self):
        # El porcentaje heredará el signo negativo de merma_absoluta
        if self.merma_absoluta is not None and self.toneladas_remisionadas > 0:
            merma_percent = (self.merma_absoluta / self.toneladas_remisionadas) * 100
            return merma_percent
        return None
    
    @property
    def documentos_completos(self):
        return all([
            self.pdf_registro_camion_remision,
            #self.pdf_remision_permiso,
            self.pdf_hoja_circulacion, 
            self.foto_superior_vacia,
            self.foto_frontal,
            self.foto_superior_llena,
            self.foto_trasera
        ])

    def _is_terminado(self):
        # Campos mínimos requeridos para considerar terminado
        campos_principales_requeridos = [
            self.remision, self.fecha_carga, self.boleta_bascula, self.transportista,
            self.chofer, self.tractor, self.tolva, self.material,
            self.toneladas_remisionadas, self.toneladas_recibidas
        ]

        if not all(campos_principales_requeridos):
            return False
            
        return self.documentos_completos

    def save(self, *args, **kwargs):
        # 1. BLOQUEO DE EDICIÓN
        if self.pk:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
                if old_instance.status in ['AUDITADO', 'CANCELADO', 'RECHAZADO']: # <--- AGREGAR RECHAZADO AQUÍ TAMBIÉN SI QUIERES BLOQUEAR EDICIÓN
                    if self.status == old_instance.status:
                        # Esto permite cambiar EL estatus (ej: de rechazado a pendiente), 
                        # pero bloquea editar el resto si ya está en ese estado.
                        pass 
            except self.__class__.DoesNotExist:
                pass

        # 2. LÓGICA AUTOMÁTICA DE ESTATUS (AQUÍ ESTÁ EL ERROR)
        # Debes agregar 'RECHAZADO' a esta lista para que la lógica automática lo ignore
        if self.status not in ['AUDITADO', 'CANCELADO', 'RECHAZADO']: 
            if self._is_terminado():
                self.status = 'TERMINADO'
            else:
                self.status = 'PENDIENTE'
                
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status in ['AUDITADO', 'CANCELADO']:
            raise PermissionDenied(f"No se puede eliminar un registro con estatus {self.get_status_display()}.")
        super().delete(*args, **kwargs)
        

class EntradaMaquila(models.Model):
    STATUS_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('TERMINADO', 'Terminado'),
        ('AUDITADO', 'Auditado'),
        ('CANCELADO', 'Cancelado'), # <--- Estatus Agregado
    ]

    c_id_remito = models.CharField(
        max_length=255, 
        verbose_name="ID Remito", 
        help_text="Identificador único del remito de entrada",
        unique=True,  # <--- AGREGAR ESTO
        error_messages={ # <--- OPCIONAL: Mensaje de error por defecto
            'unique': "Este ID de Remito ya está registrado en el sistema."
        }
    )
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
    comentario = models.TextField(
        verbose_name="Comentarios Generales", 
        blank=True, 
        null=True, 
        help_text="Observaciones adicionales sobre la entrada"
    )

    class Meta:
        verbose_name = "Registro de Entrada de Maquila"
        verbose_name_plural = "Registros de Entradas de Maquila"
        ordering = ['-fecha_ingreso', '-creado_en']
        indexes = [
            models.Index(fields=['c_id_remito']),
            models.Index(fields=['fecha_ingreso']),
            models.Index(fields=['status']),
        ]
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
        # Cálculos de peso
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

        # 1. BLOQUEO DE EDICIÓN: Si ya está finalizado (Auditado o Cancelado)
        if self.pk:
            old_instance = EntradaMaquila.objects.get(pk=self.pk)
            if old_instance.status in ['AUDITADO', 'CANCELADO']:
                # Si el estatus no cambia (es decir, intentan editar campos), bloquear.
                if self.status == old_instance.status:
                    raise PermissionDenied(f"No se puede modificar una entrada con estatus {old_instance.get_status_display()}.")
        
        # 2. LÓGICA AUTOMÁTICA (Solo si no es Auditado ni Cancelado)
        if self.status not in ['AUDITADO', 'CANCELADO']:
            if self._is_terminado():
                self.status = 'TERMINADO'
            else:
                self.status = 'PENDIENTE'
                
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # 3. BLOQUEO DE ELIMINACIÓN
        if self.status in ['AUDITADO', 'CANCELADO']:
            raise PermissionDenied(f"No se puede eliminar una entrada con estatus {self.get_status_display()}.")
        super().delete(*args, **kwargs)


from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ternium_profile')
    area = models.CharField(max_length=100, blank=True, null=True, default='General')
    telefono = models.CharField(max_length=20, blank=True, null=True)
    
    # --- AGREGAR ESTE CAMPO ---
    empresa = models.CharField(
        max_length=150, 
        blank=True, 
        null=True, 
        verbose_name="Empresa Asignada"
    )
    # --------------------------

    avatar = models.ImageField(default='avatars/default-avatar.png', max_length=255)
    
    empresas_autorizadas = models.ManyToManyField(
        'Empresa',
        blank=True,
        related_name='usuarios_autorizados',
        help_text="Empresas con las que este usuario puede generar folios y ver información."
    )

    ROL_CHOICES = [
        ('', 'Admin General'),
        ('flujos_bancos', 'Flujos Bancos'),
        ('ternium', 'Ternium'),
    ]
    rol = models.CharField(max_length=30, blank=True, default='', choices=ROL_CHOICES,
                           verbose_name="Rol de acceso")

    # Configuración de la tabla de /remisiones/ para este usuario:
    #   {"columnas": ["remision", "fecha", ...], "personalizada": true}
    # Se guardan las dos vistas: 'columnas' conserva la tabla que armó el
    # usuario aunque tenga desactivada la personalización, así puede volver a
    # la vista por defecto y regresar a la suya sin rehacerla.
    columnas_remisiones = models.JSONField(
        default=dict, blank=True,
        verbose_name="Configuración de la tabla de remisiones"
    )

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
        
class HistorialRemision(models.Model):
    remision = models.ForeignKey(Remision, on_delete=models.CASCADE, related_name='historial')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    # Cambiamos accion/descripcion por un solo campo 'cambio' para coincidir con tu HTML
    cambio = models.TextField(verbose_name="Descripción del cambio") 

    class Meta:
        ordering = ['-fecha']
        verbose_name = "Historial de Remisión"
        verbose_name_plural = "Historial de Remisiones"

    def __str__(self):
        return f"{self.remision} - {self.fecha}"
        
        
class EvidenciaRemision(models.Model):
    """
    Modelo para soportar múltiples archivos por remisión.
    """
    remision = models.ForeignKey(Remision, on_delete=models.CASCADE, related_name='evidencias')
    archivo = models.FileField(
        upload_to='remisiones/evidencias/', # Django requiere esto, aunque usaremos S3 manual
        verbose_name="Archivo de Evidencia"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidencia {self.id} - {self.remision.remision}"

    def nombre_corto(self):
        return os.path.basename(self.archivo.name)
        
    def es_imagen(self):
        ext = os.path.splitext(self.archivo.name)[1].lower()
        return ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    
    
class Plastico(models.Model):
    STATUS_CHOICES = [
        ('BORRADOR', 'Borrador'),
        ('TERMINADO', 'Terminado'),
        ('AUDITADO', 'Auditado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    UNIDAD_CHOICES = [
        ('KG', 'Kilogramos (KG)'),
        ('TON', 'Toneladas (TON)'),
    ]

    # --- NUEVO CAMPO: Vinculación con Empresa (Operación) ---
    empresa = models.ForeignKey(
        'Empresa', 
        on_delete=models.PROTECT, 
        verbose_name="Operación",
        null=True, blank=True
    )
    # --------------------------------------------------------

    # Datos Generales
    remision = models.CharField(max_length=100, blank=True, null=True, verbose_name="Remisión / Folio")
    fecha = models.DateField(blank=True, null=True, verbose_name="Fecha")
    
    # Origen y Destino
    origen = models.ForeignKey(Lugar, on_delete=models.SET_NULL, null=True, blank=True, related_name='plasticos_origen')
    destino = models.ForeignKey(Lugar, on_delete=models.SET_NULL, null=True, blank=True, related_name='plasticos_destino')
    
    operador = models.CharField(max_length=200, blank=True, null=True, verbose_name="Operador")
    unidad = models.CharField(max_length=100, blank=True, null=True, verbose_name="Unidad / Placas")
    
    folio_ld = models.CharField(max_length=100, blank=True, null=True, verbose_name="Folio LD")
    folio_dlv = models.CharField(max_length=100, blank=True, null=True, verbose_name="Folio DLV")
    
    descripcion = models.CharField(max_length=255, blank=True, null=True, verbose_name="Descripción / Material")
    fecha_entrega = models.DateField(blank=True, null=True, verbose_name="Fecha Entrega")
    
    # Valores Numéricos
    unidad_medida = models.CharField(max_length=3, choices=UNIDAD_CHOICES, default='KG', verbose_name="Unidad de Medida")
    
    peso_bruto = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True, verbose_name="Peso Bruto")
    peso_tarimas = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="Peso Tarimas (Siempre KG)")
    
    # Peso Neto Calculado
    peso = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True, verbose_name="Peso Neto")
    
    precio = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="Precio Unitario")
    venta = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="Venta Total")
    pagado = models.BooleanField(default=False, verbose_name="¿Pagado?")
    
    pdf_adicional = models.FileField(
        upload_to='plastico/adicionales/', 
        blank=True, 
        null=True, 
        verbose_name="PDF Adicional (Opcional)"
    )
    comentario = models.TextField(blank=True, null=True)
    
    # Control
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='BORRADOR')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Plástico {self.remision or self.pk}"
    
    class Meta:
        permissions = [
            ("can_audit_plastico", "Puede auditar plásticos"),
            ("acceso_plastico", "Puede acceder al módulo de plásticos"),
        ]
        
    def _is_terminado(self):
        """Verifica si tiene los datos mínimos para ser TERMINADO."""
        campos_requeridos = [
            self.remision, self.fecha, self.origen, self.destino, 
            self.operador, self.unidad, self.descripcion, self.peso_bruto,
            self.peso, self.precio, self.venta
        ]
        datos_completos = all(campos_requeridos)
        valores_validos = ((self.peso or 0) > 0) and ((self.venta or 0) > 0)
        
        return datos_completos and valores_validos

    def save(self, *args, **kwargs):
        # --- 1. GENERACIÓN AUTOMÁTICA DE FOLIO DINÁMICA ---
        # Solo si no tiene folio y se seleccionó una operación (empresa)
        if not self.remision and self.empresa:
            # Obtener prefijo (ej: SEA, PLA, GEN)
            prefijo = self.empresa.prefijo.upper() if self.empresa.prefijo else "GEN"
            
            # Buscar el último folio QUE CORRESPONDA A ESE PREFIJO ESPECÍFICO
            last = Plastico.objects.filter(remision__startswith=f"{prefijo}-").order_by('id').last()
            
            if not last:
                new_id = 1
            else:
                try:
                    # Extraer el número del último folio (ej: SEA-050 -> 50)
                    parts = last.remision.split('-')
                    if len(parts) > 1:
                        last_number = int(parts[1])
                        new_id = last_number + 1
                    else:
                        new_id = last.id + 1
                except:
                    new_id = 1
            
            # --- CAMBIO AQUÍ: Usar :03d en lugar de :04d ---
            # Esto genera 001, 099, 100... y cuando sea 1000 pone 1000 automáticamente.
            self.remision = f"{prefijo}-{new_id:03d}" 

        # --- 2. CÁLCULOS AUTOMÁTICOS (Backend) ---
        if self.peso_bruto is not None:
            tarimas = self.peso_tarimas or 0
            if self.unidad_medida == 'TON':
                # Convertimos tarimas (KG) a TON para restar
                self.peso = self.peso_bruto - (tarimas / 1000)
            else:
                # Todo en KG
                self.peso = self.peso_bruto - tarimas
            
            if self.peso < 0: self.peso = 0

        if self.peso is not None and self.precio is not None:
            if self.unidad_medida == 'TON':
                # Precio es por KG, pero peso en TON -> convertimos peso a KG
                cobrable = self.peso * 1000 
                self.venta = cobrable * self.precio
            else:
                self.venta = self.peso * self.precio

        # --- 3. BLOQUEO DE EDICIÓN ---
        if self.pk:
            try:
                old = Plastico.objects.get(pk=self.pk)
                if old.status in ['AUDITADO', 'CANCELADO']:
                    pass 
            except Plastico.DoesNotExist:
                pass

        # --- 4. ASIGNACIÓN DE ESTATUS ---
        if self.status not in ['AUDITADO', 'CANCELADO']:
            if self._is_terminado():
                self.status = 'TERMINADO'
            else:
                self.status = 'BORRADOR'

        super().save(*args, **kwargs)
        
class EvidenciaPlastico(models.Model):
    plastico = models.ForeignKey(Plastico, on_delete=models.CASCADE, related_name='evidencias')
    archivo = models.FileField(upload_to='plastico/evidencias/', verbose_name="Archivo")
    subido_en = models.DateTimeField(auto_now_add=True)

class HistorialPlastico(models.Model):
    plastico = models.ForeignKey(Plastico, on_delete=models.CASCADE, related_name='historial')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    cambio = models.TextField()
    
class ControlTarima(models.Model):
    fecha = models.DateField(verbose_name="Fecha")
    origen = models.ForeignKey(Lugar, on_delete=models.SET_NULL, null=True, blank=True, related_name='tarimas_origen')
    destino = models.ForeignKey(Lugar, on_delete=models.SET_NULL, null=True, blank=True, related_name='tarimas_destino')
    
    # Tarimas Chicas
    tarima_chica_cant = models.IntegerField(default=0, verbose_name="Cant. Tarima Chica")
    precio_chica = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Precio Chica")
    # SE ELIMINÓ editable=False
    total_chica = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total Chica")
    
    # Tarimas Grandes
    tarima_grande_cant = models.IntegerField(default=0, verbose_name="Cant. Tarima Grande")
    precio_grande = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Precio Grande")
    # SE ELIMINÓ editable=False
    total_grande = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total Grande")
    tarima_mediana_cant = models.IntegerField(default=0, verbose_name="Cant. Tarima Mediana")
    precio_mediana = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Precio Mediana")
    total_mediana = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total Mediana")
    # Totales
    # SE ELIMINÓ editable=False
    gran_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Gran Total")
    
    comentarios = models.TextField(blank=True, null=True)
    
    # Evidencia (PDF o Foto)
    evidencia = models.FileField(
        upload_to='tarimas/evidencias/', 
        blank=True, 
        null=True, 
        verbose_name="Evidencia (PDF/Foto)"
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        from decimal import Decimal
        
        cant_chica = self.tarima_chica_cant or 0
        precio_chica = self.precio_chica or Decimal(0)
        
        # Lógica para Medianas
        cant_mediana = self.tarima_mediana_cant or 0
        precio_mediana = self.precio_mediana or Decimal(0)
        
        cant_grande = self.tarima_grande_cant or 0
        precio_grande = self.precio_grande or Decimal(0)

        # Cálculos individuales
        self.total_chica = cant_chica * precio_chica
        self.total_mediana = cant_mediana * precio_mediana # <-- Nuevo
        self.total_grande = cant_grande * precio_grande
        
        # Gran Total actualizado
        self.gran_total = self.total_chica + self.total_mediana + self.total_grande
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Tarimas {self.fecha} - {self.origen} a {self.destino}"

    class Meta:
        verbose_name = "Control de Tarima"
        verbose_name_plural = "Control de Tarimas"
        ordering = ['-fecha']

class ConfiguracionManifiesto(models.Model):
    origen = models.ForeignKey('Lugar', on_delete=models.CASCADE, related_name='configs_manifiesto')
    material = models.ForeignKey('Material', on_delete=models.CASCADE, related_name='configs_manifiesto')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('origen', 'material') # Evita duplicados
        verbose_name = "Configuración de Manifiesto"
        verbose_name_plural = "Configuraciones de Manifiestos"

    def __str__(self):
        return f"{self.origen.nombre} - {self.material.nombre}"

class ControlManifiestoTrane(models.Model):
    fecha_captura = models.DateField(verbose_name="Fecha de Captura", null=True, blank=True)
    
    # Catálogos y textos manuales
    operador = models.ForeignKey(Operador, on_delete=models.SET_NULL, null=True, blank=True)
    operador_manual = models.CharField(max_length=200, blank=True, null=True)
    remision_vinculada = models.OneToOneField('Remision', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Operación Original")    
    linea_transporte = models.ForeignKey(LineaTransporte, on_delete=models.SET_NULL, null=True, blank=True)
    
    unidad = models.ForeignKey(Unidad, on_delete=models.SET_NULL, null=True, blank=True)
    unidad_manual = models.CharField(max_length=100, blank=True, null=True)
    placas_unidad_manual = models.CharField(max_length=50, blank=True, null=True)
    
    contenedor = models.ForeignKey(Contenedor, on_delete=models.SET_NULL, null=True, blank=True)
    contenedor_manual = models.CharField(max_length=100, blank=True, null=True)
    placas_contenedor_manual = models.CharField(max_length=50, blank=True, null=True)
    cantidad_kg = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="Cantidad (Kg)", null=True, blank=True)    # Lugares y Material
    origen = models.ForeignKey(Lugar, related_name='control_trane_origen', on_delete=models.SET_NULL, null=True, blank=True)
    destino = models.ForeignKey(Lugar, related_name='control_trane_destino', on_delete=models.SET_NULL, null=True, blank=True)
    folio = models.CharField(max_length=100, verbose_name="Folio", blank=True, null=True)
    material = models.ForeignKey(Material, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Archivos
    manifiesto = models.FileField(upload_to='trane/manifiestos/', blank=True, null=True, verbose_name="Manifiesto")
    documento_trane = models.FileField(upload_to='trane/documentos/', blank=True, null=True, verbose_name="Documento Trane")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Control Manifiesto Trane"
        verbose_name_plural = "Control Manifiestos Trane"
        ordering = ['-fecha_captura', '-id']

    def __str__(self):
        return f"Control Trane {self.folio or self.id}"
    
from django.db import models

class PrecioMedline(models.Model):
    mes = models.CharField(max_length=7, unique=True, verbose_name="Mes (YYYY-MM)")
    precio_carton = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    precio_archivo = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)

    def __str__(self):
        return f"{self.mes} - Cartón: ${self.precio_carton} | Archivo: ${self.precio_archivo}"


class ConfiguracionAlertaMerma(models.Model):
    """
    Umbral de merma (%) por material. Si la merma supera el umbral,
    se dispara un correo de alerta. Default global: 1 %.
    """
    material = models.OneToOneField(
        'Material', on_delete=models.CASCADE,
        related_name='config_alerta_merma',
        verbose_name="Material"
    )
    porcentaje_umbral = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00,
        verbose_name="Umbral de merma (%)"
    )

    class Meta:
        verbose_name = 'Configuración Alerta Merma'
        verbose_name_plural = 'Configuraciones Alerta Merma'
        ordering = ['material__nombre']

    def __str__(self):
        return f"{self.material.nombre} — {self.porcentaje_umbral}%"


class DestinatarioAlertaMerma(models.Model):
    """Correos que reciben las alertas de merma."""
    email = models.EmailField(unique=True, verbose_name="Correo electrónico")

    class Meta:
        verbose_name = 'Destinatario Alerta Merma'
        verbose_name_plural = 'Destinatarios Alerta Merma'
        ordering = ['email']

    def __str__(self):
        return self.email


class RemisionAlertaMermaLog(models.Model):
    """
    Bitácora de alertas de merma enviadas por remisión. Sirve únicamente
    como bandera anti-duplicado: si una remisión ya tiene un registro aquí,
    no se vuelve a enviar el correo (aunque la remisión se edite).
    OneToOne para garantizar a nivel de BD que solo hay un registro por
    remisión.
    """
    remision = models.OneToOneField(
        'Remision', on_delete=models.CASCADE,
        related_name='alerta_merma_log',
        verbose_name="Remisión",
    )
    enviada_en = models.DateTimeField(auto_now_add=True, verbose_name="Enviada en")
    materiales_alertados = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Cantidad de materiales que superaron el umbral",
    )
    detalle = models.TextField(
        blank=True, default='',
        verbose_name="Resumen de la alerta enviada",
    )

    class Meta:
        verbose_name = 'Log de Alerta Merma'
        verbose_name_plural = 'Logs de Alertas Merma'
        ordering = ['-enviada_en']

    def __str__(self):
        return f"Alerta merma · remisión {self.remision_id} · {self.enviada_en:%Y-%m-%d %H:%M}"


class Alerta(models.Model):
    """
    Alertas/mensajes que aparecen en el Centro de Alertas (campana del header
    y módulo de administración). Las crean usuarios STAFF desde el panel
    `/admin/centro-alertas`. Los usuarios marcan como leídas mediante el M2M
    `leida_por` (cada usuario tiene su propio "leído").
    """
    TIPO_CHOICES = [
        ('alert',   'Crítica'),
        ('warning', 'Advertencia'),
        ('info',    'Informativa'),
        ('success', 'Éxito'),
        ('neural',  'Neural'),
    ]
    tipo  = models.CharField(max_length=10, choices=TIPO_CHOICES, default='info')
    title = models.CharField("Título", max_length=200)
    desc  = models.TextField("Mensaje")
    creada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='alertas_creadas', verbose_name='Creada por',
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    # Cada usuario que abra esta alerta marca leído para él mismo. Así no
    # interferimos entre staff distinto (cada uno tiene su badge "no leído").
    leida_por = models.ManyToManyField(
        User, blank=True, related_name='alertas_leidas',
        verbose_name='Leída por',
    )

    class Meta:
        verbose_name = 'Alerta'
        verbose_name_plural = 'Alertas'
        ordering = ['-creada_en']

    def __str__(self):
        return f"[{self.tipo}] {self.title} ({self.creada_en:%Y-%m-%d %H:%M})"


class ChatMensaje(models.Model):
    """
    Mensaje del chat IA del asistente del sistema. Cada usuario tiene su
    propio hilo de conversación (no se comparte entre usuarios).
    """
    ROL_CHOICES = [
        ('user', 'Usuario'),
        ('bot',  'Asistente'),
    ]
    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_mensajes')
    rol       = models.CharField(max_length=10, choices=ROL_CHOICES)
    contenido = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mensaje del Chat IA'
        verbose_name_plural = 'Mensajes del Chat IA'
        ordering = ['creado_en']
        indexes = [models.Index(fields=['user', 'creado_en'])]

    def __str__(self):
        return f"{self.user.username} [{self.rol}] {self.contenido[:50]}"


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO DE VIAJES — Carta de Traslado (sin timbrar)
# ═══════════════════════════════════════════════════════════════════════════════

class Viaje(models.Model):
    """
    Bitácora de viajes para generar Cartas de Traslado (sin timbrar).
    El operador se vincula a un Empleado de RH con puesto que contenga "OPERADOR".
    """
    ESTADO_CHOICES = [
        ('PLANIFICADO', 'Planificado'),
        ('EN_RUTA',     'En Ruta'),
        ('ENTREGADO',   'Entregado'),
        ('CANCELADO',   'Cancelado'),
    ]

    numero_viaje = models.PositiveIntegerField("Número de viaje", unique=True, blank=True, null=True,
                                                db_index=True, help_text="ID interno secuencial autoincremental")
    id_viaje = models.CharField("ID Viaje", max_length=20, unique=True, blank=True,
                                help_text="Auto-generado tipo V-000001")
    folio_carga = models.CharField("Folio de Carga", max_length=50, blank=True, null=True)
    fecha_viaje = models.DateField("Fecha del Viaje")
    operador = models.ForeignKey('RH.Empleado', on_delete=models.PROTECT,
                                  related_name='viajes', verbose_name="Operador")
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT,
                                related_name='viajes', verbose_name="Unidad")
    origen = models.ForeignKey(Lugar, on_delete=models.PROTECT,
                                related_name='viajes_origen', verbose_name="Lugar de Origen")
    destino = models.ForeignKey(Lugar, on_delete=models.PROTECT,
                                 related_name='viajes_destino', verbose_name="Lugar de Destino")
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='viajes', verbose_name="Empresa")
    sueldo_operador = models.DecimalField("Sueldo del operador", max_digits=12, decimal_places=2,
                                           default=0, help_text="Pago al operador por este viaje")
    eco_remolque = models.CharField("Eco. Remolque", max_length=50, blank=True, null=True)
    placa_remolque = models.CharField("Placa Remolque", max_length=50, blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PLANIFICADO')
    observaciones = models.TextField(blank=True, null=True)
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='viajes_creados')
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Viaje"
        verbose_name_plural = "Viajes"
        ordering = ['-numero_viaje']
        permissions = [
            ('acceso_viajes', 'Acceso al módulo de Viajes / Cartas de Traslado'),
            ('exportar_viajes_pdf', 'Puede exportar Cartas de Traslado a PDF'),
        ]

    def save(self, *args, **kwargs):
        from django.db.models import Max
        if not self.numero_viaje:
            last = Viaje.objects.aggregate(m=Max('numero_viaje'))['m']
            self.numero_viaje = (last or 0) + 1
        if not self.id_viaje:
            self.id_viaje = f"V-{self.numero_viaje:06d}"
        super().save(*args, **kwargs)

    @property
    def kms_totales(self):
        return sum((p.kms or 0) for p in self.paradas.all())

    @property
    def mismo_origen_destino(self):
        return self.origen_id is not None and self.origen_id == self.destino_id

    def __str__(self):
        return f"{self.id_viaje} — {self.origen} → {self.destino}"


class ItinerarioParada(models.Model):
    """Cada parada del itinerario del viaje (orden y kilómetros)."""
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='paradas')
    lugar = models.ForeignKey(Lugar, on_delete=models.PROTECT, related_name='paradas')
    orden = models.PositiveSmallIntegerField(default=1)
    fecha_hora = models.DateTimeField("Fecha y hora", blank=True, null=True)
    kms = models.DecimalField("Kilómetros", max_digits=10, decimal_places=3, default=0)
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Parada del Itinerario"
        verbose_name_plural = "Paradas del Itinerario"
        ordering = ['viaje', 'orden']

    def __str__(self):
        return f"{self.viaje.id_viaje} — #{self.orden} {self.lugar}"


class ViajeMercancia(models.Model):
    """Mercancía transportada en un tramo (origen→destino) del viaje."""
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='mercancias')
    parada_origen = models.ForeignKey(ItinerarioParada, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='mercancias_origen')
    parada_destino = models.ForeignKey(ItinerarioParada, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='mercancias_destino')
    clave_producto = models.CharField("Clave SAT del Producto", max_length=20, blank=True, null=True,
                                       help_text="Ej: 14121503")
    descripcion = models.CharField("Descripción", max_length=255)
    cantidad = models.DecimalField("Cantidad", max_digits=12, decimal_places=2, default=1)
    peso_kg = models.DecimalField("Peso (kg)", max_digits=12, decimal_places=3, default=0)
    unidad_medida = models.CharField("Unidad de medida", max_length=10, default='H87',
                                      help_text="Código SAT: H87=Pieza, KGM=Kilogramo, TNE=Tonelada métrica")
    material_peligroso = models.BooleanField("¿Material peligroso?", default=False)
    notas = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Mercancía del Viaje"
        verbose_name_plural = "Mercancías del Viaje"
        ordering = ['viaje', 'id']

    def __str__(self):
        return f"{self.descripcion} ({self.cantidad} × {self.peso_kg} kg)"


# ═══════════════════════════════════════════════════════════════════════════════
# LIQUIDACIONES DE OPERADOR
# ═══════════════════════════════════════════════════════════════════════════════

class LiquidacionOperador(models.Model):
    """
    Liquidación de pago a un operador por un periodo (semana / quincena / mes).
    Suma los sueldos de los viajes en el rango + extras manuales - descuentos.
    """
    ESTADO_CHOICES = [
        ('BORRADOR', 'Borrador'),
        ('APROBADA', 'Aprobada'),
        ('PAGADA',   'Pagada'),
        ('CANCELADA', 'Cancelada'),
    ]

    folio = models.CharField("Folio", max_length=20, unique=True, blank=True,
                              help_text="Auto-generado tipo L-000001")
    operador = models.ForeignKey('RH.Empleado', on_delete=models.PROTECT,
                                  related_name='liquidaciones', verbose_name="Operador")
    fecha_inicio = models.DateField("Periodo desde")
    fecha_fin = models.DateField("Periodo hasta")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='BORRADOR')
    fecha_pago = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True, null=True)
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='liquidaciones_creadas')
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Liquidación de Operador"
        verbose_name_plural = "Liquidaciones de Operador"
        ordering = ['-creado_en']
        permissions = [
            ('acceso_liquidaciones', 'Acceso al módulo de Liquidaciones de Operador'),
        ]

    def save(self, *args, **kwargs):
        if not self.folio:
            from django.db.models import Max
            last = LiquidacionOperador.objects.aggregate(m=Max('folio'))['m']
            try:
                last_num = int(last.split('-')[1]) if last else 0
            except (AttributeError, IndexError, ValueError):
                last_num = 0
            self.folio = f"L-{last_num + 1:06d}"
        super().save(*args, **kwargs)

    @property
    def total_viajes(self):
        return sum((c.monto or 0) for c in self.conceptos.filter(tipo='VIAJE'))

    @property
    def total_extras(self):
        return sum((c.monto or 0) for c in self.conceptos.filter(tipo='EXTRA'))

    @property
    def total_descuentos(self):
        return sum((c.monto or 0) for c in self.conceptos.filter(tipo='DESCUENTO'))

    @property
    def total_pagar(self):
        return self.total_viajes + self.total_extras - self.total_descuentos

    def __str__(self):
        return f"{self.folio} — {self.operador} ({self.fecha_inicio} a {self.fecha_fin})"


class LiquidacionConcepto(models.Model):
    """Cada renglón de la liquidación: viaje, extra (bono, peaje) o descuento."""
    TIPO_CHOICES = [
        ('VIAJE',     'Viaje'),
        ('EXTRA',     'Extra / Bono'),
        ('DESCUENTO', 'Descuento'),
    ]
    liquidacion = models.ForeignKey(LiquidacionOperador, on_delete=models.CASCADE, related_name='conceptos')
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, default='VIAJE')
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    viaje = models.ForeignKey(Viaje, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='conceptos_liquidacion')

    class Meta:
        verbose_name = "Concepto de Liquidación"
        verbose_name_plural = "Conceptos de Liquidación"
        ordering = ['liquidacion', 'id']

    def __str__(self):
        return f"{self.tipo}: {self.descripcion} (${self.monto})"


class ManifiestoResiduos(models.Model):
    """Manifiesto oficial de Entrega, Transporte y Destino de Residuos de Manejo
    Especial (formato SMA Nuevo Leon). Los campos de los 4 apartados (Generador,
    Carga de residuos, Transporte, Destinatario) y la tabla de residuos se
    guardan en un JSONField `datos` para flexibilidad; con ellos se llena el
    formulario en la app y se genera el PDF con ese mismo formato oficial."""
    no_manifiesto = models.CharField(max_length=100, blank=True, default="", verbose_name="No. de manifiesto")
    datos = models.JSONField(default=dict, blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="manifiestos_residuos")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
        verbose_name = "Manifiesto de Residuos"
        verbose_name_plural = "Manifiestos de Residuos"

    def __str__(self):
        return self.no_manifiesto or f"Manifiesto {self.id}"
