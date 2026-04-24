# RH/models.py
from django.db import models
from django.core.validators import RegexValidator
import os
import uuid
from django.contrib.auth.models import User
from datetime import date, timedelta
from django.db.models import Sum
import math
from django.utils import timezone
from decimal import Decimal
import math
from datetime import date
import uuid

# --- Funciones de subida de archivos ---
def get_upload_path(instance, filename, path):
    """ Genera una ruta de archivo única usando UUID. """
    ext = os.path.splitext(filename)[1]
    new_filename = f"{uuid.uuid4()}{ext}"
    return os.path.join(path, new_filename)

def empleado_foto_perfil_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_fotos/')

def empleado_ine_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/ine/')

def empleado_domicilio_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/domicilio/')

def empleado_cv_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/cv/')

def operador_documento_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/operador/')

def historial_documento_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/historial/')

def contrato_documento_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/contratos/')

# --- Rutas para nuevos documentos ---
def empleado_acta_nacimiento_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/acta_nacimiento/')

def empleado_comprobante_estudios_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/estudios/')

def empleado_carta_recomendacion_1_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/recomendacion/')

def empleado_carta_recomendacion_2_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/recomendacion/')

def empleado_constancia_fiscal_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/fiscal/')

def empleado_aviso_infonavit_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/infonavit/')

def empleado_semanas_imss_path(instance, filename):
    return get_upload_path(instance, filename, 'empleados_documentos/imss/')


