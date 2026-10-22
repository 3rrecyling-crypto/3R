"""
Permiso "Exportar reportes a Excel" (ternium.exportar_remisiones, en /admin/permisos › Dashboard
de Remisiones). Lo piden todas las descargas de reportes de remisiones: el Excel, el Excel de lo
que se ve, los reportes específicos, el ZIP de documentos Medline y el reporte de destrucción.
Sin él, Next no muestra esos botones. El superusuario siempre puede.
"""
from django.http import JsonResponse

PERMISO = 'ternium.exportar_remisiones'
MENSAJE = 'No tienes el permiso "Exportar reportes a Excel". Pídelo a un administrador.'


def puede_exportar(user):
    return user.is_authenticated and (user.is_superuser or user.has_perm(PERMISO))


def sin_permiso():
    return JsonResponse({'error': 'SIN_PERMISO', 'detail': MENSAJE}, status=403)


def de_mis_empresas(user, queryset):
    """Solo las remisiones de las empresas autorizadas del usuario (el superusuario ve todas)."""
    if user.is_superuser:
        return queryset
    perfil = getattr(user, 'ternium_profile', None)
    return queryset.filter(empresa__in=perfil.empresas_autorizadas.all()) if perfil else queryset.none()
