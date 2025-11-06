# PROYECTO/asgi.py

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import chat.routing  # Asegúrate de que esta línea esté presente

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PROYECTO.settings')

application = ProtocolTypeRouter({
    # Manejador para las peticiones HTTP normales (tus vistas de Django)
    "http": get_asgi_application(),

    # Manejador para las conexiones WebSocket
    "websocket": AuthMiddlewareStack(
        URLRouter(
            chat.routing.websocket_urlpatterns
        )
    ),
})