class DivisionOperativa(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "División Operativa"
        verbose_name_plural = "Divisiones Operativas"
        ordering = ['nombre']
        
class TipoCarga(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

class TipoViaje(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

class Departamento(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='departamentos_creados')

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

    def __str__(self):
        return self.nombre

class Puesto(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre del puesto (ej. 'Gerente de Ventas', 'Operador de Tráfico')")
    descripcion = models.TextField(blank=True, null=True, help_text="Descripción detallada del puesto.")
    salario_base = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Salario base mensual para este puesto.")
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='puestos_creados')

    class Meta:
        verbose_name = "Puesto"
        verbose_name_plural = "Puestos"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

class MotivoInactivacion(models.Model):
    motivo = models.CharField(max_length=200, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Motivo de Inactivación"
        verbose_name_plural = "Motivos de Inactivación"
        ordering = ['motivo']

    def __str__(self):
        return self.motivo
    
class EmpleadoQuerySet(models.QuerySet):
    """QuerySet personalizado para Empleado"""
    
    def activos(self):
        """Empleados que NO están eliminados y están activos"""
        return self.filter(eliminado=False, activo=True)
    
    def inactivos(self):
        """Empleados que NO están eliminados y están inactivos"""
        return self.filter(eliminado=False, activo=False)
    
    def eliminados(self):
        """Empleados marcados como eliminados (papelera)"""
        return self.filter(eliminado=True)
    
    def no_eliminados(self):
        """Empleados NO eliminados"""
        return self.filter(eliminado=False)
    
    def eliminar(self, usuario=None, motivo=""):
        """Soft delete - marca como eliminado en lugar de borrar"""
        for empleado in self:
            empleado.soft_delete(usuario=usuario, motivo=motivo)
        return self.count()
    
    def eliminar_permanentemente(self):
        """Eliminación permanente (solo para administradores)"""
        count = 0
        for empleado in self:
            empleado.eliminar_permanentemente()
            count += 1
        return count

class EmpleadoManager(models.Manager):
    """Manager personalizado para Empleado"""
    
    def get_queryset(self):
        return EmpleadoQuerySet(self.model, using=self._db)
    
    def activos(self):
        return self.get_queryset().activos()
    
    def inactivos(self):
        return self.get_queryset().inactivos()
    
    def eliminados(self):
        return self.get_queryset().eliminados()
    
    def no_eliminados(self):
        return self.get_queryset().no_eliminados()

class Empleado(models.Model):

    # Reemplazar el manager por defecto
    objects = EmpleadoManager()

    id = models.UUIDField(
    primary_key=True,
    default=uuid.uuid4,
    editable=False
    )
    puesto_anterior = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    fecha_ingreso = models.DateField(default=timezone.now, null=True, blank=True)

    # ✅ NUEVO: ID DEL SISTEMA DE ORIGEN (EXCEL / BACKUP)
    origen_id = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="ID original del sistema de origen (importaciones/backups)"
    )

    numero_empleado = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True
    )

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)

    puesto = models.ForeignKey(
        'Puesto',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Puesto"
    )

    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empleados'
    )

    fecha_contratacion = models.DateField(default=timezone.now, null=True, blank=True)

    email = models.EmailField(unique=True, null=True, blank=True)

    activo = models.BooleanField(default=True)

    motivo_inactivacion = models.ForeignKey(
        MotivoInactivacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Motivo por el cual el empleado fue inactivado."
    )

    fecha_inactivacion = models.DateField(null=True, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)

    # --- CAMPOS PARA SOFT DELETE ---
    eliminado = models.BooleanField(default=False, verbose_name="Eliminado")
    fecha_eliminacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de eliminación")
    motivo_eliminacion = models.TextField(blank=True, null=True, verbose_name="Motivo de eliminación")

    eliminado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empleados_eliminados',
        verbose_name="Eliminado por"
    )

    # --- CAMPOS DE DOMICILIO ---
    direccion = models.CharField(max_length=255, blank=True, null=True)
    colonia = models.CharField(max_length=100, blank=True, null=True)
    codigo_postal = models.CharField(max_length=10, blank=True, null=True)
    ciudad = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=100, blank=True, null=True)
    pais = models.CharField(max_length=50, default="México", blank=True, null=True)

    telefono_personal = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="El número de teléfono debe estar en el formato: '+999999999'. Hasta 15 dígitos permitidos."
            )
        ]
    )

    ESTADO_CIVIL_CHOICES = [
        ('Soltero/a', 'Soltero/a'),
        ('Casado/a', 'Casado/a'),
        ('Viudo/a', 'Viudo/a'),
        ('Divorciado/a', 'Divorciado/a'),
        ('Unión Libre', 'Unión Libre'),
    ]

    estado_civil = models.CharField(max_length=20, choices=ESTADO_CIVIL_CHOICES, blank=True, null=True)
    nacionalidad = models.CharField(max_length=50, default="Mexicana", blank=True, null=True)

    curp = models.CharField(
        max_length=18,
        unique=True,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r'^[A-Z]{4}[0-9]{6}[H,M][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[0-9A-Z]{2}$',
                message="Formato de CURP inválido."
            )
        ]
    )

    rfc = models.CharField(
        max_length=13,
        unique=True,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r'^[A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3}$',
                message="Formato de RFC inválido."
            )
        ]
    )

    nss = models.CharField(
        max_length=11,
        unique=True,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r'^\d{11}$',
                message="NSS debe ser un número de 11 dígitos."
            )
        ]
    )

    # --- FAMILIA / SUPERVISOR ---
    supervisor = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipo_a_cargo'
    )

    nombre_conyuge = models.CharField(max_length=200, blank=True, null=True)
    telefono_conyuge = models.CharField(max_length=15, blank=True, null=True)

    foto_perfil = models.ImageField(upload_to=empleado_foto_perfil_path, null=True, blank=True)

    banco = models.CharField(max_length=100, blank=True, null=True)
    clabe_interbancaria = models.CharField(max_length=18, blank=True, null=True)
    numero_cuenta = models.CharField(max_length=20, blank=True, null=True)
    numero_tarjeta = models.CharField(max_length=16, blank=True, null=True)

    nombre_referencia_1 = models.CharField(max_length=100, blank=True, null=True)
    telefono_referencia_1 = models.CharField(max_length=15, blank=True, null=True)
    relacion_referencia_1 = models.CharField(max_length=50, blank=True, null=True)

    nombre_referencia_2 = models.CharField(max_length=100, blank=True, null=True)
    telefono_referencia_2 = models.CharField(max_length=15, blank=True, null=True)
    relacion_referencia_2 = models.CharField(max_length=50, blank=True, null=True)

    # --- DOCUMENTOS ---
    ine_documento = models.FileField(upload_to=empleado_ine_path, null=True, blank=True)
    comprobante_domicilio = models.FileField(upload_to=empleado_domicilio_path, null=True, blank=True)
    curriculum_vitae = models.FileField(upload_to=empleado_cv_path, null=True, blank=True)

    acta_nacimiento_documento = models.FileField(upload_to=empleado_acta_nacimiento_path, null=True, blank=True)
    comprobante_estudios_documento = models.FileField(upload_to=empleado_comprobante_estudios_path, null=True, blank=True)
    carta_recomendacion_1_documento = models.FileField(upload_to=empleado_carta_recomendacion_1_path, null=True, blank=True)
    carta_recomendacion_2_documento = models.FileField(upload_to=empleado_carta_recomendacion_2_path, null=True, blank=True)
    constancia_fiscal_documento = models.FileField(upload_to=empleado_constancia_fiscal_path, null=True, blank=True)
    aviso_retencion_infonavit_documento = models.FileField(upload_to=empleado_aviso_infonavit_path, null=True, blank=True)
    semanas_cotizadas_imss_documento = models.FileField(upload_to=empleado_semanas_imss_path, null=True, blank=True)

    # --- INFORMACIÓN OPERATIVA ---
    EMPRESA_CHOICES = [
        ('MIGMAR', 'Migmar'),
        ('MARCO_MORALES', 'Marco Morales'),
        ('CHIHUAHUA', 'Chihuahua'),
    ]

    empresa = models.CharField(max_length=20, choices=EMPRESA_CHOICES, blank=True, null=True)

    division_operativa = models.ManyToManyField(DivisionOperativa, blank=True)
    tipo_carga = models.ManyToManyField(TipoCarga, blank=True)
    tipo_viaje = models.ManyToManyField(TipoViaje, blank=True)
    
    # --- PROPIEDADES PARA SIMPLIFICAR PLANTILLAS ---
    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        today = date.today()
        return today.year - self.fecha_nacimiento.year - ((today.month, today.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))

    @property
    def antiguedad(self):
        if not self.fecha_contratacion:
            return 0
        return (date.today() - self.fecha_contratacion).days // 365

    @property
    def salario_actual(self):
        return self.salarios.order_by('-fecha_efectiva').first()
    
    # --- MÉTODOS PARA SOFT DELETE ---
    def soft_delete(self, usuario=None, motivo=""):
        """Marca el empleado como eliminado (soft delete)"""
        self.eliminado = True
        self.fecha_eliminacion = timezone.now()
        self.eliminado_por = usuario
        self.motivo_eliminacion = motivo
        self.save()
        return True
    
    def restaurar(self):
        """Restaurar empleado desde la papelera"""
        self.eliminado = False
        self.fecha_eliminacion = None
        self.eliminado_por = None
        self.motivo_eliminacion = None
        self.save()
        return True
    
    def eliminar_permanentemente(self, *args, **kwargs):
        """Eliminación permanente (solo para administradores)"""
        # Primero eliminar archivos adjuntos
        self._eliminar_archivos_adjuntos()
        # Luego llamar al delete del padre para eliminación permanente
        return super().delete(*args, **kwargs)
    
    def _eliminar_archivos_adjuntos(self):
        """Elimina archivos adjuntos antes de borrar permanentemente (S3 compatible)"""
        adjuntos = [
            self.foto_perfil, self.ine_documento, self.comprobante_domicilio,
            self.curriculum_vitae, self.acta_nacimiento_documento,
            self.comprobante_estudios_documento, self.carta_recomendacion_1_documento,
            self.carta_recomendacion_2_documento, self.constancia_fiscal_documento,
            self.aviso_retencion_infonavit_documento, self.semanas_cotizadas_imss_documento
        ]
        
        for adjunto in adjuntos:
            if adjunto:
                try:
                    adjunto.delete(save=False)
                except Exception as e:
                    print(f"Error eliminando adjunto: {e}")

    @property
    def documentos_count(self):
        base_docs = 0
        if self.ine_documento: base_docs += 1
        if self.comprobante_domicilio: base_docs += 1
        if self.curriculum_vitae: base_docs += 1
        if self.acta_nacimiento_documento: base_docs += 1
        if self.comprobante_estudios_documento: base_docs += 1
        if self.carta_recomendacion_1_documento: base_docs += 1
        if self.carta_recomendacion_2_documento: base_docs += 1
        if self.constancia_fiscal_documento: base_docs += 1
        if self.aviso_retencion_infonavit_documento: base_docs += 1
        if self.semanas_cotizadas_imss_documento: base_docs += 1
        return base_docs + self.documentos_operador.count() + self.contratos.count()
    
    @property
    def companeros_departamento(self):
        if not self.departamento:
            return Empleado.objects.none()
        return Empleado.objects.filter(departamento=self.departamento, activo=True).exclude(pk=self.pk)

    class Meta:
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"
        ordering = ['apellido', 'nombre']

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

