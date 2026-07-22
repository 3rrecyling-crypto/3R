from django.urls import re_path

from .consumers import ChatConsumer

# Ruta WS propia (distinta del chat de plantillas que usa ws/chat/<id>/ y ws/status/).
websocket_urlpatterns = [
    re_path(r"^ws/mensajeria/$", ChatConsumer.as_asgi()),
]
