from django.conf import settings


def version_nueva(request):
    """Dirección de la versión nueva (Next.js) para el botón de la barra."""
    return {'NEXT_APP_URL': getattr(settings, 'NEXT_APP_URL', 'https://app.3recycling.com.mx')}