# --- NUEVO MODELO PARA HIJOS ---
class Hijo(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='hijos')
    nombre = models.CharField(max_length=200)
    fecha_nacimiento = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Hijo/a de {self.empleado}: {self.nombre}"
    
    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        today = date.today()
        # Cálculo preciso de la edad
        return today.year - self.fecha_nacimiento.year - ((today.month, today.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))

    class Meta:
        verbose_name = "Hijo"
        verbose_name_plural = "Hijos"
        ordering = ['fecha_nacimiento']

class Salario(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='salarios')
    sueldo_diario = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_efectiva = models.DateField(help_text="Fecha a partir de la cual este salario es efectivo.")
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Salario"
        verbose_name_plural = "Salarios"
        ordering = ['-fecha_efectiva']

    @property
    def sueldo_semanal(self):
        if self.sueldo_diario is not None:
            return self.sueldo_diario * 7
        return None
    
    @property
    def dias_vacaciones_disponibles(self):
        """
        Calcula los días de vacaciones disponibles según años de servicio
        """
        if not self.empleado.fecha_contratacion:
            return 0
        
        años_servicio = self.empleado.antiguedad
        
        try:
            config = ConfiguracionVacacion.objects.filter(
                años_minimo__lte=años_servicio
            ).order_by('-años_minimo').first()
            
            if config:
                # Restar vacaciones ya tomadas este año
                hoy = date.today()
                inicio_año = date(hoy.year, 1, 1)
                
                vacaciones_tomadas = Vacacion.objects.filter(
                    empleado=self.empleado,
                    estado='tomado',
                    fecha_inicio__gte=inicio_año
                ).aggregate(total=Sum('dias_solicitados'))['total'] or 0
                
                return max(0, config.dias_vacaciones - vacaciones_tomadas)
            
        except:
            pass
        
        return 0

    @property
    def historial_vacaciones(self):
        """Vacaciones del empleado ordenadas por fecha"""
        return self.empleado.vacaciones.all().order_by('-fecha_solicitud')

    @property
    def prestamos_activos(self):
        """Préstamos activos del empleado"""
        return self.empleado.prestamos.filter(estado='activo')

    @property
    def total_adeudado(self):
        """Total adeudado en préstamos"""
        prestamos_activos = self.prestamos_activos
        return sum(prestamo.saldo_pendiente for prestamo in prestamos_activos)

    @property
    def sueldo_mensual(self):
        if self.sueldo_diario is not None:
            return self.sueldo_diario * 30
        return None

    def __str__(self):
        return f"Salario de {self.empleado} - ${self.sueldo_diario}/día desde {self.fecha_efectiva}"

