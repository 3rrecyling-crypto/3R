"""
api/serializers/compras.py
"""
from rest_framework import serializers
from compras.models import (
    Proveedor, Categoria, UnidadMedida, Articulo,
    ArticuloProveedor, SolicitudCompra, DetalleSolicitud,
    OrdenCompra, DetalleOrdenCompra,
)


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = '__all__'


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'


class UnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadMedida
        fields = '__all__'


class ArticuloProveedorSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.razon_social', read_only=True)

    class Meta:
        model = ArticuloProveedor
        fields = '__all__'


class ArticuloSerializer(serializers.ModelSerializer):
    proveedores = ArticuloProveedorSerializer(
        many=True, read_only=True, source='articuloproveedor_set'
    )

    class Meta:
        model = Articulo
        fields = '__all__'


class DetalleSolicitudSerializer(serializers.ModelSerializer):
    articulo_nombre = serializers.CharField(source='articulo.nombre', read_only=True)

    class Meta:
        model = DetalleSolicitud
        fields = '__all__'


class SolicitudCompraSerializer(serializers.ModelSerializer):
    solicitante_nombre = serializers.SerializerMethodField()
    detalles = DetalleSolicitudSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = SolicitudCompra
        fields = '__all__'

    def get_solicitante_nombre(self, obj):
        return obj.solicitante.get_full_name() if obj.solicitante else ''

    def get_total(self, obj):
        try:
            return float(
                sum(d.cantidad * d.precio_unitario for d in obj.detalles.all())
            )
        except Exception:
            return None


class DetalleOrdenCompraSerializer(serializers.ModelSerializer):
    articulo_nombre = serializers.CharField(source='articulo.nombre', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = DetalleOrdenCompra
        fields = '__all__'

    def get_subtotal(self, obj):
        try:
            return float(obj.subtotal)
        except Exception:
            return None


class OrdenCompraSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.razon_social', read_only=True)
    detalles = DetalleOrdenCompraSerializer(many=True, read_only=True)
    total_general = serializers.SerializerMethodField()

    class Meta:
        model = OrdenCompra
        fields = '__all__'

    def get_total_general(self, obj):
        try:
            return float(
                sum(d.subtotal for d in obj.detalles.all())
            )
        except Exception:
            return None
