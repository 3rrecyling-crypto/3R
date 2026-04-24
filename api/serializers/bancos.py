"""
api/serializers/bancos.py
"""
from rest_framework import serializers
from flujo_bancos.models import (
    Cuenta, UnidadNegocio, Operacion, Categoria, SubCategoria,
    Movimiento, Tercero, ResumenMensual, ComprobanteFiscal,
)


class CuentaSerializer(serializers.ModelSerializer):
    saldo_actual = serializers.SerializerMethodField()

    class Meta:
        model = Cuenta
        fields = '__all__'

    def get_saldo_actual(self, obj):
        try:
            return float(obj.saldo_actual)
        except Exception:
            return None


class UnidadNegocioSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadNegocio
        fields = '__all__'


class OperacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Operacion
        fields = '__all__'


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'


class SubCategoriaSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)

    class Meta:
        model = SubCategoria
        fields = '__all__'


class TerceroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tercero
        fields = '__all__'


class ComprobanteFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComprobanteFiscal
        fields = '__all__'


class MovimientoSerializer(serializers.ModelSerializer):
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True)
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    subcategoria_nombre = serializers.CharField(source='subcategoria.nombre', read_only=True)
    operacion_nombre = serializers.CharField(source='operacion.nombre', read_only=True)
    tercero_nombre = serializers.CharField(source='tercero.nombre', read_only=True)
    comprobantes = ComprobanteFiscalSerializer(many=True, read_only=True)

    class Meta:
        model = Movimiento
        fields = '__all__'


class ResumenMensualSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumenMensual
        fields = '__all__'
