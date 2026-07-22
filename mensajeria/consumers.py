"""Consumer WebSocket por usuario.

Modelo simple: cada usuario se conecta a `ws/chat/` y entra al grupo
`chat_user_<id>`. Las views REST publican eventos a ese grupo cuando hay un
mensaje nuevo, una lectura, o se agrega/quita a alguien, y el front los
reproduce sobre su estado local.

Eventos emitidos al cliente (envueltos como `{"type": …, "payload": …}` del
broadcast pero el consumer los reenvía como JSON plano):

    {"type": "message.new",        "conversation_id": int, "message": {...}}
    {"type": "conversation.read",  "conversation_id": int, "user_id": int}

El consumer también acepta del cliente:

    {"type": "ping"}                                  -> {"type": "pong"}
    {"type": "typing", "conversation_id": int}        -> broadcast a los demás
"""
from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.user_id = user.id
        self.group = f"chat_user_{user.id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"type": "hello", "user_id": user.id})

    async def disconnect(self, code):
        if getattr(self, "group", None):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        tipo = content.get("type")
        if tipo == "ping":
            await self.send_json({"type": "pong"})
            return
        if tipo == "typing":
            conv_id = content.get("conversation_id")
            if not conv_id:
                return
            # Reenvía a los otros miembros que el usuario está escribiendo.
            otros = await _otros_user_ids(conv_id, self.user_id)
            for uid in otros:
                await self.channel_layer.group_send(
                    f"chat_user_{uid}",
                    {"type": "chat.event", "payload": {
                        "type": "typing",
                        "conversation_id": conv_id,
                        "user_id": self.user_id,
                    }},
                )

    # Handler que recibe los mensajes "chat.event" del group_send.
    async def chat_event(self, event):
        await self.send_json(event["payload"])


@database_sync_to_async
def _otros_user_ids(conv_id: int, yo_id: int) -> list[int]:
    from .models import Membership
    return list(Membership.objects
                .filter(conversation_id=conv_id, salido_en__isnull=True)
                .exclude(user_id=yo_id)
                .values_list("user_id", flat=True))
