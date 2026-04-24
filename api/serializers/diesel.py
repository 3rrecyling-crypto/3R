"""
api/serializers/diesel.py
"""
from rest_framework import serializers
from cargas_diesel.models import (
    Patio, PerfilUsuarioDiesel, ProveedorDiesel,
    Unidad, Totem, CompraCombustible, AjusteInventario, CargaDiesel,
)


class PatioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patio
        fields = '__all__'


class ProveedorDieselSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProveedorDiesel
        fields = '__all__'


class UnidadDieselSerializer(serializers.ModelSerializer):
    patio_nombre = serializers.CharField(source='patio.nombre', read_only=True)
    ultimo_rendimiento = serializers.SerializerMethodField()

    class Meta:
        model = Unidad
        fields = '__all__'

    def get_ultimo_rendimiento(self, obj):
        try:
            return float(obj.ultimo_rendimiento)
        except Exception:
            return None


class TotemSerializer(serializers.ModelSerializer):
    patio_nombre = serializers.CharField(source='patio.nombre', read_only=True)
    estado_diesel = serializers.SerializerMethodField()
    estado_urea = serializers.SerializerMethodField()
    porcentaje_diesel = serializers.SerializerMethodField()
    porcentaje_urea = serializers.SerializerMethodField()

    class Meta:
        model = Totem
        fields = '__all__'

    def get_estado_diesel(self, obj):
        try:
            return obj.estado_diesel
        except Exception:
            return None

    def get_estado_urea(self, obj):
        try:
            return obj.estado_urea
        except Exception:
            return None

    def get_porcentaje_diesel(self, obj):
        try:
            if obj.capacidad_diesel and obj.capacidad_diesel > 0:
                return round(float(obj.cantidad_diesel / obj.capacidad_diesel * 100), 1)
        except Exception:
            pass
        return 0

    def get_porcentaje_urea(self, obj):
        try:
            if obj.capacidad_urea and obj.capacidad_urea > 0:
                return round(float(obj.cantidad_urea / obj.capacidad_urea * 100), 1)
        except Exception:
            pass
        return 0


class CompraCombustibleSerializer(serializers.ModelSerializer):
    patio_nombre = serializers.CharField(source='patio.nombre', read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = CompraCombustible
        fields = '__all__'

    def get_total(self, obj):
        try:
            return float(obj.total)
        except Exception:
            return None


class AjusteInventarioSerializer(serializers.ModelSerializer):
    patio_nombre = serializers.CharField(source='patio.nombre', read_only=True)

    class Meta:
        model = AjusteInventario
        fields = '__all__'


class CargaDieselSerializer(serializers.ModelSerializer):
    patio_nombre = serializers.CharField(source='patio.nombre', read_only=True)
    unidad_numero = serializers.CharField(source='unidad.numero_economico', read_only=True)
    costo_total = serializers.SerializerMethodField()
    rendimiento = serializers.SerializerMethodField()

    class Meta:
        model = CargaDiesel
        fields = '__all__'

    def get_costo_total(self, obj):
        try:
            return float(obj.costo_total)
        except Exception:
            return None

    def get_rendimiento(self, obj):
        try:
            return float(obj.rendimiento)
        except Exception:
            return None
