# chat/routing.py

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Ruta para el chat privado, ahora usa un ID de conversación
    re_path(r'ws/chat/(?P<conversation_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    # Ruta para el estado de presencia global
    re_path(r'ws/status/$', consumers.PresenceConsumer.as_asgi()),
]