class TipoDocumentoOperador(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej. 'Licencia de Conducir', 'Certificado Médico'")
    descripcion = models.TextField(blank=True, null=True)
    requiere_fecha_vencimiento = models.BooleanField(default=False, help_text="Indica si este tipo de documento tiene una fecha de vencimiento.")

    class Meta:
        verbose_name = "Tipo de Documento de Operador"
        verbose_name_plural = "Tipos de Documentos de Operador"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class DocumentoOperador(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='documentos_operador')
    tipo_documento = models.ForeignKey(TipoDocumentoOperador, on_delete=models.PROTECT)
    archivo = models.FileField(upload_to=operador_documento_path)
    numero_documento = models.CharField(max_length=100, blank=True, null=True, help_text="Número de licencia, folio, etc.")
    fecha_expedicion = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Documento de Operador"
        verbose_name_plural = "Documentos de Operador"
        unique_together = ('empleado', 'tipo_documento', 'numero_documento')
        ordering = ['empleado__apellido', 'empleado__nombre', 'tipo_documento__nombre']

    def delete(self, *args, **kwargs):
        if self.archivo:
            self.archivo.delete(save=False)
        super().delete(*args, **kwargs)

class HistorialLaboral(models.Model):
    EVENT_CHOICES = [
        ('CAMBIO_PUESTO', 'Cambio de Puesto'),
        ('SUSPENSION', 'Suspensión'),
        ('INCAPACIDAD', 'Incapacidad'),
        ('ACTA_ADMINISTRATIVA', 'Acta Administrativa'),
        ('PERMISO', 'Permiso'),
        ('RECONTRATACION', 'Re-contratación'),
        ('RENUNCIA', 'Renuncia'),
        ('BAJA', 'Baja'),
        ('ABANDONO', 'Abandono'),
    ]
    MOTIVO_SALIDA_CHOICES = [
        ('Renuncia', (
            ('AMBIENTE_LABORAL', 'Ambiente laboral'),
            ('LIDERAZGO_RENUNCIA', 'Liderazgo'),
            ('MOTIVOS_PERSONALES', 'Motivos personales'),
            ('PRESTACIONES', 'Prestaciones'),
        )),
        ('Baja', (
            ('RESICION_CONTRATO', 'Rescisión de Contrato'),
            ('FALTAS_REGLAMENTO', 'Faltas al Reglamento'),
            ('TERMINO_CONTRATO', 'Término de Contrato'),
            ('BAJO_RENDIMIENTO', 'Bajo Rendimiento'),
        )),
        ('Abandono', (
            ('FALTAS_INJUSTIFICADAS', 'Faltas injustificadas'),
            ('LIDERAZGO_ABANDONO', 'Liderazgo'),
            ('PAGO', 'Pago'),
        )),
    ]
    
    ESTATUS_CHOICES = [
        ('BUSCANDO', 'Buscando Reemplazo'),
        ('REMPLAZADO', 'Reemplazado'),
    ]
    MOTIVO_SALIDA_CHOICES_FLAT = [choice for group in MOTIVO_SALIDA_CHOICES for choice in group[1]]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='historial_laboral_eventos')
    tipo_evento = models.CharField(max_length=50, choices=EVENT_CHOICES, verbose_name="Tipo de Evento")
    fecha_inicio = models.DateField(verbose_name="Fecha del Evento / Inicio")
    fecha_fin = models.DateField(null=True, blank=True, verbose_name="Fecha de Fin (si aplica)")
    puesto = models.CharField(max_length=100, blank=True, null=True, help_text="Nuevo puesto del empleado.")
    departamento = models.CharField(max_length=100, blank=True, null=True, help_text="Nuevo departamento del empleado.")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción / Observaciones")
    motivo_salida = models.CharField(max_length=50, choices=MOTIVO_SALIDA_CHOICES, blank=True, null=True, help_text="Detallar el motivo si el evento es una Renuncia, Baja o Abandono.")
    documento_adjunto = models.FileField(upload_to=historial_documento_path, null=True, blank=True, verbose_name="Adjuntar Documento")

     # --- NUEVOS CAMPOS ---
    estatus = models.CharField(
        max_length=20,
        choices=ESTATUS_CHOICES,
        default='BUSCANDO',
        verbose_name="Estatus de la Vacante"
    )
    reemplazo = models.ForeignKey(
        Empleado,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reemplaza_a',
        help_text="Empleado que cubre esta vacante."
    )
    fecha_reemplazo = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Asignación del Reemplazo"
    )


    class Meta:
        verbose_name = "Evento de Historial Laboral"
        verbose_name_plural = "Eventos de Historial Laboral"
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f"{self.get_tipo_evento_display()} para {self.empleado} el {self.fecha_inicio}"

    def delete(self, *args, **kwargs):
        if self.documento_adjunto:
            self.documento_adjunto.delete(save=False)
        super().delete(*args, **kwargs)

class Contrato(models.Model):
    TIPO_CONTRATO_CHOICES = [
        ('DETERMINADO', 'Determinado'),
        ('INDETERMINADO', 'Indeterminado'),
    ]
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='contratos')
    tipo_contrato = models.CharField(max_length=20, choices=TIPO_CONTRATO_CHOICES)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True, help_text="Requerido solo si el contrato es de tipo 'Determinado'")
    archivo_contrato = models.FileField(upload_to=contrato_documento_path, null=True, blank=True, verbose_name="Archivo del Contrato")
    comentarios = models.TextField(blank=True, null=True, verbose_name="Comentarios")

    class Meta:
        verbose_name = "Contrato"
        verbose_name_plural = "Contratos"
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f"Contrato {self.get_tipo_contrato_display()} para {self.empleado} desde {self.fecha_inicio}"

    def delete(self, *args, **kwargs):
        if self.archivo_contrato:
            self.archivo_contrato.delete(save=False)
        super().delete(*args, **kwargs)
        
    @property
    def duracion(self):
        if not self.fecha_fin:
            return "Indefinido"
        
        delta = self.fecha_fin - self.fecha_inicio
        years = delta.days // 365
        months = (delta.days % 365) // 30
        
        if years > 0:
            return f"{years} año(s)"
        elif months > 0:
            return f"{months} mes(es)"
        else:
            return f"{delta.days} día(s)"
        

class MotivoBaja(models.Model):
    """
    Modelo para los motivos de baja jerarquizados
    """
    TIPO_MOTIVO_CHOICES = [
        ('PRINCIPAL', 'Motivo Principal'),
        ('SECUNDARIO', 'Motivo Secundario'),
        ('DETALLE', 'Detalle Específico'),
    ]
    
    nombre = models.CharField(max_length=100)
    tipo_motivo = models.CharField(
        max_length=20, 
        choices=TIPO_MOTIVO_CHOICES,
        default='DETALLE'
    )
    padre = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='submotivos'
    )
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['tipo_motivo', 'nombre']
        verbose_name = 'Motivo de Baja'
        verbose_name_plural = 'Motivos de Baja'
    
    def __str__(self):
        if self.padre:
            return f"{self.padre.nombre} > {self.nombre}"
        return self.nombre
    
    @property
    def es_principal(self):
        return self.tipo_motivo == 'PRINCIPAL'
    
    @property
    def es_secundario(self):
        return self.tipo_motivo == 'SECUNDARIO'
    
    @property
    def es_detalle(self):
        return self.tipo_motivo == 'DETALLE'


