from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SimulacionViajeViewSet

router = DefaultRouter()
router.register("simulaciones", SimulacionViajeViewSet, basename="simulaciones-viaje")

urlpatterns = [
    path("", include(router.urls)),
]
