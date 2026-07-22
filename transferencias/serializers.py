from rest_framework import serializers

from .models import ArchivoTransferencia, Transferencia


class ArchivoTransferenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchivoTransferencia
        fields = ["id", "nombre", "tamano"]


class TransferenciaSerializer(serializers.ModelSerializer):
    archivos = ArchivoTransferenciaSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    expirada = serializers.BooleanField(read_only=True)

    class Meta:
        model = Transferencia
        fields = ["id", "token", "titulo", "creado_en", "expira_en", "descargas", "expirada", "archivos", "total"]

    def get_total(self, obj: Transferencia) -> int:
        return sum(a.tamano for a in obj.archivos.all())