class BajaEmpleado(models.Model):
    """
    Modelo para registrar las bajas de empleados con todos los detalles
    """
    empleado = models.ForeignKey(
        'Empleado', 
        on_delete=models.CASCADE,
        related_name='bajas'
    )
    
    # Motivos jerarquizados
    motivo_principal = models.ForeignKey(
        MotivoBaja,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bajas_principales',
        limit_choices_to={'tipo_motivo': 'PRINCIPAL', 'activo': True}
    )
    
    motivo_secundario = models.ForeignKey(
        MotivoBaja,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bajas_secundarias',
        limit_choices_to={'tipo_motivo': 'SECUNDARIO', 'activo': True}
    )
    
    motivo_detalle = models.ForeignKey(
        MotivoBaja,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bajas_detalles',
        limit_choices_to={'tipo_motivo': 'DETALLE', 'activo': True}
    )
    
    # Información de la baja
    fecha_baja = models.DateField(default=date.today)
    comentario_baja = models.TextField(verbose_name="Comentario de Baja")
    documento_baja = models.FileField(
        upload_to='bajas/documentos/',
        null=True,
        blank=True,
        verbose_name="Documento de Baja"
    )
    
    # Recontratación
    es_recontratable = models.BooleanField(
        default=False,
        verbose_name="¿Es recontratable?"
    )
    motivo_recontratable = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motivo por el cual es recontratable"
    )
    fecha_posible_recontratacion = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha posible de recontratación"
    )

    # NUEVOS CAMPOS PARA CONCILIACIÓN Y ARBITRAJE
    fue_conciliacion_arbitraje = models.BooleanField(
        default=False,
        verbose_name="¿Fue a Conciliación y Arbitraje?",
        help_text="Selecciona si el empleado acudió a Conciliación y Arbitraje"
    )
    
    fecha_conciliacion_arbitraje = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Conciliación y Arbitraje"
    )
    
    documento_conciliacion = models.FileField(
        upload_to='bajas/conciliacion_arbitraje/',
        null=True,
        blank=True,
        verbose_name="Documento de Conciliación y Arbitraje",
        help_text="Sube el documento oficial de Conciliación y Arbitraje"
    )
    
    observaciones_conciliacion = models.TextField(
        blank=True,
        null=True,
        verbose_name="Observaciones de Conciliación",
        help_text="Observaciones adicionales sobre el proceso de conciliación"
    )
    
    # Campos del sistema
    fecha_registro = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bajas_registradas'
    )
    
    # Recontratado
    recontratado = models.BooleanField(default=False)
    fecha_recontratacion = models.DateField(null=True, blank=True)
    comentario_recontratacion = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-fecha_baja', '-fecha_registro']
        verbose_name = 'Baja de Empleado'
        verbose_name_plural = 'Bajas de Empleados'
    
    def __str__(self):
        return f"Baja de {self.empleado.nombre_completo} - {self.fecha_baja}"
    
    @property
    def cadena_motivos(self):
        """Retorna la cadena completa de motivos"""
        motivos = []
        if self.motivo_principal:
            motivos.append(self.motivo_principal.nombre)
        if self.motivo_secundario:
            motivos.append(f" > {self.motivo_secundario.nombre}")
        if self.motivo_detalle:
            motivos.append(f" > {self.motivo_detalle.nombre}")
        return ' '.join(motivos) if motivos else "Sin motivo especificado"
    
    @property
    def dias_desde_baja(self):
        if self.fecha_baja:
            return (date.today() - self.fecha_baja).days
        return 0
    
    def recontratar(self, fecha_recontratacion=None, comentario=None):
        """Método para recontratar al empleado"""
        if not self.es_recontratable:
            return False
        
        self.recontratado = True
        self.fecha_recontratacion = fecha_recontratacion or date.today()
        self.comentario_recontratacion = comentario
        self.save()
        
        # Reactivar al empleado
        self.empleado.activo = True
        self.empleado.motivo_inactivacion = None
        self.empleado.fecha_inactivacion = None
        self.empleado.save()
        
        # Crear registro en historial laboral
        HistorialLaboral.objects.create(
            empleado=self.empleado,
            tipo_evento='RECONTRATACION',
            fecha_inicio=self.fecha_recontratacion,
            descripcion=f"Recontratación después de baja. {comentario or ''}",
            motivo_salida='RECONTRATACION'
        )
        
        return True
    
