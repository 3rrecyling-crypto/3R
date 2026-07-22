from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("diagramas", views.DiagramaViewSet, basename="diagrama")
router.register("plantillas", views.PlantillaCanvasViewSet, basename="plantilla-canvas")
urlpatterns = router.urls + [
    path("usuarios/", views.UsuariosDisponiblesView.as_view(), name="diagramas-usuarios"),
]
