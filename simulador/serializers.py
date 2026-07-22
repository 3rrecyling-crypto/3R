from __future__ import annotations

from rest_framework import serializers

from .models import SimulacionViaje


class SimulacionViajeSerializer(serializers.ModelSerializer):
    creado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = SimulacionViaje
        fields = ["id", "nombre", "es_plantilla", "data", "resultado",
                  "creado_por", "creado_por_nombre", "creado", "actualizado"]
        read_only_fields = ["creado_por", "creado", "actualizado"]

    def get_creado_por_nombre(self, obj):
        u = obj.creado_por
        if not u:
            return ""
        return (getattr(u, "get_full_name", lambda: "")() or u.username or "").strip()


class SimulacionViajeListSerializer(SimulacionViajeSerializer):
    """Listado ligero: sin la captura completa (data puede pesar)."""

    class Meta(SimulacionViajeSerializer.Meta):
        fields = ["id", "nombre", "es_plantilla", "resultado",
                  "creado_por_nombre", "creado", "actualizado"]