def crear_motivos_baja_iniciales():
    """Crea los motivos de baja iniciales"""
    from django.db import transaction
    
    with transaction.atomic():
        # Motivos Principales
        renuncia = MotivoBaja.objects.create(
            nombre='Renuncia Voluntaria',
            tipo_motivo='PRINCIPAL',
            descripcion='El empleado decide dejar la empresa por voluntad propia'
        )
        
        recision = MotivoBaja.objects.create(
            nombre='Recisión de Contrato',
            tipo_motivo='PRINCIPAL',
            descripcion='La empresa decide terminar el contrato por causas justificadas'
        )
        
        terminacion = MotivoBaja.objects.create(
            nombre='Terminación de Contrato',
            tipo_motivo='PRINCIPAL',
            descripcion='Finalización natural del contrato determinado'
        )
        
        indisciplina = MotivoBaja.objects.create(
            nombre='Indisciplina',
            tipo_motivo='PRINCIPAL',
            descripcion='Falta grave a las normas de conducta'
        )
        
        abandono = MotivoBaja.objects.create(
            nombre='Abandono',
            tipo_motivo='PRINCIPAL',
            descripcion='El empleado abandona sus funciones sin notificación'
        )
        
        # Motivos Secundarios para Renuncia Voluntaria
        MotivoBaja.objects.create(
            nombre='Temas Familiares',
            tipo_motivo='SECUNDARIO',
            padre=renuncia,
            descripcion='Problemas o situaciones familiares'
        )
        
        MotivoBaja.objects.create(
            nombre='Crecimiento Laboral',
            tipo_motivo='SECUNDARIO',
            padre=renuncia,
            descripcion='Oportunidad de crecimiento en otra empresa'
        )
        
        MotivoBaja.objects.create(
            nombre='Cambio de Puesto',
            tipo_motivo='SECUNDARIO',
            padre=renuncia,
            descripcion='Desempeñar diferentes funciones'
        )
        
        # Motivos Secundarios para Recisión de Contrato
        MotivoBaja.objects.create(
            nombre='Robo',
            tipo_motivo='SECUNDARIO',
            padre=recision,
            descripcion='Sustracción de bienes de la empresa'
        )
        
        MotivoBaja.objects.create(
            nombre='Consumo de Droga',
            tipo_motivo='SECUNDARIO',
            padre=recision,
            descripcion='Uso de sustancias prohibidas'
        )
        
        MotivoBaja.objects.create(
            nombre='Indisciplina Grave',
            tipo_motivo='SECUNDARIO',
            padre=recision,
            descripcion='Incumplimiento grave de reglamentos'
        )
        
        MotivoBaja.objects.create(
            nombre='Faltas Injustificadas',
            tipo_motivo='SECUNDARIO',
            padre=recision,
            descripcion='Ausencias sin justificación'
        )
        
        MotivoBaja.objects.create(
            nombre='Abandono de Unidad',
            tipo_motivo='SECUNDARIO',
            padre=recision,
            descripcion='Dejar vehículo o equipo sin supervisión'
        )
        
        MotivoBaja.objects.create(
            nombre='Viaje Tirado',
            tipo_motivo='SECUNDARIO',
            padre=recision,
            descripcion='Abandonar un viaje en curso'
        )
        
        # Motivos Secundarios para Abandono
        MotivoBaja.objects.create(
            nombre='Ausentismo',
            tipo_motivo='SECUNDARIO',
            padre=abandono,
            descripcion='Inasistencia prolongada sin justificación'
        )
        
        MotivoBaja.objects.create(
            nombre='Abandono de Unidad',
            tipo_motivo='SECUNDARIO',
            padre=abandono,
            descripcion='Dejar vehículo o equipo abandonado'
        )
        
        # Motivos de Detalle
        MotivoBaja.objects.create(
            nombre='Robo de Combustible',
            tipo_motivo='DETALLE',
            padre=MotivoBaja.objects.get(nombre='Robo'),
            descripcion='Sustracción de combustible'
        )
        
        MotivoBaja.objects.create(
            nombre='Robo de Mercancía',
            tipo_motivo='DETALLE',
            padre=MotivoBaja.objects.get(nombre='Robo'),
            descripcion='Sustracción de mercancía transportada'
        )
        
        MotivoBaja.objects.create(
            nombre='3 Faltas Consecutivas',
            tipo_motivo='DETALLE',
            padre=MotivoBaja.objects.get(nombre='Faltas Injustificadas'),
            descripcion='Tres faltas injustificadas consecutivas'
        )
        
        MotivoBaja.objects.create(
            nombre='Más de 5 Faltas en un Mes',
            tipo_motivo='DETALLE',
            padre=MotivoBaja.objects.get(nombre='Faltas Injustificadas'),
            descripcion='Cinco o más faltas en un período de 30 días'
        )

class Vacacion(models.Model):
    """
    Modelo para gestionar las vacaciones de los empleados
    """
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('GOZADO', 'Gozado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    TIPO_VACACION_CHOICES = [
        ('ORDINARIAS', 'Vacaciones Ordinarias'),
        ('ANTICIPADAS', 'Vacaciones Anticipadas'),
        ('PRORROGA', 'Prórroga'),
        ('EXTRA', 'Vacaciones Extra'),
        ('HISTORICO', 'Registro Histórico'),  # Agregado para modo histórico
    ]
    
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='vacaciones')
    tipo_vacacion = models.CharField(max_length=20, choices=TIPO_VACACION_CHOICES, default='ORDINARIAS')
    fecha_solicitud = models.DateField(auto_now_add=True)
    fecha_inicio = models.DateField(verbose_name="Fecha de inicio")
    fecha_fin = models.DateField(verbose_name="Fecha de fin")
    dias_solicitados = models.IntegerField(verbose_name="Días solicitados")
    dias_reales = models.IntegerField(verbose_name="Días reales", null=True, blank=True)
    periodo_correspondiente = models.CharField(
        max_length=7, 
        help_text="Formato: AÑO-MES (ej: 2024-01)"
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    aprobado_por = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='vacaciones_aprobadas'
    )
    fecha_aprobacion = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True, null=True)
    documento_solicitud = models.FileField(
        upload_to='vacaciones/solicitudes/',
        null=True,
        blank=True,
        verbose_name="Documento de solicitud"
    )
    documento_aprobacion = models.FileField(
        upload_to='vacaciones/aprobaciones/',
        null=True,
        blank=True,
        verbose_name="Documento de aprobación"
    )
    
    # Auditoría
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vacaciones_creadas'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-fecha_solicitud', '-fecha_creacion']
        verbose_name = 'Vacación'
        verbose_name_plural = 'Vacaciones'
    
    def save(self, *args, **kwargs):
        """Sobrescribe el método save para calcular los días laborables automáticamente"""
        if self.fecha_inicio and self.fecha_fin:
            # Calcular días laborables (lunes a viernes)
            dias_lab = 0
            fecha_actual = self.fecha_inicio
            while fecha_actual <= self.fecha_fin:
                if fecha_actual.weekday() < 5:  # Lunes a Viernes
                    dias_lab += 1
                fecha_actual += timedelta(days=1)
            self.dias_reales = dias_lab
            
            # También asegurar que dias_solicitados tenga el total calendario si no se especificó
            if not self.dias_solicitados:
                delta = self.fecha_fin - self.fecha_inicio
                self.dias_solicitados = delta.days + 1
                
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Vacaciones de {self.empleado.nombre_completo} - {self.fecha_inicio} a {self.fecha_fin}"
    
    @property
    def dias_total(self):
        """Calcula el total de días de vacación (incluye fines de semana)"""
        if self.fecha_inicio and self.fecha_fin:
            delta = self.fecha_fin - self.fecha_inicio
            return delta.days + 1  # Incluye el día de inicio
        return self.dias_solicitados
    
    @property
    def dias_laborables(self):
        """Calcula días laborables (excluye sábados y domingos)"""
        if not self.fecha_inicio or not self.fecha_fin:
            return self.dias_solicitados
        
        dias_laborables = 0
        fecha_actual = self.fecha_inicio
        
        while fecha_actual <= self.fecha_fin:
            # 0 = lunes, 1 = martes, ..., 5 = sábado, 6 = domingo
            if fecha_actual.weekday() < 5:  # Lunes a Viernes
                dias_laborables += 1
            fecha_actual += timedelta(days=1)
        
        return dias_laborables
    
    @property
    def dias_restantes(self):
        """Días que faltan para empezar las vacaciones"""
        if self.fecha_inicio:
            hoy = date.today()
            dias_restantes = (self.fecha_inicio - hoy).days
            return max(0, dias_restantes)
        return None
    
    @property
    def esta_proxima(self):
        """Verifica si las vacaciones son en los próximos 15 días"""
        if self.fecha_inicio and self.estado == 'APROBADO':
            hoy = date.today()
            dias_restantes = (self.fecha_inicio - hoy).days
            return 0 <= dias_restantes <= 15
        return False


