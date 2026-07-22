"""Vistas REST del chat.

Endpoints principales:
- GET    /api/chat/conversaciones/                       lista del usuario
- POST   /api/chat/conversaciones/direct/                crea (o reusa) 1-a-1
- POST   /api/chat/conversaciones/grupo/                 crea grupo
- GET    /api/chat/conversaciones/{id}/mensajes/         historial paginado
- POST   /api/chat/conversaciones/{id}/mensajes/         envía texto + adjuntos (multipart)
- POST   /api/chat/conversaciones/{id}/leer/             marca como leído hasta ahora
- GET    /api/chat/no-leidos/                            total de mensajes sin leer
- GET    /api/chat/usuarios/?q=…                         busca usuarios para iniciar chat
- POST   /api/chat/conversaciones/{id}/videollamada/     token LiveKit para la sala
"""
from __future__ import annotations

import mimetypes
import uuid
from datetime import timedelta
from io import BytesIO

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    Attachment, Conversation, EventoCalendario, GrabacionVideollamada,
    InvitacionVideollamada, Membership, Message, RecordatorioEvento,
)
from .serializers import (
    ConversationSerializer, CrearDirectSerializer, CrearGrupoSerializer,
    EventoCalendarioSerializer, MessageSerializer, UserMiniSerializer,
)

User = get_user_model()
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB por adjunto


def _es_imagen(mime: str) -> bool:
    return bool(mime) and mime.startswith("image/")


def _dimensiones(fh) -> tuple[int | None, int | None]:
    try:
        from PIL import Image  # Pillow
        fh.seek(0)
        data = fh.read()
        fh.seek(0)
        img = Image.open(BytesIO(data))
        return img.width, img.height
    except Exception:
        return None, None


def _broadcast(conversation: Conversation, payload: dict) -> None:
    """Publica un evento WS a todos los miembros activos. Best-effort: si el
    channel layer no está disponible (p. ej. Redis apagado), NO rompe la petición
    — el mensaje ya quedó guardado y el front se actualiza por polling."""
    layer = get_channel_layer()
    if not layer:
        return
    try:
        user_ids = list(conversation.memberships.filter(salido_en__isnull=True)
                        .values_list("user_id", flat=True))
        for m in user_ids:
            async_to_sync(layer.group_send)(
                f"chat_user_{m}",
                {"type": "chat.event", "payload": payload},
            )
    except Exception:
        # Redis/channel layer caído: degradamos a polling, sin romper el request.
        pass


class MensajesPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


