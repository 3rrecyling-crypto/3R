"""Serializers del chat."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Max
from rest_framework import serializers

from .models import Attachment, Conversation, EventoCalendario, Membership, Message

User = get_user_model()


class UserMiniSerializer(serializers.ModelSerializer):
    nombre = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "nombre", "email"]

    def get_nombre(self, u) -> str:
        full = f"{u.first_name or ''} {u.last_name or ''}".strip()
        return full or u.username


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "nombre_original", "mime", "tamano", "es_imagen",
                  "ancho", "alto", "url", "creado"]

    def get_url(self, a) -> str:
        try:
            return a.archivo.url
        except Exception:
            return ""


class MessageSerializer(serializers.ModelSerializer):
    sender = UserMiniSerializer(read_only=True)
    adjuntos = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ["id", "conversation", "sender", "body", "creado",
                  "editado_en", "deleted_at", "es_sistema", "adjuntos"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "es_admin", "silenciado", "unido_en",
                  "salido_en", "last_read_at"]


class ConversationSerializer(serializers.ModelSerializer):
    participantes = serializers.SerializerMethodField()
    titulo_calculado = serializers.SerializerMethodField()
    ultimo_mensaje = serializers.SerializerMethodField()
    no_leidos = serializers.SerializerMethodField()
    otro = serializers.SerializerMethodField()  # solo DIRECT

    class Meta:
        model = Conversation
        fields = ["id", "kind", "titulo", "titulo_calculado", "creado",
                  "actualizado", "ultimo_mensaje_en", "participantes",
                  "ultimo_mensaje", "no_leidos", "otro"]

    def _yo(self):
        request = self.context.get("request")
        return request.user if request else None

    def get_participantes(self, c):
        qs = c.memberships.filter(salido_en__isnull=True).select_related("user")
        return MembershipSerializer(qs, many=True).data

    def get_titulo_calculado(self, c) -> str:
        if c.kind == Conversation.GROUP:
            return c.titulo or f"Grupo #{c.pk}"
        yo = self._yo()
        otros = c.memberships.exclude(user=yo).select_related("user")[:1]
        if otros:
            u = otros[0].user
            return f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username
        return "Conversación"

    def get_ultimo_mensaje(self, c):
        m = c.mensajes.order_by("-creado").first()
        if not m:
            return None
        return MessageSerializer(m).data

    def get_no_leidos(self, c) -> int:
        yo = self._yo()
        if not yo:
            return 0
        member = c.memberships.filter(user=yo).first()
        if not member:
            return 0
        return c.mensajes.filter(creado__gt=member.last_read_at).exclude(sender=yo).count()

    def get_otro(self, c):
        if c.kind != Conversation.DIRECT:
            return None
        yo = self._yo()
        otros = c.memberships.exclude(user=yo).select_related("user")
        if otros:
            return UserMiniSerializer(otros[0].user).data
        return None


class CrearDirectSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()


class CrearGrupoSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=120)
    user_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class EventoCalendarioSerializer(serializers.ModelSerializer):
    """Evento del calendario (reunión/videollamada o tarea)."""
    creado_por = UserMiniSerializer(read_only=True)
    participantes = UserMiniSerializer(many=True, read_only=True)
    participantes_ids = serializers.PrimaryKeyRelatedField(
        source="participantes", many=True, write_only=True, required=False,
        queryset=User.objects.all(),
    )
    conversation_id = serializers.PrimaryKeyRelatedField(
        source="conversation", write_only=True, required=False, allow_null=True,
        queryset=Conversation.objects.all(),
    )
    puede_editar = serializers.SerializerMethodField()

    class Meta:
        model = EventoCalendario
        fields = [
            "id", "tipo", "titulo", "descripcion", "inicio", "fin", "todo_el_dia",
            "color", "estado", "creado_por", "participantes", "participantes_ids",
            "conversation", "conversation_id", "puede_editar", "creado",
            "canal_recordatorio", "recordatorio_destino",
        ]
        read_only_fields = ["creado_por", "creado", "conversation"]

    def get_puede_editar(self, o) -> bool:
        req = self.context.get("request")
        return bool(req and o.creado_por_id == req.user.id)
