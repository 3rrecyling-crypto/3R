"""
Logos de las tarjetas de "Reportes Específicos por Origen" en la ventana de
descarga de Excel (HTML y Next).

Staff puede subir un logo por reporte (modelo LogoReporte). Si no hay uno
subido se usa el de siempre en S3 y, si tampoco hay, un ícono.
"""
import os
import uuid
from io import BytesIO

S3_LOGOS = 'https://3rrecycling.s3.amazonaws.com/static/Fotos_Reportes/'

# Mismo orden que las tarjetas. 'icono' (Font Awesome) se muestra cuando no hay
# logo o el navegador no lo puede cargar.
REPORTES_ORIGEN = [
    {'clave': 'huaxing', 'nombre': 'HUAXING', 'descripcion': 'Cargas y descargas.',
     'logo': S3_LOGOS + 'HUAXING.jpg', 'icono': 'fa-industry text-secondary'},
    {'clave': 'bachoco', 'nombre': 'BACHOCO', 'descripcion': 'Cargas y descargas.',
     'logo': S3_LOGOS + 'BACHOCO.png', 'icono': 'fa-industry text-secondary'},
    {'clave': 'trane', 'nombre': 'TRANE', 'descripcion': 'Cargas y descargas.',
     'logo': S3_LOGOS + 'TRANE.png', 'icono': 'fa-industry text-secondary'},
    {'clave': 'hudson', 'nombre': 'HUDSON', 'descripcion': 'Con precios y ventas.',
     'logo': S3_LOGOS + 'HUDSON.png', 'icono': 'fa-industry text-secondary'},
    {'clave': 'sealed-air', 'nombre': 'SEALED-AIR', 'descripcion': 'Kg, precio y total por material.',
     'logo': '', 'icono': 'fa-box-open text-info'},
    {'clave': 'proboca', 'nombre': 'PROBOCA', 'descripcion': 'Con Folio de Salida y estatus.',
     'logo': '', 'icono': 'fa-sign-out-alt text-primary'},
]
CLAVES = {r['clave'] for r in REPORTES_ORIGEN}

EXTENSIONES = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
MAX_BYTES = 5 * 1024 * 1024
# Las tarjetas lo muestran a 40-56 px de alto; se guarda con margen para pantallas de alta densidad.
TAMANO_MAX = (480, 160)


def puede_editar(usuario):
    return usuario.is_authenticated and (usuario.is_staff or usuario.is_superuser)


def _subidos(request):
    """{clave: url absoluta} de los logos que subió staff."""
    from .models import LogoReporte

    subidos = {}
    for logo in LogoReporte.objects.filter(clave__in=CLAVES):
        try:
            url = logo.imagen.url
        except Exception:
            continue
        subidos[logo.clave] = request.build_absolute_uri(url) if url.startswith('/') else url
    return subidos


def logos_reportes(request):
    """{clave: {'url': str ('' = ícono), 'personalizado': bool}} para la API (Next)."""
    subidos = _subidos(request)
    return {
        r['clave']: {'url': subidos.get(r['clave'], r['logo']), 'personalizado': r['clave'] in subidos}
        for r in REPORTES_ORIGEN
    }


def reportes_origen(request):
    """Tarjetas para la plantilla HTML: la definición con el logo vigente."""
    subidos = _subidos(request)
    return [
        {**r, 'logo': subidos.get(r['clave'], r['logo']), 'personalizado': r['clave'] in subidos}
        for r in REPORTES_ORIGEN
    ]


def preparar_logo(archivo):
    """
    Valida la imagen subida y la deja lista para guardar: endereza (EXIF),
    reduce a TAMANO_MAX sin recortar y la pasa a PNG (conserva la transparencia).
    Regresa (ContentFile, None) o (None, mensaje de error).
    """
    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError

    if os.path.splitext(archivo.name)[1].lower() not in EXTENSIONES:
        return None, 'Formato no permitido. Usa PNG, JPG, WEBP o GIF.'
    if archivo.size > MAX_BYTES:
        return None, 'La imagen pesa más de 5 MB.'
    try:
        img = Image.open(archivo)
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return None, 'El archivo no es una imagen válida.'

    img = ImageOps.exif_transpose(img).convert('RGBA')
    img.thumbnail(TAMANO_MAX, Image.LANCZOS)
    salida = BytesIO()
    img.save(salida, format='PNG', optimize=True)
    return ContentFile(salida.getvalue(), name=f'{uuid.uuid4().hex[:10]}.png'), None


def guardar_logo(clave, contenido, usuario):
    """Sube o reemplaza el logo de un reporte y borra el archivo anterior."""
    from .models import LogoReporte

    logo = LogoReporte.objects.filter(clave=clave).first() or LogoReporte(clave=clave)
    anterior = logo.imagen.name if logo.imagen else ''
    logo.imagen.save(f'{clave}-{contenido.name}', contenido, save=False)
    logo.actualizado_por = usuario
    logo.save()
    _borrar_archivo(logo.imagen.storage, anterior)


def quitar_logo(clave):
    """Quita el logo subido; la tarjeta vuelve al logo de siempre o al ícono."""
    from .models import LogoReporte

    logo = LogoReporte.objects.filter(clave=clave).first()
    if logo:
        nombre, storage = logo.imagen.name, logo.imagen.storage
        logo.delete()
        _borrar_archivo(storage, nombre)


def _borrar_archivo(storage, nombre):
    if nombre:
        try:
            storage.delete(nombre)
        except Exception:
            pass