class ConversationViewSet(viewsets.GenericViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return (Conversation.objects
                .filter(memberships__user=self.request.user,
                        memberships__salido_en__isnull=True)
                .distinct()
                .order_by("-ultimo_mensaje_en"))

    def list(self, request):
        qs = self.get_queryset()
        ser = self.get_serializer(qs, many=True)
        return Response({"results": ser.data, "count": qs.count()})

    def retrieve(self, request, pk=None):
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(self.get_serializer(conv).data)

    @action(detail=False, methods=["post"], url_path="direct")
    def crear_direct(self, request):
        ser = CrearDirectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        otro_id = ser.validated_data["user_id"]
        if otro_id == request.user.id:
            return Response({"detail": "No puedes abrir un chat contigo mismo."}, status=400)
        otro = get_object_or_404(User, pk=otro_id, is_active=True)

        # Reusar una conversación directa ya existente entre los dos.
        existente = (Conversation.objects
                     .filter(kind=Conversation.DIRECT,
                             memberships__user=request.user)
                     .filter(memberships__user=otro)
                     .distinct()
                     .first())
        if existente:
            # Si alguno de los dos había salido (soft-left) de esta conversación
            # directa, reactívalo: si no, no la vería en su lista pese a "reabrirla".
            existente.memberships.filter(
                user__in=[request.user, otro], salido_en__isnull=False,
            ).update(salido_en=None)
            return Response(self.get_serializer(existente).data)

        with transaction.atomic():
            conv = Conversation.objects.create(
                kind=Conversation.DIRECT, creado_por=request.user,
            )
            Membership.objects.bulk_create([
                Membership(conversation=conv, user=request.user),
                Membership(conversation=conv, user=otro),
            ])
        return Response(self.get_serializer(conv).data, status=201)

    @action(detail=False, methods=["post"], url_path="grupo")
    def crear_grupo(self, request):
        ser = CrearGrupoSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user_ids = set(ser.validated_data["user_ids"]) - {request.user.id}
        if not user_ids:
            return Response({"detail": "Agrega al menos un participante."}, status=400)
        otros = list(User.objects.filter(pk__in=user_ids, is_active=True))
        if not otros:
            return Response({"detail": "No se encontraron usuarios válidos."}, status=400)
        with transaction.atomic():
            conv = Conversation.objects.create(
                kind=Conversation.GROUP,
                titulo=ser.validated_data["titulo"],
                creado_por=request.user,
            )
            miembros = [Membership(conversation=conv, user=request.user, es_admin=True)]
            miembros += [Membership(conversation=conv, user=u) for u in otros]
            Membership.objects.bulk_create(miembros)
            # Mensaje del sistema "creó el grupo".
            Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"creó el grupo «{conv.titulo}»",
                es_sistema=True,
            )
            conv.ultimo_mensaje_en = timezone.now()
            conv.save(update_fields=["ultimo_mensaje_en"])
        return Response(self.get_serializer(conv).data, status=201)

    @action(detail=False, methods=["post"], url_path="reunion-rapida")
    def reunion_rapida(self, request):
        """Reunión INSTANTÁNEA: crea una conversación de grupo con SOLO el creador
        y devuelve el token LiveKit para entrar de inmediato. No hace falta tener
        un chat previo con nadie; ya dentro de la sala se invita a otros con el
        botón «Invitar» (link público /reunion/<token>)."""
        from . import livekit_utils as lk

        if not lk.livekit_configurado():
            return Response(
                {"detail": "Videollamadas no configuradas: falta LIVEKIT_URL / "
                           "LIVEKIT_API_KEY / LIVEKIT_API_SECRET en el backend."},
                status=503,
            )

        user = request.user
        nombre = (user.get_full_name() or "").strip() or user.username
        titulo = (request.data.get("titulo") or "").strip()[:120] or f"Reunión de {nombre}"

        with transaction.atomic():
            conv = Conversation.objects.create(
                kind=Conversation.GROUP, titulo=titulo, creado_por=user,
            )
            Membership.objects.create(conversation=conv, user=user, es_admin=True)
            Message.objects.create(
                conversation=conv, sender=user, es_sistema=True,
                body="📹 inició una reunión instantánea",
            )
            conv.ultimo_mensaje_en = timezone.now()
            conv.save(update_fields=["ultimo_mensaje_en"])

        room = lk.room_name(conv.id)
        lk.crear_sala(room, creador_nombre=nombre, creador_id=user.id)
        token = lk.crear_access_token(
            room=room, identity=f"user_{user.id}", nombre=nombre, admin=True,
        )
        return Response({
            "conv_id": conv.id,
            "titulo": titulo,
            "url": lk.server_url(),
            "token": token,
            "room": room,
        }, status=201)

    @action(detail=True, methods=["get", "post"], url_path="mensajes")
    def mensajes(self, request, pk=None):
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        if request.method == "GET":
            qs = conv.mensajes.select_related("sender").prefetch_related("adjuntos").order_by("-creado")
            page = MensajesPagination()
            ms = page.paginate_queryset(qs, request)
            ser = MessageSerializer(ms, many=True)
            return page.get_paginated_response(ser.data)

        body = (request.data.get("body") or "").strip()
        files = request.FILES.getlist("adjuntos") if hasattr(request, "FILES") else []
        if not body and not files:
            return Response({"detail": "Mensaje vacío."}, status=400)

        for f in files:
            if f.size > MAX_FILE_BYTES:
                return Response(
                    {"detail": f"El archivo «{f.name}» supera el límite de 20 MB."},
                    status=400,
                )

        with transaction.atomic():
            msg = Message.objects.create(
                conversation=conv, sender=request.user, body=body,
            )
            for f in files:
                mime = f.content_type or mimetypes.guess_type(f.name)[0] or ""
                es_img = _es_imagen(mime)
                w, h = _dimensiones(f) if es_img else (None, None)
                Attachment.objects.create(
                    message=msg,
                    archivo=f,
                    nombre_original=f.name[:255],
                    mime=mime[:120],
                    tamano=f.size or 0,
                    es_imagen=es_img,
                    ancho=w,
                    alto=h,
                )
            conv.ultimo_mensaje_en = msg.creado
            conv.save(update_fields=["ultimo_mensaje_en", "actualizado"])
            # El propio sender ya leyó su mensaje.
            Membership.objects.filter(conversation=conv, user=request.user) \
                .update(last_read_at=msg.creado)

        data = MessageSerializer(msg).data
        _broadcast(conv, {
            "type": "message.new",
            "conversation_id": conv.id,
            "message": data,
        })
        return Response(data, status=201)

    @action(detail=True, methods=["post"], url_path="leer")
    def marcar_leido(self, request, pk=None):
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        Membership.objects.filter(conversation=conv, user=request.user) \
            .update(last_read_at=timezone.now())
        _broadcast(conv, {
            "type": "conversation.read",
            "conversation_id": conv.id,
            "user_id": request.user.id,
        })
        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="videollamada")
    def videollamada(self, request, pk=None):
        """Devuelve un token LiveKit para unirse a la videollamada de la conversación.

        La sala es determinística (`conv_<id>`), así que todos los miembros que
        pulsen "videollamada" caen en la MISMA sala. Si nadie estaba en llamada
        (heurística: ningún inicio en los últimos minutos), además publica un
        evento `call.started` a los miembros (banner "unirse") y deja un mensaje
        de sistema en el hilo.
        """
        from . import livekit_utils as lk

        conv = get_object_or_404(self.get_queryset(), pk=pk)
        if not lk.livekit_configurado():
            return Response(
                {"detail": "Videollamadas no configuradas: falta LIVEKIT_URL / "
                           "LIVEKIT_API_KEY / LIVEKIT_API_SECRET en el backend."},
                status=503,
            )

        user = request.user
        nombre = (user.get_full_name() or "").strip() or user.username
        room = lk.room_name(conv.id)
        token = lk.crear_access_token(
            room=room, identity=f"user_{user.id}", nombre=nombre, admin=True,
        )

        # ¿Esta petición "inicia" la llamada? Si nadie la marcó en los últimos
        # minutos, cuenta como inicio → mensaje de sistema + banner. Al reentrar
        # (o al unirse otro miembro enseguida) no vuelve a spamear.
        hace_poco = timezone.now() - timedelta(minutes=3)
        recien_iniciada = conv.mensajes.filter(
            es_sistema=True, body__startswith="📹", creado__gte=hace_poco,
        ).exists()
        if not recien_iniciada:
            # Marca la sala con el creador para el aviso "creada por …" (best-effort).
            lk.crear_sala(room, creador_nombre=nombre, creador_id=user.id)
            msg = Message.objects.create(
                conversation=conv, sender=user, es_sistema=True,
                body="📹 inició una videollamada",
            )
            conv.ultimo_mensaje_en = msg.creado
            conv.save(update_fields=["ultimo_mensaje_en"])
            data = MessageSerializer(msg).data
            _broadcast(conv, {
                "type": "message.new", "conversation_id": conv.id, "message": data,
            })
            _broadcast(conv, {
                "type": "call.started",
                "conversation_id": conv.id,
                "room": room,
                "by": {"id": user.id, "nombre": nombre},
            })

        return Response({"url": lk.server_url(), "token": token, "room": room})

    @action(detail=True, methods=["post"], url_path="videollamada/finalizar")
    def videollamada_finalizar(self, request, pk=None):
        """Termina la videollamada para TODOS (borra la sala en LiveKit → expulsa
        a todos). Cualquier miembro de la conversación puede hacerlo. Útil cuando
        alguien dejó una pestaña abierta y la llamada quedó "colgada"."""
        from . import livekit_utils as lk

        conv = get_object_or_404(self.get_queryset(), pk=pk)
        room = lk.room_name(conv.id)
        ok = lk.eliminar_sala(room)

        # Mensaje de sistema + aviso a los miembros para que el banner desaparezca.
        nombre = (request.user.get_full_name() or "").strip() or request.user.username
        msg = Message.objects.create(
            conversation=conv, sender=request.user, es_sistema=True,
            body="📴 finalizó la videollamada",
        )
        conv.ultimo_mensaje_en = msg.creado
        conv.save(update_fields=["ultimo_mensaje_en"])
        data = MessageSerializer(msg).data
        _broadcast(conv, {"type": "message.new", "conversation_id": conv.id, "message": data})
        _broadcast(conv, {
            "type": "call.ended", "conversation_id": conv.id,
            "by": {"id": request.user.id, "nombre": nombre},
        })
        return Response({"ok": ok})

    @action(detail=True, methods=["post"], url_path="invitar-externo")
    def invitar_externo(self, request, pk=None):
        """Crea un link público para que alguien EXTERNO (sin cuenta) entre a la
        videollamada de esta conversación. Devuelve el token y el link.

        Body opcional: `expira_horas` (int). Por defecto la invitación dura 7 días.
        """
        from . import livekit_utils as lk

        conv = get_object_or_404(self.get_queryset(), pk=pk)
        if not lk.livekit_configurado():
            return Response(
                {"detail": "Videollamadas no configuradas: falta LIVEKIT_URL / "
                           "LIVEKIT_API_KEY / LIVEKIT_API_SECRET en el backend."},
                status=503,
            )

        expira_en = timezone.now() + timedelta(days=1)
        horas = request.data.get("expira_horas")
        if horas is not None:
            try:
                h = int(horas)
                expira_en = timezone.now() + timedelta(hours=h) if h > 0 else None
            except (TypeError, ValueError):
                pass

        inv = InvitacionVideollamada.objects.create(
            conversation=conv, creado_por=request.user, expira_en=expira_en,
        )
        # El link definitivo lo arma el front con su propio origin; aquí damos
        # una versión con FRONTEND_URL/Origin como respaldo.
        base = (request.headers.get("Origin") or getattr(dj_settings, "FRONTEND_URL", "") or "").rstrip("/")
        return Response({
            "token": str(inv.token),
            "path": f"/reunion/{inv.token}",
            "link": f"{base}/reunion/{inv.token}" if base else f"/reunion/{inv.token}",
            "expira_en": inv.expira_en,
        }, status=201)

    @action(detail=True, methods=["get"], url_path="invitaciones")
    def invitaciones(self, request, pk=None):
        """Lista las invitaciones externas VIGENTES de la conversación."""
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        ahora = timezone.now()
        qs = (conv.invitaciones_video
              .filter(revocado=False)
              .filter(Q(expira_en__isnull=True) | Q(expira_en__gt=ahora))
              .order_by("-creado"))
        out = [{
            "token": str(i.token),
            "path": f"/reunion/{i.token}",
            "expira_en": i.expira_en,
            "usos": i.usos,
            "creado": i.creado,
        } for i in qs]
        return Response({"invitaciones": out})

    @action(detail=True, methods=["post"], url_path="videollamada/grabar")
    def videollamada_grabar(self, request, pk=None):
        """Inicia la grabación de la videollamada (Egress → S3)."""
        from . import livekit_utils as lk

        conv = get_object_or_404(self.get_queryset(), pk=pk)
        if not lk.grabacion_disponible():
            return Response(
                {"detail": "Grabación no disponible: requiere Egress habilitado en "
                           "LiveKit y un bucket S3 configurado (AWS_STORAGE_BUCKET_NAME)."},
                status=503,
            )
        room = lk.room_name(conv.id)
        # Nombre de archivo con fecha (sin Date.now/random del entorno de scripts).
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        filepath = f"grabaciones/{room}_{ts}.mp4"
        egress_id = lk.iniciar_grabacion(room, filepath)
        if not egress_id:
            return Response({"detail": "No se pudo iniciar la grabación (¿Egress habilitado?)."}, status=502)

        GrabacionVideollamada.objects.create(
            conversation=conv, archivo=filepath, egress_id=egress_id, creado_por=request.user,
        )
        nombre = (request.user.get_full_name() or "").strip() or request.user.username
        msg = Message.objects.create(
            conversation=conv, sender=request.user, es_sistema=True,
            body="🔴 inició la grabación de la videollamada",
        )
        conv.ultimo_mensaje_en = msg.creado
        conv.save(update_fields=["ultimo_mensaje_en"])
        _broadcast(conv, {"type": "message.new", "conversation_id": conv.id,
                          "message": MessageSerializer(msg).data})
        return Response({"grabando": True, "egress_id": egress_id, "archivo": filepath})

    @action(detail=True, methods=["post"], url_path="videollamada/grabar/detener")
    def videollamada_grabar_detener(self, request, pk=None):
        """Detiene la grabación activa. El MP4 queda en el bucket S3."""
        from . import livekit_utils as lk

        conv = get_object_or_404(self.get_queryset(), pk=pk)
        room = lk.room_name(conv.id)
        n = lk.detener_grabacion(room)
        conv.grabaciones.filter(detenida_en__isnull=True).update(detenida_en=timezone.now())
        if n:
            msg = Message.objects.create(
                conversation=conv, sender=request.user, es_sistema=True,
                body="⏹️ detuvo la grabación (el archivo quedó guardado)",
            )
            conv.ultimo_mensaje_en = msg.creado
            conv.save(update_fields=["ultimo_mensaje_en"])
            _broadcast(conv, {"type": "message.new", "conversation_id": conv.id,
                              "message": MessageSerializer(msg).data})
        return Response({"grabando": False, "detenidas": n})

    @action(detail=True, methods=["get"], url_path="videollamada/grabacion")
    def videollamada_grabacion_estado(self, request, pk=None):
        """¿Se está grabando ahora mismo? (para el estado del botón)."""
        from . import livekit_utils as lk
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        return Response({
            "disponible": lk.grabacion_disponible(),
            "grabando": lk.esta_grabando(lk.room_name(conv.id)) if lk.grabacion_disponible() else False,
        })

    @action(detail=True, methods=["get"], url_path="grabaciones")
    def grabaciones(self, request, pk=None):
        """Lista las grabaciones de la conversación con link temporal de descarga."""
        from . import livekit_utils as lk
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        out = []
        for g in conv.grabaciones.select_related("creado_por").all()[:100]:
            autor = ""
            if g.creado_por:
                autor = (g.creado_por.get_full_name() or "").strip() or g.creado_por.username
            out.append({
                "id": g.id,
                "creado": g.creado,
                "detenida_en": g.detenida_en,
                "por": autor,
                "archivo": g.archivo,
                "url": lk.presigned_url(g.archivo),  # None si S3 no está configurado
                "en_curso": g.detenida_en is None,
            })
        return Response({"grabaciones": out})

    @action(detail=True, methods=["post"], url_path="agregar")
    def agregar_miembros(self, request, pk=None):
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        if conv.kind != Conversation.GROUP:
            return Response({"detail": "Sólo en grupos."}, status=400)
        ids = request.data.get("user_ids") or []
        nuevos = User.objects.filter(pk__in=ids, is_active=True)
        with transaction.atomic():
            for u in nuevos:
                Membership.objects.get_or_create(
                    conversation=conv, user=u, defaults={"salido_en": None},
                )
            Message.objects.create(
                conversation=conv, sender=request.user, es_sistema=True,
                body=f"agregó a {', '.join(u.username for u in nuevos)}",
            )
            conv.ultimo_mensaje_en = timezone.now()
            conv.save(update_fields=["ultimo_mensaje_en"])
        return Response(self.get_serializer(conv).data)

    @action(detail=True, methods=["post"], url_path="salir")
    def salir(self, request, pk=None):
        conv = get_object_or_404(self.get_queryset(), pk=pk)
        Membership.objects.filter(conversation=conv, user=request.user) \
            .update(salido_en=timezone.now())
        Message.objects.create(
            conversation=conv, sender=request.user, es_sistema=True,
            body="salió de la conversación",
        )
        conv.ultimo_mensaje_en = timezone.now()
        conv.save(update_fields=["ultimo_mensaje_en"])
        return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def no_leidos(request):
    """Total de mensajes sin leer + desglose por conversación."""
    # Un solo query con agregado condicional en vez de un .count() por conversación
    # (antes era N+1: una query extra por cada membresía del usuario).
    miembros = (Membership.objects
                .filter(user=request.user, salido_en__isnull=True)
                .annotate(_no_leidos=Count(
                    "conversation__mensajes",
                    filter=Q(conversation__mensajes__creado__gt=F("last_read_at"))
                    & ~Q(conversation__mensajes__sender=request.user),
                )))
    total = 0
    por_conv = {}
    for m in miembros:
        if m._no_leidos:
            por_conv[m.conversation_id] = m._no_leidos
            total += m._no_leidos
    return Response({"total": total, "por_conversacion": por_conv})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def usuarios(request):
    """Busca usuarios para iniciar chat. Excluye al propio usuario y a inactivos."""
    q = (request.GET.get("q") or "").strip()
    qs = User.objects.filter(is_active=True).exclude(pk=request.user.id)
    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q)
            | Q(last_name__icontains=q) | Q(email__icontains=q),
        )
    qs = qs.order_by("first_name", "username")[:25]
    return Response({"results": UserMiniSerializer(qs, many=True).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def videollamadas_activas(request):
    """Videollamadas EN CURSO en las conversaciones del usuario.

    Pregunta a LiveKit qué salas `conv_*` tienen participantes ahora mismo y las
    cruza con las conversaciones del usuario. Respuesta:

        {"activas": {"<conv_id>": {creador_nombre, iniciada_en, num_participants}}}

    El front la sondea cada pocos segundos (y al recibir `call.started`) para
    pintar el aviso "Unirse a videollamada · creada por … · ⏱ tiempo · N".
    """
    from . import livekit_utils as lk

    activas = lk.salas_activas()
    if not activas:
        return Response({"activas": {}})
    mis_convs = set(
        Membership.objects
        .filter(user=request.user, salido_en__isnull=True)
        .values_list("conversation_id", flat=True)
    )
    out = {str(cid): data for cid, data in activas.items() if cid in mis_convs}
    return Response({"activas": out})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revocar_invitacion(request, token):
    """Revoca una invitación externa. Solo un miembro de la conversación puede."""
    inv = (InvitacionVideollamada.objects
           .select_related("conversation").filter(token=token).first())
    if not inv:
        return Response({"detail": "Invitación no encontrada."}, status=404)
    es_miembro = Membership.objects.filter(
        conversation=inv.conversation, user=request.user, salido_en__isnull=True,
    ).exists()
    if not es_miembro:
        return Response({"detail": "No puedes revocar esta invitación."}, status=403)
    inv.revocado = True
    inv.save(update_fields=["revocado"])
    return Response({"ok": True})


# ── Endpoints PÚBLICOS para invitados externos (sin cuenta) ─────────────────
# El token es un UUID impredecible; la ruta usa el conversor <uuid:token>, así
# que un link inválido da 404 automático. Se valida vigencia (no revocada / no
# expirada) antes de entregar nada.

@api_view(["GET"])
@permission_classes([AllowAny])
def reunion_info(request, token):
    """Info mínima de la reunión para la pantalla de acceso del invitado."""
    inv = (InvitacionVideollamada.objects
           .select_related("conversation", "creado_por")
           .filter(token=token).first())
    if not inv:
        return Response({"vigente": False, "detail": "Invitación no encontrada."}, status=404)
    if not inv.vigente():
        return Response({"vigente": False, "detail": "Esta invitación expiró o fue revocada."}, status=410)
    conv = inv.conversation
    invitado_por = ""
    if inv.creado_por:
        invitado_por = (inv.creado_por.get_full_name() or "").strip() or inv.creado_por.username
    return Response({
        "vigente": True,
        "titulo": conv.titulo or "Videollamada",
        "invitado_por": invitado_por,
        "expira_en": inv.expira_en,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def reunion_token(request, token):
    """Entrega un token LiveKit de INVITADO (permisos limitados) para la sala.

    Body: `{ "nombre": "Nombre del invitado" }`.
    """
    from . import livekit_utils as lk

    inv = (InvitacionVideollamada.objects
           .select_related("conversation").filter(token=token).first())
    if not inv or not inv.vigente():
        return Response({"detail": "Invitación no válida, expirada o revocada."}, status=410)
    if not lk.livekit_configurado():
        return Response({"detail": "Videollamadas no configuradas."}, status=503)

    nombre = (request.data.get("nombre") or "").strip()[:60] or "Invitado"
    conv = inv.conversation
    room = lk.room_name(conv.id)
    identity = f"guest_{uuid.uuid4().hex[:12]}"
    tok = lk.crear_access_token(
        room=room, identity=identity, nombre=f"{nombre} (invitado)", admin=False,
    )

    inv.usos = (inv.usos or 0) + 1
    inv.save(update_fields=["usos"])

    return Response({"url": lk.server_url(), "token": tok, "room": room})


# ── Calendario: reuniones (videollamadas programadas) y tareas ───────────────
class EventoCalendarioViewSet(viewsets.ModelViewSet):
    """Eventos del calendario del usuario: los que creó o en los que participa.
    Filtro por rango con ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD (sobre `inicio`)."""

    serializer_class = EventoCalendarioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        u = self.request.user
        qs = (EventoCalendario.objects
              .filter(Q(creado_por=u) | Q(participantes=u))
              .distinct()
              .select_related("creado_por", "conversation")
              .prefetch_related("participantes"))
        desde = self.request.query_params.get("desde")
        hasta = self.request.query_params.get("hasta")
        if desde:
            qs = qs.filter(inicio__date__gte=desde)
        if hasta:
            qs = qs.filter(inicio__date__lte=hasta)
        return qs

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)

    @action(detail=True, methods=["post"], url_path="completar")
    def completar(self, request, pk=None):
        ev = self.get_object()
        ev.estado = "COMPLETADA"
        ev.save(update_fields=["estado", "actualizado"])
        return Response(self.get_serializer(ev).data)

    @action(detail=True, methods=["post"], url_path="estado")
    def cambiar_estado(self, request, pk=None):
        ev = self.get_object()
        nuevo = (request.data.get("estado") or "").upper()
        if nuevo not in dict(EventoCalendario.ESTADO):
            return Response({"detail": "Estado inválido."}, status=400)
        ev.estado = nuevo
        ev.save(update_fields=["estado", "actualizado"])
        return Response(self.get_serializer(ev).data)


# ── Recordatorios del calendario (avisos "un día antes" y "el mismo día") ────
# Se generan de forma PEREZOSA cuando el front llama a /recordatorios-check/
# (ChatContext lo hace al entrar y cada pocos minutos). Cada aviso se publica
# como mensaje de sistema en la conversación "🔔 Recordatorios" del usuario, así
# aparece en su chat con su badge de no-leídos. No depende de un cron externo.

def _conversacion_recordatorios(user) -> Conversation:
    """Conversación especial (una por usuario) donde caen los recordatorios."""
    conv = (Conversation.objects
            .filter(es_recordatorios=True, memberships__user=user)
            .first())
    if conv:
        return conv
    conv = Conversation.objects.create(
        kind=Conversation.GROUP, titulo="🔔 Recordatorios",
        es_recordatorios=True, creado_por=user,
    )
    Membership.objects.create(conversation=conv, user=user)
    return conv


def _texto_recordatorio(ev: EventoCalendario, tipo: str) -> str:
    from django.utils import timezone as _tz
    etiqueta = "reunión" if ev.tipo == "REUNION" else "tarea"
    hora = _tz.localtime(ev.inicio).strftime("%H:%M")
    if tipo == RecordatorioEvento.DIA_ANTES:
        cuando = "es MAÑANA" if ev.todo_el_dia else f"es MAÑANA a las {hora}"
    else:
        cuando = "es HOY" if ev.todo_el_dia else f"es HOY a las {hora}"
    return f"⏰ Recordatorio: la {etiqueta} «{ev.titulo}» {cuando}."


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def recordatorios_check(request):
    """Genera los recordatorios pendientes del usuario (un día antes / el mismo
    día) y los publica como mensajes. Idempotente: no repite un aviso ya enviado."""
    from django.utils import timezone

    user = request.user
    ahora = timezone.now()
    hoy = timezone.localdate()
    manana = hoy + timedelta(days=1)

    # Candidatos: eventos activos del usuario que empiezan en la ventana ~[-1d, +2d].
    # El bucket real (hoy/mañana) se decide con la fecha LOCAL de cada evento, para
    # que no falle por diferencias de zona horaria en el filtro.
    eventos = (EventoCalendario.objects
               .filter(Q(creado_por=user) | Q(participantes=user))
               .filter(inicio__gte=ahora - timedelta(days=1),
                       inicio__lte=ahora + timedelta(days=2))
               .exclude(estado__in=["COMPLETADA", "CANCELADA"])
               .distinct())

    generados = 0
    conv = None
    for ev in eventos:
        dia = timezone.localtime(ev.inicio).date()
        if dia == hoy:
            tipo = RecordatorioEvento.DIA
        elif dia == manana:
            tipo = RecordatorioEvento.DIA_ANTES
        else:
            continue
        # Aviso EXTERNO (correo / WhatsApp) — una sola vez por evento + hito.
        if ev.canal_recordatorio and ev.canal_recordatorio != "CHAT":
            flag = "recordatorio_ext_dia" if tipo == RecordatorioEvento.DIA else "recordatorio_ext_dia_antes"
            if not getattr(ev, flag, False):
                try:
                    from .notificaciones import enviar_recordatorio_externo
                    enviar_recordatorio_externo(ev, _texto_recordatorio(ev, tipo))
                except Exception:
                    pass
                setattr(ev, flag, True)
                ev.save(update_fields=[flag])
        _, creado = RecordatorioEvento.objects.get_or_create(
            evento=ev, user=user, tipo=tipo,
        )
        if not creado:
            continue  # ya se avisó de este hito
        if conv is None:
            conv = _conversacion_recordatorios(user)
        msg = Message.objects.create(
            conversation=conv, sender=None, es_sistema=True,
            body=_texto_recordatorio(ev, tipo),
        )
        conv.ultimo_mensaje_en = msg.creado
        conv.save(update_fields=["ultimo_mensaje_en"])
        _broadcast(conv, {
            "type": "message.new", "conversation_id": conv.id,
            "message": MessageSerializer(msg).data,
        })
        generados += 1

    return Response({"generados": generados})
