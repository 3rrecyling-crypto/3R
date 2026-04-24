"""
api/views/config.py
GET  /api/v1/config/          → leer toda la configuración
PATCH /api/v1/config/         → editar (requiere can_edit_config)
GET  /api/v1/config/modulos/  → solo flags de módulos habilitados
GET  /api/v1/config/ui/       → solo colores / branding
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from api.models import ConfiguracionSistema
from api.serializers.config import ConfiguracionSistemaSerializer
from api.permissions import CanEditConfig


class ConfiguracionView(APIView):
    """GET y PATCH sobre la configuración maestra."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cfg = ConfiguracionSistema.get_config()
        serializer = ConfiguracionSistemaSerializer(cfg)
        return Response(serializer.data)

    def patch(self, request):
        if not (request.user.is_superuser or request.user.has_perm('api.can_edit_config')):
            return Response(
                {'detail': 'Se requiere permiso para editar la configuración.'},
                status=status.HTTP_403_FORBIDDEN
            )
        cfg = ConfiguracionSistema.get_config()
        serializer = ConfiguracionSistemaSerializer(cfg, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            obj.actualizado_por = request.user
            obj.save(update_fields=['actualizado_por'])
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConfiguracionModulosView(APIView):
    """Solo devuelve los flags de módulos habilitados (público para el layout del frontend)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cfg = ConfiguracionSistema.get_config()
        return Response({
            'modulos': {
                'remisiones': cfg.modulo_remisiones,
                'plastico': cfg.modulo_plastico,
                'tarimas': cfg.modulo_tarimas,
                'maquila': cfg.modulo_maquila,
                'trane': cfg.modulo_trane,
                'medline': cfg.modulo_medline,
                'rh': cfg.modulo_rh,
                'bancos': cfg.modulo_bancos,
                'compras': cfg.modulo_compras,
                'cxp': cfg.modulo_cxp,
                'facturacion': cfg.modulo_facturacion,
                'diesel': cfg.modulo_diesel,
                'chat': cfg.modulo_chat,
                'ia': cfg.modulo_ia,
                'dashboard_patio': cfg.modulo_dashboard_patio,
                'reportes_kpi': cfg.modulo_reportes_kpi,
            },
            'empresa': {
                'nombre': cfg.empresa_nombre,
                'logo_url': cfg.empresa_logo_url,
                'slogan': cfg.empresa_slogan,
            }
        })


class ConfiguracionUIView(APIView):
    """Solo devuelve tokens de diseño (colores, fuentes) para el tema del frontend."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cfg = ConfiguracionSistema.get_config()
        return Response({
            'colores': {
                'primario': cfg.color_primario,
                'secundario': cfg.color_secundario,
                'acento': cfg.color_acento,
                'peligro': cfg.color_peligro,
            },
            'fuente_principal': cfg.fuente_principal,
            'tema_oscuro_por_defecto': cfg.tema_oscuro_por_defecto,
            'idioma_por_defecto': cfg.idioma_por_defecto,
            'zona_horaria': cfg.zona_horaria,
            'moneda_por_defecto': cfg.moneda_por_defecto,
            'items_por_pagina': cfg.items_por_pagina,
        })
