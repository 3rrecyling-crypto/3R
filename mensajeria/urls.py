from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("conversaciones", views.ConversationViewSet, basename="chat-conv")
router.register("eventos", views.EventoCalendarioViewSet, basename="chat-evento")

urlpatterns = [
    path("no-leidos/", views.no_leidos, name="chat-no-leidos"),
    path("recordatorios-check/", views.recordatorios_check, name="chat-recordatorios-check"),
    path("usuarios/", views.usuarios, name="chat-usuarios"),
    path("videollamadas-activas/", views.videollamadas_activas, name="chat-videollamadas-activas"),
    path("invitaciones/<uuid:token>/revocar/", views.revocar_invitacion, name="chat-invitacion-revocar"),
    # Públicos (invitados externos sin cuenta):
    path("reunion/<uuid:token>/", views.reunion_info, name="chat-reunion-info"),
    path("reunion/<uuid:token>/token/", views.reunion_token, name="chat-reunion-token"),
]
urlpatterns += router.urls
