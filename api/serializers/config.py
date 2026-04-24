from rest_framework import serializers
from api.models import ConfiguracionSistema


class ConfiguracionSistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionSistema
        exclude = ['actualizado_por']
        read_only_fields = ['actualizado_en']
