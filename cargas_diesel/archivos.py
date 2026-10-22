"""
Archivos de diésel (fotos de las cargas y factura PDF de las compras) en S3, igual que las remisiones.

Django 5.1 ya no lee DEFAULT_FILE_STORAGE: el almacenamiento por defecto guarda en el disco del
servidor (Render lo borra en cada deploy) mientras MEDIA_URL apunta a S3, así que la foto no se ve.
Las remisiones suben el archivo con boto3 a media/<ruta> y en el campo guardan solo la ruta; aquí se
hace lo mismo. Sin credenciales de AWS (en local) se usa el almacenamiento por defecto.
"""
import logging
import mimetypes
import os
import secrets

import boto3
from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


class ErrorArchivo(Exception):
    """No se pudo guardar un archivo; el mensaje se muestra tal cual."""


def usa_s3():
    return bool(getattr(settings, 'AWS_ACCESS_KEY_ID', None) and getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
                and getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None))


def _cliente():
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )


def _llave(nombre):
    return f"{settings.AWS_MEDIA_LOCATION}/{nombre}"


def subir(instancia, campo, archivo, nombre_visible=None):
    """Sube el archivo del campo y deja en el campo su ruta. La ruta sale del upload_to del campo
    (con la fecha) y lleva una parte al azar para no pisar otra foto con el mismo nombre."""
    field = instancia._meta.get_field(campo)
    nombre_visible = nombre_visible or f'"{field.verbose_name}"'
    base, ext = os.path.splitext(os.path.basename(getattr(archivo, 'name', '') or 'archivo'))
    # Con "/" aunque corra en Windows: es la llave en S3.
    nombre = field.generate_filename(instancia, f'{base[:60]}_{secrets.token_hex(4)}{ext.lower()}').replace('\\', '/')
    try:
        if usa_s3():
            if hasattr(archivo, 'seek'):
                archivo.seek(0)
            tipo = getattr(archivo, 'content_type', None) or mimetypes.guess_type(nombre)[0] or 'application/octet-stream'
            _cliente().upload_fileobj(archivo, settings.AWS_STORAGE_BUCKET_NAME, _llave(nombre),
                                      ExtraArgs={'ContentType': tipo})
        else:
            nombre = default_storage.save(nombre, archivo)
    except Exception as e:
        logger.exception('No se pudo guardar %s (%s)', nombre_visible, nombre)
        raise ErrorArchivo(f'No se pudo guardar {nombre_visible}. Intenta de nuevo.') from e
    setattr(instancia, campo, nombre)
    return nombre


def leer(archivo):
    """Contenido (bytes) de un archivo guardado: de S3 si está configurado; si no está ahí,
    del almacenamiento por defecto (fotos anteriores en el disco del servidor)."""
    if usa_s3():
        try:
            return _cliente().get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=_llave(archivo.name))['Body'].read()
        except Exception:
            logger.warning('No se encontró en S3: %s', archivo.name, exc_info=True)
    with archivo.open('rb') as f:
        return f.read()
