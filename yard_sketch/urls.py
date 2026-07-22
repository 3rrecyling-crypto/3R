from django.urls import path

from .views import EditarSketchView, GenerarSketchView

urlpatterns = [
    path("generar/", GenerarSketchView.as_view(), name="yard-sketch-generar"),
    path("editar/", EditarSketchView.as_view(), name="yard-sketch-editar"),
]
