"""API del Simulador de Viajes: historial y plantillas por usuario.

Nota 3r: el endpoint de código postal de SANBENITO NO se porta; se reusa el de
3r en /api/v1/codigo-postal/. Esta app solo maneja el CRUD de simulaciones.
"""
from __future__ import annotations

from rest_framework import permissions, viewsets

from .models import SimulacionViaje
from .serializers import SimulacionViajeListSerializer, SimulacionViajeSerializer


class SimulacionViajeViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Cada quien ve sus simulaciones; los superusuarios ven todas.
        qs = SimulacionViaje.objects.all()
        u = self.request.user
        if not u.is_superuser:
            qs = qs.filter(creado_por=u)
        if self.request.query_params.get("plantillas") == "1":
            qs = qs.filter(es_plantilla=True)
        return qs

    def get_serializer_class(self):
        return SimulacionViajeListSerializer if self.action == "list" else SimulacionViajeSerializer

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)
