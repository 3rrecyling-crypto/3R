"""
Quién descarga reportes de remisiones (el Excel, el Excel de lo que se ve, los reportes
específicos, el ZIP de documentos Medline y el reporte de destrucción): quien puede ver
remisiones (acceso al módulo Remisiones o "Ver Remisiones") o tiene "Exportar reportes a Excel".
Un usuario con sesión pero sin acceso a remisiones no descarga nada. Sin permiso, Next no muestra
esos botones. El superusuario siempre puede.
"""
from django.http import JsonResponse

PERMISOS = ('ternium.acceso_remisiones', 'ternium.view_remision', 'ternium.exportar_remisiones')
MENSAJE = 'No tienes acceso a Remisiones para descargar sus reportes. Pídelo a un administrador.'


def puede_exportar(user):
    return user.is_authenticated and (user.is_superuser or any(user.has_perm(p) for p in PERMISOS))


def sin_permiso():
    return JsonResponse({'error': 'SIN_PERMISO', 'detail': MENSAJE}, status=403)


def de_mis_empresas(user, queryset):
    """Solo las remisiones de las empresas autorizadas del usuario (el superusuario ve todas)."""
    if user.is_superuser:
        return queryset
    perfil = getattr(user, 'ternium_profile', None)
    return queryset.filter(empresa__in=perfil.empresas_autorizadas.all()) if perfil else queryset.none()
