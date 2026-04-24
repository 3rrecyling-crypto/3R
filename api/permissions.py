"""
api/permissions.py
Permisos DRF reutilizables que espejean el modelo de permisos Django.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated


class IsAuthenticatedOrToken(IsAuthenticated):
    """Permite acceso por sesión Django O por token DRF."""
    pass


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class CanEditConfig(BasePermission):
    message = 'Se requiere permiso: api.can_edit_config'

    def has_permission(self, request, view):
        return (
            request.user.is_superuser or
            request.user.has_perm('api.can_edit_config')
        )


class AccesoRemisiones(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_superuser or
            request.user.has_perm('ternium.acceso_remisiones')
        )


class AccesoCatalogos(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_superuser or
            request.user.has_perm('ternium.acceso_catalogos')
        )


class AccesoBancos(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_superuser or
            request.user.has_perm('flujo_bancos.acceso_flujo_bancos')
        )


class AccesoDiesel(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_superuser or
            request.user.has_perm('ternium.acceso_diesel')
        )


class AccesoRH(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_superuser or
            request.user.has_perm('RH.view_empleado')
        )


class AccesoReportes(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_superuser or
            request.user.has_perm('ternium.acceso_reportes_kpi')
        )


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in ('GET', 'HEAD', 'OPTIONS')
