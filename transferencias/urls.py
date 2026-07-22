from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import TransferenciaViewSet, publico_descarga, publico_detalle

router = DefaultRouter()
router.register(r"", TransferenciaViewSet, basename="transferencias")

# Rutas resultantes (bajo /api/transferencias/):
#   GET/POST  /                          mis transferencias / crear (multipart 'archivos')
#   DELETE    /<id>/                     eliminar (borra blobs)
#   GET       /publico/<token>/          metadatos públicos (sin cuenta)
#   GET       /publico/<token>/archivo/<id>/   descarga proxy (sin cuenta)
urlpatterns = [
    path("publico/<str:token>/", publico_detalle),
    path("publico/<str:token>/archivo/<int:archivo_id>/", publico_descarga),
] + router.urls
