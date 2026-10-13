# tickets/models.py
# Mesa de ayuda: cualquier usuario levanta solicitudes de mejora, reportes de
# falla, peticiones o dudas; el equipo que atiende les da seguimiento.
import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import get_valid_filename


class Ticket(models.Model):
    class Tipo(models.TextChoices):
        MEJORA = 'MEJORA', 'Solicitud de mejora'
        FALLA = 'FALLA', 'Reporte de falla'
        PETICION = 'PETICION', 'Petición'
        SOPORTE = 'SOPORTE', 'Duda o soporte'
        OTRO = 'OTRO', 'Otro'

    class Prioridad(models.TextChoices):
        BAJA = 'BAJA', 'Baja'
        MEDIA = 'MEDIA', 'Media'
        ALTA = 'ALTA', 'Alta'
        CRITICA = 'CRITICA', 'Crítica'

    class Estado(models.TextChoices):
        RECIBIDO = 'RECIBIDO', 'Recibido'
        EN_REVISION = 'EN_REVISION', 'En revisión'
        EN_PROCESO = 'EN_PROCESO', 'En proceso'
        EN_ESPERA = 'EN_ESPERA', 'En espera de información'
        RESUELTO = 'RESUELTO', 'Resuelto, por confirmar'
        CERRADO = 'CERRADO', 'Cerrado'
        RECHAZADO = 'RECHAZADO', 'Rechazado'
        CANCELADO = 'CANCELADO', 'Cancelado por el solicitante'

    class Modulo(models.TextChoices):
        REMISIONES = 'REMISIONES', 'Remisiones'
        REPORTES = 'REPORTES', 'Reportes y Excel'
        CATALOGOS = 'CATALOGOS', 'Catálogos'
        DIESEL = 'DIESEL', 'Control Diésel'
        VIAJES = 'VIAJES', 'Viajes y liquidaciones'
        TRANE = 'TRANE', 'Portal Trane'
        BANCOS = 'BANCOS', 'Bancos y flujos'
        RH = 'RH', 'Recursos Humanos'
        HERRAMIENTAS = 'HERRAMIENTAS', 'Herramientas y diseño'
        CHAT = 'CHAT', 'Mensajes y videollamadas'
        ACCESO = 'ACCESO', 'Acceso, usuarios y permisos'
        GENERAL = 'GENERAL', 'General / otro'

    # Ciclo: soporte atiende (EN ATENCIÓN) → lo marca RESUELTO → el solicitante lo
    # confirma y lo CIERRA (o lo reabre). Solo el solicitante cierra o cancela.
    ESTADOS_EN_ATENCION = (Estado.RECIBIDO, Estado.EN_REVISION, Estado.EN_PROCESO, Estado.EN_ESPERA)
    ESTADOS_FINALES = (Estado.CERRADO, Estado.RECHAZADO, Estado.CANCELADO)
    # Estados que soporte puede poner (cerrar y cancelar le tocan al solicitante).
    ESTADOS_SOPORTE = ESTADOS_EN_ATENCION + (Estado.RESUELTO, Estado.RECHAZADO)

    folio = models.CharField(max_length=20, unique=True, null=True, blank=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.MEJORA)
    modulo = models.CharField(max_length=15, choices=Modulo.choices, default=Modulo.GENERAL,
                              verbose_name='Módulo del sistema')
    prioridad = models.CharField(max_length=10, choices=Prioridad.choices, default=Prioridad.MEDIA)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.RECIBIDO)
    titulo = models.CharField(max_length=150, verbose_name='Asunto')
    descripcion = models.TextField(verbose_name='Descripción')

    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    related_name='tickets_solicitados')
    asignado_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='tickets_asignados', verbose_name='Responsable')

    fecha_recepcion = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de recepción')
    fecha_seguimiento = models.DateField(null=True, blank=True, verbose_name='Fecha de seguimiento',
                                         help_text='Fecha comprometida para la siguiente revisión o respuesta.')
    fecha_resolucion = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de resolución',
                                            help_text='Cuando soporte lo marcó como resuelto.')
    fecha_cierre = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de cierre',
                                        help_text='Cuando el solicitante lo cerró (o se rechazó/canceló).')
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ticket'
        verbose_name_plural = 'Tickets'
        ordering = ['-fecha_recepcion']
        permissions = [
            ('atender_tickets', 'Puede atender tickets (ver todos, asignar, cambiar estado y seguimiento)'),
        ]

    def __str__(self):
        return f'{self.folio or "TCK"} · {self.titulo}'

    @property
    def abierto(self):
        """Sigue abierto hasta que el solicitante lo cierra (incluye "resuelto, por confirmar")."""
        return self.estado not in self.ESTADOS_FINALES

    @property
    def en_atencion(self):
        return self.estado in self.ESTADOS_EN_ATENCION

    def _dias_hasta(self, fin):
        if not self.fecha_recepcion:
            return 0
        return (timezone.localdate(fin or timezone.now()) - timezone.localdate(self.fecha_recepcion)).days

    @property
    def dias_transcurridos(self):
        """Días naturales desde la recepción hasta hoy (o hasta el cierre, si ya cerró)."""
        return self._dias_hasta(self.fecha_cierre)

    @property
    def dias_resolucion(self):
        """Días que tardó soporte en resolverlo (None si aún no se resuelve)."""
        return self._dias_hasta(self.fecha_resolucion) if self.fecha_resolucion else None

    @property
    def seguimiento_vencido(self):
        return bool(self.en_atencion and self.fecha_seguimiento and self.fecha_seguimiento < timezone.localdate())

    def asignar_folio(self):
        if not self.folio and self.pk:
            self.folio = f'TCK-{self.pk:05d}'
            Ticket.objects.filter(pk=self.pk).update(folio=self.folio)


class TicketComentario(models.Model):
    class Tipo(models.TextChoices):
        COMENTARIO = 'COMENTARIO', 'Comentario'
        SISTEMA = 'SISTEMA', 'Movimiento del sistema'

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.COMENTARIO)
    mensaje = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Comentario de ticket'
        verbose_name_plural = 'Comentarios de ticket'
        ordering = ['creado_en', 'pk']

    def __str__(self):
        return f'{self.ticket} · {self.get_tipo_display()}'


def _ruta_archivo_ticket(instance, filename):
    # Prefijo aleatorio: en S3 un nombre repetido sobrescribiría el archivo anterior.
    nombre = get_valid_filename(os.path.basename(filename)) or 'archivo'
    return f'tickets/{instance.ticket_id}/{uuid.uuid4().hex[:8]}_{nombre}'


class TicketArchivo(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='archivos')
    comentario = models.ForeignKey(TicketComentario, on_delete=models.CASCADE, null=True, blank=True,
                                   related_name='archivos')
    archivo = models.FileField(upload_to=_ruta_archivo_ticket, max_length=255)
    nombre = models.CharField(max_length=255)
    tamano = models.PositiveIntegerField(default=0, verbose_name='Tamaño (bytes)')
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Archivo de ticket'
        verbose_name_plural = 'Archivos de ticket'
        ordering = ['subido_en', 'pk']

    def __str__(self):
        return self.nombre
