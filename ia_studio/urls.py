from django.urls import path

from .views import (
    ChatViajeView, EditarCanvasView, GenerarAnalisisViajeView, GenerarCanvasView,
    GenerarChecklistView, GenerarDiagramaView, GenerarGuionVideoView, GenerarImagenView,
)

urlpatterns = [
    path("diagrama/", GenerarDiagramaView.as_view(), name="ia-studio-diagrama"),
    path("canvas/", GenerarCanvasView.as_view(), name="ia-studio-canvas"),
    path("canvas-editar/", EditarCanvasView.as_view(), name="ia-studio-canvas-editar"),
    path("checklist/", GenerarChecklistView.as_view(), name="ia-studio-checklist"),
    path("guion-video/", GenerarGuionVideoView.as_view(), name="ia-studio-guion-video"),
    path("analisis-viaje/", GenerarAnalisisViajeView.as_view(), name="ia-studio-analisis-viaje"),
    path("chat-viaje/", ChatViajeView.as_view(), name="ia-studio-chat-viaje"),
    path("imagen/", GenerarImagenView.as_view(), name="ia-studio-imagen"),
]