class HistoricoVacaciones(models.Model):
    """
    Historial de días de vacaciones por año para cada empleado
    """
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='historico_vacaciones')
    año = models.IntegerField(verbose_name="Año correspondiente")
    dias_correspondientes = models.IntegerField(verbose_name="Días correspondientes")
    dias_tomados = models.IntegerField(default=0, verbose_name="Días tomados")
    dias_pendientes = models.IntegerField(default=0, verbose_name="Días pendientes")
    dias_antiguedad = models.IntegerField(default=0, verbose_name="Días por antigüedad")
    dias_extra = models.IntegerField(default=0, verbose_name="Días extra")
    fecha_actualizacion = models.DateField(auto_now=True)
    
    class Meta:
        unique_together = ('empleado', 'año')
        ordering = ['-año']
        verbose_name = 'Histórico de Vacaciones'
        verbose_name_plural = 'Históricos de Vacaciones'
    
    def __str__(self):
        return f"{self.empleado.nombre_completo} - {self.año}: {self.dias_pendientes} días"
    
    @property
    def porcentaje_tomado(self):
        if self.dias_correspondientes > 0:
            return (self.dias_tomados / self.dias_correspondientes) * 100
        return 0
    
    def actualizar_dias(self):
        """Actualiza los días pendientes"""
        self.dias_pendientes = self.dias_correspondientes - self.dias_tomados
        self.save()


class Prestamo(models.Model):
    """
    Modelo para gestionar préstamos a empleados con plazos en SEMANAS (1-52)
    """
    ESTADO_CHOICES = [
        ('SOLICITADO', 'Solicitado'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('EN_CURSO', 'En curso'),
        ('PAGADO', 'Pagado'),
        ('MOROSO', 'Moroso'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    TIPO_PRESTAMO_CHOICES = [
        ('PERSONAL', 'Préstamo Personal'),
        ('ADELANTO', 'Adelanto de Sueldo'),
        ('EMERGENCIA', 'Préstamo de Emergencia'),
        ('ESPECIAL', 'Préstamo Especial'),
    ]
    
    empleado = models.ForeignKey('Empleado', on_delete=models.CASCADE, related_name='prestamos')
    tipo_prestamo = models.CharField(max_length=20, choices=TIPO_PRESTAMO_CHOICES, default='PERSONAL')
    fecha_solicitud = models.DateField(auto_now_add=True)
    fecha_aprobacion = models.DateField(null=True, blank=True)
    monto_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto total")
    monto_pagado = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Monto pagado")
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Saldo pendiente")
    tasa_interes = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Tasa de interés anual (%)")
    plazo_semanas = models.IntegerField(verbose_name="Plazo en semanas", help_text="Entre 1 y 52 semanas (1 año)")
    fecha_primer_pago = models.DateField(verbose_name="Fecha primer pago")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='SOLICITADO')
    concepto = models.CharField(max_length=255, verbose_name="Concepto del préstamo")
    observaciones = models.TextField(blank=True, null=True)
    documento_solicitud = models.FileField(
        upload_to='prestamos/solicitudes/',
        null=True,
        blank=True,
        verbose_name="Documento de solicitud"
    )
    contrato = models.FileField(
        upload_to='prestamos/contratos/',
        null=True,
        blank=True,
        verbose_name="Contrato firmado"
    )
    
    # Quién autorizó
    aprobado_por = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='prestamos_aprobados'
    )
    
    # Auditoría
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prestamos_creados'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-fecha_solicitud', '-fecha_creacion']
        verbose_name = 'Préstamo'
        verbose_name_plural = 'Préstamos'
    
    def __str__(self):
        return f"Préstamo {self.tipo_prestamo} - {self.empleado.nombre_completo}: ${self.monto_total}"
    
    def save(self, *args, **kwargs):
        # Calcular saldo pendiente
        if self.monto_total and self.monto_pagado:
            self.saldo_pendiente = self.monto_total - self.monto_pagado
        
        # Validar plazo entre 1 y 52 semanas
        if self.plazo_semanas < 1:
            self.plazo_semanas = 1
        elif self.plazo_semanas > 52:
            self.plazo_semanas = 52
            
        super().save(*args, **kwargs)
    
    @property
    def progreso_pago(self):
        """Porcentaje del préstamo pagado"""
        if self.monto_total > 0:
            return round((self.monto_pagado / self.monto_total) * 100, 2)
        return 0
    
    @property
    def pago_semanal(self):
        """Calcula el pago semanal con Decimal para precisión"""
        if self.plazo_semanas > 0 and self.monto_total > 0:
            # Convertir todo a Decimal
            plazo_decimal = Decimal(str(self.plazo_semanas))
            monto_decimal = Decimal(str(self.monto_total))
            tasa_decimal = Decimal(str(self.tasa_interes))
            
            # Tasa de interés anual convertida a semanal
            interes_anual = tasa_decimal / Decimal('100')
            
            if interes_anual > 0:
                # Tasa semanal = tasa anual / 52 semanas
                tasa_semanal = interes_anual / Decimal('52')
                
                # Fórmula de amortización: P = (r * PV) / (1 - (1 + r)^-n)
                # donde r = tasa semanal, PV = valor presente, n = número de semanas
                uno_mas_r = Decimal('1') + tasa_semanal
                uno_mas_r_pow_n = uno_mas_r ** int(self.plazo_semanas)
                
                numerador = tasa_semanal * uno_mas_r_pow_n
                denominador = uno_mas_r_pow_n - Decimal('1')
                
                if denominador != 0:
                    pago_semanal = monto_decimal * (numerador / denominador)
                else:
                    # Fallback: división simple (sin interés)
                    pago_semanal = monto_decimal / plazo_decimal
            else:
                # Sin interés: división simple
                pago_semanal = monto_decimal / plazo_decimal
            
            return round(pago_semanal, 2)
        return Decimal('0')
    
    @property
    def pago_mensual_aproximado(self):
        """Calcula el pago mensual aproximado (para validaciones)"""
        pago_semanal = self.pago_semanal
        return round(pago_semanal * Decimal('4.33'), 2)  # 4.33 semanas por mes
    
    @property
    def semanas_restantes(self):
        """Semanas restantes para terminar de pagar"""
        if self.monto_total > 0 and self.pago_semanal > 0:
            saldo_decimal = Decimal(str(self.saldo_pendiente))
            pago_semanal_decimal = Decimal(str(self.pago_semanal))
            
            if pago_semanal_decimal > 0:
                semanas = saldo_decimal / pago_semanal_decimal
                return math.ceil(semanas)
        return 0
    
    @property
    def total_interes(self):
        """Calcula el total de intereses a pagar"""
        pago_semanal = self.pago_semanal
        if pago_semanal > 0 and self.plazo_semanas > 0:
            total_pagado = pago_semanal * Decimal(str(self.plazo_semanas))
            return round(total_pagado - Decimal(str(self.monto_total)), 2)
        return Decimal('0')
    
    @property
    def fecha_final_estimada(self):
        """Calcula la fecha final estimada del préstamo"""
        if self.fecha_primer_pago and self.plazo_semanas > 0:
            from datetime import timedelta
            return self.fecha_primer_pago + timedelta(weeks=self.plazo_semanas)
        return None
    
    @property
    def esta_moroso(self):
        """Verifica si el préstamo está en mora"""
        if self.estado == 'EN_CURSO' and self.fecha_primer_pago:
            hoy = date.today()
            
            # Buscar pagos atrasados
            pagos_atrasados = self.pagos.filter(
                estado='PENDIENTE',
                fecha_pago__lt=hoy
            ).exists()
            
            return pagos_atrasados
            
        return False
    
    def get_plazo_equivalente_meses(self, decimales=1):
        """Retorna el plazo equivalente en meses"""
        if self.plazo_semanas > 0:
            return round(self.plazo_semanas / Decimal('4.33'), decimales)
        return 0


