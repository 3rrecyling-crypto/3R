"""Modelos del chat interno.

Diseño:
- Conversation: caja común. `kind=DIRECT` (1-a-1) o `kind=GROUP` (n participantes).
- Membership: relación M2M con metadata (last_read_at para no leídos, rol admin).
- Message: texto (puede estar vacío si solo es adjunto). Soft-delete con `deleted_at`.
- Attachment: archivo subido por mensaje. Multiple por mensaje (drag de varios).
"""
from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def attachment_upload_to(instance: "Attachment", filename: str) -> str:
    """Path: chat/<conv_id>/<uuid>__<original-name>"""
    base, ext = os.path.splitext(filename)
    safe = uuid.uuid4().hex
    return f"chat/{instance.message.conversation_id}/{safe}__{filename}"[:240]


class Conversation(models.Model):
    DIRECT = "DIRECT"
    GROUP = "GROUP"
    KIND_CHOICES = [(DIRECT, "Directa 1-a-1"), (GROUP, "Grupo")]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=DIRECT)
    titulo = models.CharField(max_length=120, blank=True)  # solo grupos
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="chat_conversaciones_creadas",
    )
    # Cache: timestamp del último mensaje, para ordenar la lista en O(1).
    ultimo_mensaje_en = models.DateTimeField(default=timezone.now, db_index=True)
    # Conversación especial "🔔 Recordatorios" (una por usuario) donde el sistema
    # publica avisos de eventos del calendario. No se crea manualmente.
    es_recordatorios = models.BooleanField(default=False)

    class Meta:
        ordering = ["-ultimo_mensaje_en"]

    def __str__(self) -> str:
        if self.kind == self.GROUP:
            return self.titulo or f"Grupo #{self.pk}"
        return f"Conversación #{self.pk}"


class Membership(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_membresias",
    )
    es_admin = models.BooleanField(default=False)  # solo grupos
    silenciado = models.BooleanField(default=False)
    unido_en = models.DateTimeField(auto_now_add=True)
    salido_en = models.DateTimeField(null=True, blank=True)
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"], name="chat_membership_uniq",
            ),
        ]
        indexes = [models.Index(fields=["user", "salido_en"])]

    @property
    def activo(self) -> bool:
        return self.salido_en is None


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="mensajes",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="chat_mensajes_enviados",
    )
    body = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True, db_index=True)
    editado_en = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    # Mensaje "del sistema" (ej. 'X se unió al grupo'). Sender puede ser None.
    es_sistema = models.BooleanField(default=False)

    class Meta:
        ordering = ["creado"]
        indexes = [models.Index(fields=["conversation", "creado"])]


class Attachment(models.Model):
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="adjuntos",
    )
    archivo = models.FileField(upload_to=attachment_upload_to)
    nombre_original = models.CharField(max_length=255)
    mime = models.CharField(max_length=120, blank=True)
    tamano = models.PositiveBigIntegerField(default=0)
    es_imagen = models.BooleanField(default=False)
    ancho = models.PositiveIntegerField(null=True, blank=True)
    alto = models.PositiveIntegerField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)


class InvitacionVideollamada(models.Model):
    """Invitación para que alguien EXTERNO (sin cuenta) entre a la videollamada
    de una conversación mediante un link público `/reunion/<token>`.

    El token es un UUID impredecible. La invitación puede expirar y revocarse.
    El invitado solo obtiene un token de LiveKit para ESA sala, con permisos
    limitados (no admin)."""
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="invitaciones_video",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="video_invitaciones_creadas",
    )
    creado = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField(null=True, blank=True)  # None = no expira
    revocado = models.BooleanField(default=False)
    usos = models.PositiveIntegerField(default=0)  # cuántas veces se unió alguien

    class Meta:
        ordering = ["-creado"]
        indexes = [models.Index(fields=["conversation", "revocado"])]

    def vigente(self) -> bool:
        if self.revocado:
            return False
        if self.expira_en and self.expira_en < timezone.now():
            return False
        return True

    def __str__(self) -> str:
        return f"Invitación {self.token} → conv #{self.conversation_id}"


class GrabacionVideollamada(models.Model):
    """Registro de una grabación (Egress → S3) de la videollamada de una
    conversación. El archivo (key en el bucket) se genera al iniciar; el MP4
    aparece en S3 unos segundos después de detener."""
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="grabaciones",
    )
    archivo = models.CharField(max_length=300)  # key dentro del bucket S3
    egress_id = models.CharField(max_length=80, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="video_grabaciones",
    )
    creado = models.DateTimeField(auto_now_add=True)
    detenida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado"]
        indexes = [models.Index(fields=["conversation", "creado"])]

    def __str__(self) -> str:
        return f"Grabación conv #{self.conversation_id} · {self.archivo}"


class EventoCalendario(models.Model):
    """Evento del calendario del chat: una REUNIÓN (videollamada programada a una
    hora) o una TAREA asignada. Los `participantes` son quienes lo ven en su
    calendario y, en una reunión, los invitados a la videollamada (vía la
    `conversation` ligada)."""

    TIPO = [("REUNION", "Reunión / Videollamada"), ("TAREA", "Tarea")]
    ESTADO = [
        ("PENDIENTE", "Pendiente"), ("EN_PROGRESO", "En progreso"),
        ("COMPLETADA", "Completada"), ("CANCELADA", "Cancelada"),
    ]

    tipo = models.CharField(max_length=10, choices=TIPO, default="REUNION")
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField(null=True, blank=True)
    todo_el_dia = models.BooleanField(default=False)
    color = models.CharField(max_length=9, blank=True)  # hex opcional
    estado = models.CharField(max_length=12, choices=ESTADO, default="PENDIENTE")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="eventos_calendario_creados",
    )
    participantes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="eventos_calendario", blank=True,
    )
    # Reunión: conversación (grupo) para lanzar la videollamada a la hora.
    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="eventos",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    # Recordatorio externo (correo / WhatsApp vía Twilio) además del aviso en chat.
    CANAL_CHOICES = [("CHAT", "Solo chat"), ("CORREO", "Correo"), ("WHATSAPP", "WhatsApp")]
    canal_recordatorio = models.CharField(max_length=10, choices=CANAL_CHOICES, default="CHAT")
    recordatorio_destino = models.CharField(
        max_length=120, blank=True, help_text="Correo o teléfono (WhatsApp) según el canal",
    )
    recordatorio_ext_dia_antes = models.BooleanField(default=False)
    recordatorio_ext_dia = models.BooleanField(default=False)

    class Meta:
        ordering = ["inicio"]
        indexes = [models.Index(fields=["inicio"])]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()}: {self.titulo}"


class RecordatorioEvento(models.Model):
    """Marca que ya se envió un recordatorio de `evento` a `user` para un hito
    (`DIA_ANTES` = un día antes, `DIA` = el mismo día). Evita duplicar avisos."""
    DIA_ANTES = "DIA_ANTES"
    DIA = "DIA"
    TIPO = [(DIA_ANTES, "Un día antes"), (DIA, "El mismo día")]

    evento = models.ForeignKey(
        EventoCalendario, on_delete=models.CASCADE, related_name="recordatorios",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="recordatorios_evento",
    )
    tipo = models.CharField(max_length=10, choices=TIPO)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evento", "user", "tipo"], name="recordatorio_evento_uniq",
            ),
        ]
