from rest_framework import serializers
from decimal import Decimal
from .models import (
    Patio, PerfilUsuarioDiesel, ProveedorDiesel, Unidad,
    Totem, CompraCombustible, AjusteInventario, CargaDiesel
)


class PatioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patio
        fields = '__all__'


class PatioMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patio
        fields = ['id', 'nombre', 'codigo']


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProveedorDiesel
        fields = '__all__'


class UnidadSerializer(serializers.ModelSerializer):
    patio_detalle = PatioMiniSerializer(source='patio', read_only=True)
    ultimo_rendimiento = serializers.SerializerMethodField()
    total_litros = serializers.SerializerMethodField()

    class Meta:
        model = Unidad
        fields = '__all__'

    def get_ultimo_rendimiento(self, obj):
        return obj.ultimo_rendimiento()

    def get_total_litros(self, obj):
        return obj.total_litros_consumidos()


class TotemSerializer(serializers.ModelSerializer):
    # ¡Quitamos el source='...' de estas dos líneas!
    porcentaje_diesel = serializers.FloatField(read_only=True)
    porcentaje_urea = serializers.FloatField(read_only=True)
    
    estado_diesel = serializers.CharField(read_only=True)
    estado_urea = serializers.CharField(read_only=True)
    alerta_activa_diesel = serializers.BooleanField(read_only=True)
    alerta_activa_urea = serializers.BooleanField(read_only=True)
    patio_detalle = PatioMiniSerializer(source='patio', read_only=True)

    class Meta:
        model = Totem
        fields = '__all__'

class TotemConfigSerializer(serializers.ModelSerializer):
    """Serializer solo para actualizar configuración del tótem."""
    class Meta:
        model = Totem
        fields = [
            'capacidad_diesel', 'alerta_diesel',
            'capacidad_urea', 'alerta_urea',
        ]


class CargaDieselSerializer(serializers.ModelSerializer):
    unidad_detalle = UnidadSerializer(source='unidad', read_only=True)
    patio_detalle = PatioMiniSerializer(source='patio', read_only=True)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = CargaDiesel
        fields = '__all__'
        read_only_fields = ['usuario', 'rendimiento', 'costo_total', 'precio_litro']

    def get_usuario_nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username

    def validate(self, data):
        patio = data.get('patio')
        litros = data.get('litros_diesel', Decimal('0'))
        litros_urea = data.get('litros_urea', Decimal('0'))

        if patio:
            totem = getattr(patio, 'totem', None)
            if not totem:
                raise serializers.ValidationError("Este patio no tiene un tótem configurado.")
            if totem.cantidad_diesel < litros:
                raise serializers.ValidationError(
                    f"Diésel insuficiente. Disponible: {totem.cantidad_diesel}L, Solicitado: {litros}L"
                )
            if litros_urea > 0 and totem.cantidad_urea < litros_urea:
                raise serializers.ValidationError(
                    f"Urea insuficiente. Disponible: {totem.cantidad_urea}L, Solicitado: {litros_urea}L"
                )
        return data

    def create(self, validated_data):
        # Calcular rendimiento
        carga = CargaDiesel(**validated_data)
        carga.rendimiento = carga.calcular_rendimiento()
        carga.calcular_costo()
        carga.save()

        # Descontar del tótem
        totem = carga.patio.totem
        totem.cantidad_diesel = max(totem.cantidad_diesel - carga.litros_diesel, Decimal('0'))
        if carga.litros_urea > 0:
            totem.cantidad_urea = max(totem.cantidad_urea - carga.litros_urea, Decimal('0'))
        totem.save()

        return carga


class CompraCombustibleSerializer(serializers.ModelSerializer):
    proveedor_detalle = ProveedorSerializer(source='proveedor', read_only=True)
    patio_detalle = PatioMiniSerializer(source='patio', read_only=True)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = CompraCombustible
        fields = '__all__'
        read_only_fields = ['usuario', 'total', 'proveedor_nombre']

    def get_usuario_nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username


class AjusteInventarioSerializer(serializers.ModelSerializer):
    patio_detalle = PatioMiniSerializer(source='patio', read_only=True)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = AjusteInventario
        fields = '__all__'
        read_only_fields = ['usuario', 'cantidad_anterior', 'cantidad_posterior']

    def get_usuario_nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username


class DashboardSerializer(serializers.Serializer):
    """Serializer para el dashboard consolidado."""
    totem = TotemSerializer(read_only=True)
    cargas_recientes = CargaDieselSerializer(many=True, read_only=True)
    total_cargas_mes = serializers.IntegerField()
    litros_despachados_mes = serializers.FloatField()
    costo_total_mes = serializers.FloatField()
    rendimiento_promedio = serializers.FloatField()


class UnidadRendimientoSerializer(serializers.ModelSerializer):
    """Para la lista de unidades con historial de rendimiento."""
    ultimo_rendimiento = serializers.SerializerMethodField()
    total_litros = serializers.SerializerMethodField()
    total_cargas = serializers.SerializerMethodField()
    ultima_carga = serializers.SerializerMethodField()
    patio_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Unidad
        fields = [
            'id', 'numero_economico', 'descripcion', 'tipo', 'activo',
            'ultimo_rendimiento', 'total_litros', 'total_cargas',
            'ultima_carga', 'patio_nombre'
        ]

    def get_ultimo_rendimiento(self, obj):
        return obj.ultimo_rendimiento()

    def get_total_litros(self, obj):
        return obj.total_litros_consumidos()

    def get_total_cargas(self, obj):
        return obj.cargas.count()

    def get_ultima_carga(self, obj):
        ultima = obj.cargas.order_by('-fecha_carga').first()
        if ultima:
            return ultima.fecha_carga.isoformat()
        return None

    def get_patio_nombre(self, obj):
        return obj.patio.nombre if obj.patio else 'Sin asignar'