class PagoPrestamo(models.Model):
    """
    Registro de pagos de préstamos (semanal)
    """
    ESTADO_PAGO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADO', 'Pagado'),
        ('RETRASADO', 'Retrasado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    prestamo = models.ForeignKey(Prestamo, on_delete=models.CASCADE, related_name='pagos')
    numero_pago = models.IntegerField(verbose_name="Número de pago")
    fecha_pago = models.DateField(verbose_name="Fecha de pago programada")
    fecha_pago_real = models.DateField(null=True, blank=True, verbose_name="Fecha de pago real")
    monto_programado = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto programado")
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Monto pagado")
    estado = models.CharField(max_length=20, choices=ESTADO_PAGO_CHOICES, default='PENDIENTE')
    observaciones = models.TextField(blank=True, null=True)
    comprobante = models.FileField(
        upload_to='prestamos/comprobantes/',
        null=True,
        blank=True,
        verbose_name="Comprobante de pago"
    )
    
    # Auditoría
    registrado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagos_registrados'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['numero_pago']
        verbose_name = 'Pago de Préstamo'
        verbose_name_plural = 'Pagos de Préstamos'
        unique_together = ('prestamo', 'numero_pago')
    
    def __str__(self):
        return f"Pago {self.numero_pago} - {self.prestamo.empleado.nombre_completo}: ${self.monto_pagado}"
    
    @property
    def esta_retrasado(self):
        """Verifica si el pago está retrasado"""
        if self.estado == 'PENDIENTE' and self.fecha_pago:
            hoy = date.today()
            return hoy > self.fecha_pago
        return False
    
    @property
    def dias_retraso(self):
        """Días de retraso si está retrasado"""
        if self.esta_retrasado:
            hoy = date.today()
            return (hoy - self.fecha_pago).days
        return 0

class ControlVacante(models.Model):
    """
    Modelo para gestionar el presupuesto de vacantes por empresa, puesto y división.
    """
    empresa = models.CharField(max_length=20, choices=Empleado.EMPRESA_CHOICES)
    puesto = models.ForeignKey(Puesto, on_delete=models.CASCADE, related_name='controles_vacantes')
    division = models.ForeignKey(DivisionOperativa, on_delete=models.SET_NULL, null=True, blank=True)
    cantidad_presupuestada = models.PositiveIntegerField(default=0, verbose_name="Cantidad Objetivo")
    
    class Meta:
        verbose_name = "Control de Vacante"
        verbose_name_plural = "Control de Vacantes"
        unique_together = ['empresa', 'puesto', 'division']

    def __str__(self):
        div = f" - {self.division}" if self.division else ""
        return f"{self.empresa} - {self.puesto}{div} ({self.cantidad_presupuestada})"