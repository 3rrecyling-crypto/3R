"""
api/serializers/cxp.py
"""
from rest_framework import serializers
from cuentas_por_pagar.models import Factura, Pago


class PagoSerializer(serializers.ModelSerializer):
    registrado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = '__all__'

    def get_registrado_por_nombre(self, obj):
        return obj.registrado_por.get_full_name() if obj.registrado_por else ''


class FacturaCxPSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.razon_social', read_only=True)
    pagos = PagoSerializer(many=True, read_only=True)
    monto_pagado = serializers.SerializerMethodField()
    monto_pendiente = serializers.SerializerMethodField()
    porcentaje_pagado = serializers.SerializerMethodField()
    dias_restantes = serializers.SerializerMethodField()
    plazos_programados = serializers.SerializerMethodField()

    class Meta:
        model = Factura
        fields = '__all__'

    def get_monto_pagado(self, obj):
        try:
            return float(obj.monto_pagado)
        except Exception:
            return 0

    def get_monto_pendiente(self, obj):
        try:
            return float(obj.monto_pendiente)
        except Exception:
            return None

    def get_porcentaje_pagado(self, obj):
        try:
            return round(float(obj.monto_pagado / obj.monto * 100), 1)
        except Exception:
            return 0

    def get_dias_restantes(self, obj):
        try:
            return obj.dias_restantes_credito
        except Exception:
            return None

    def get_plazos_programados(self, obj):
        try:
            return obj.plazos_programados
        except Exception:
            return []
