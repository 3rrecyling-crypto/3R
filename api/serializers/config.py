from rest_framework import serializers
from api.models import ConfiguracionSistema


class ConfiguracionSistemaSerializer(serializers.ModelSerializer):
    # Las API keys de IA se guardan pero NUNCA se devuelven en GET (igual que
    # SANBENITO). En su lugar se expone un booleano "ya hay una guardada".
    ia_api_key_set = serializers.SerializerMethodField()
    imagen_api_key_set = serializers.SerializerMethodField()

    class Meta:
        model = ConfiguracionSistema
        exclude = ['actualizado_por']
        read_only_fields = ['actualizado_en']
        extra_kwargs = {
            'ia_api_key':     {'write_only': True, 'required': False, 'allow_blank': True},
            'imagen_api_key': {'write_only': True, 'required': False, 'allow_blank': True},
        }

    def get_ia_api_key_set(self, obj) -> bool:
        return bool(obj.ia_api_key)

    def get_imagen_api_key_set(self, obj) -> bool:
        return bool(obj.imagen_api_key)

    def update(self, instance, validated_data):
        # No borrar credenciales si llegan vacías: conservar las guardadas.
        for campo in ('ia_api_key', 'imagen_api_key'):
            if not validated_data.get(campo):
                validated_data.pop(campo, None)
        return super().update(instance, validated_data)
