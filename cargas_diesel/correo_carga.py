"""
Correo al permisionario con el detalle de cada carga de diésel.

Se manda solo al registrar una carga desde la captura del celular, a los
correos del permisionario de la unidad o del thermo (Catálogos › Permisionarios).
Lleva los datos de la carga (sin costos) y las fotos adjuntas. Sale en un hilo
aparte después del commit para que el despachador no espere al servidor de
correo; si falla, queda en el log y la carga no se ve afectada.
"""
import logging
import mimetypes
import os
import re
import threading

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import connection, transaction
from django.utils import timezone
from django.utils.html import escape

from .archivos import leer
from .models import es_3r_nombre

logger = logging.getLogger(__name__)

FOTOS = [
    ('foto_odometro', 'Odómetro'), ('foto_bomba', 'Foto inicio (Bomba)'), ('foto_bomba_final', 'Foto final (Bomba)'),
    ('foto_horas_thermo', 'Horas del thermo'), ('foto_thermo', 'Foto inicio (Thermo)'),
    ('foto_thermo_final', 'Foto final (Thermo)'),
]


def separar_correos(texto):
    """Correos de un texto separado por comas, punto y coma o espacios."""
    return [c for c in re.split(r'[\s,;]+', texto or '') if c]


def correo_invalido(texto):
    """El primer correo mal escrito del texto, o None si todos están bien."""
    for c in separar_correos(texto):
        try:
            validate_email(c)
        except ValidationError:
            return c
    return None


def _num(n, dec=0):
    return f'{float(n):,.{dec}f}'


def _filas(carga):
    es_thermo = carga.tipo_carga == 'thermo'
    if es_thermo:
        equipo = carga.thermo
        detalle = equipo.descripcion if equipo else ''
    else:
        unidad_cat = carga.unidad.unidad_catalogo if carga.unidad_id else None
        detalle = (unidad_cat.license_plate if unidad_cat else '') or ''
    filas = [
        ('Permisionario', carga.permisionario_nombre or '—'),
        ('Tipo de carga', 'Thermo' if es_thermo else 'Unidad'),
        ('Thermo' if es_thermo else 'Unidad', carga.equipo + (f' · {detalle}' if detalle else '')),
        *([('Operador', carga.operador_nombre)] if carga.operador_nombre else []),
        ('Patio', carga.patio.nombre),
        ('Fecha y hora', timezone.localtime(carga.fecha_carga).strftime('%d/%m/%Y %H:%M')),
        ('Despachador', carga.usuario.get_full_name() or carga.usuario.username),
    ]
    if es_thermo:
        if carga.hrs_thermo:
            filas.append(('Horas del thermo', _num(carga.hrs_thermo, 1)))
        filas.append(('Litros al thermo', f'{_num(carga.litros_thermo, 2)} L'))
    else:
        if carga.odometro is not None:  # solo las unidades de 3R llevan kilometraje
            filas.append(('Kilometraje', f'{_num(carga.odometro)} km'))
        filas.append(('Litros de diésel', f'{_num(carga.litros_diesel, 2)} L'))
        # Solo la flota de 3R maneja rendimiento; las unidades de permisionarios son ajenas.
        if carga.rendimiento is not None and es_3r_nombre(carga.permisionario_nombre):
            filas.append(('Rendimiento', f'{_num(carga.rendimiento, 2)} km/L'))
    # Los cinchos ya no se capturan desde el celular; solo salen si la carga los trae.
    if carga.cinchos_anteriores or carga.cinchos_actuales:
        filas += [
            ('Cinchos anteriores', carga.cinchos_anteriores or '—'),
            ('Cinchos actuales', carga.cinchos_actuales or '—'),
        ]
    return filas


def _correo(carga, n_fotos):
    """(asunto, texto, html) del correo de la carga."""
    fecha = timezone.localtime(carga.fecha_carga).strftime('%d/%m/%Y %H:%M')
    tipo = 'Thermo' if carga.tipo_carga == 'thermo' else 'Unidad'
    asunto = f'Carga de diésel · {tipo} {carga.equipo} · {fecha}'
    filas = _filas(carga)
    nota_fotos = f'Se adjuntan {n_fotos} foto(s) de la carga.' if n_fotos else 'La carga no tiene fotos.'

    texto = '\n'.join([f'CARGA DE DIÉSEL — {tipo.upper()} {carga.equipo}', '',
                       *[f'  {k}: {v}' for k, v in filas], '', nota_fotos])

    celda = 'padding:7px 10px;border-bottom:1px solid #e5e7eb;font-size:13px'
    tabla = ''.join(f"<tr><td style='{celda};color:#6b7280;width:40%'>{escape(k)}</td>"
                    f"<td style='{celda}'><b>{escape(v)}</b></td></tr>" for k, v in filas)
    html = f"""<div style='font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:auto;color:#111827'>
<div style='background:#0F766E;color:#fff;padding:16px 20px;border-radius:8px 8px 0 0'>
  <div style='font-size:12px;opacity:.85'>3R Recycling · Carga de diésel</div>
  <div style='font-size:20px;font-weight:bold'>{escape(tipo)} {escape(carga.equipo)}</div>
</div>
<div style='border:1px solid #e5e7eb;border-top:0;padding:16px 20px;border-radius:0 0 8px 8px'>
  <table style='border-collapse:collapse;width:100%'>{tabla}</table>
  <p style='font-size:12px;color:#6b7280;margin-top:16px'>{escape(nota_fotos)}</p>
</div></div>"""
    return asunto, texto, html


def enviar_correo_carga(carga_id):
    """Manda el correo de la carga. Devuelve (enviado, motivo). Nunca lanza."""
    from .models import CargaDiesel
    try:
        carga = CargaDiesel.objects.select_related(
            'permisionario', 'patio', 'usuario', 'unidad__unidad_catalogo', 'thermo',
        ).filter(pk=carga_id).first()
        if not carga:
            return False, 'La carga no existe.'
        destinatarios = separar_correos(carga.permisionario.correo if carga.permisionario_id else '')
        if not destinatarios:
            return False, 'El permisionario no tiene correo.'

        adjuntos = []
        complementarias = [(f.foto, f'Complementaria {n}') for n, f in enumerate(carga.fotos_complementarias.all(), 1)]
        for archivo, nombre in [(getattr(carga, campo), nombre) for campo, nombre in FOTOS] + complementarias:
            if not archivo:
                continue
            try:
                contenido = leer(archivo)
                ext = os.path.splitext(archivo.name)[1].lower() or '.jpg'
                adjuntos.append((f'{nombre}{ext}', contenido, mimetypes.guess_type(f'x{ext}')[0] or 'image/jpeg'))
            except Exception:
                logger.warning('No se pudo adjuntar la foto %s de la carga %s', nombre, carga_id, exc_info=True)

        asunto, texto, html = _correo(carga, len(adjuntos))
        correo = EmailMultiAlternatives(asunto, texto, settings.DEFAULT_FROM_EMAIL, destinatarios)
        correo.attach_alternative(html, 'text/html')
        for adjunto in adjuntos:
            correo.attach(*adjunto)
        correo.send(fail_silently=False)

        CargaDiesel.objects.filter(pk=carga_id).update(
            correo_enviado_a=', '.join(destinatarios)[:500], correo_enviado_en=timezone.now())
        logger.info('Correo de carga de diésel %s enviado a %s', carga_id, destinatarios)
        return True, f'Enviado a {len(destinatarios)} correo(s).'
    except Exception as e:  # el correo nunca debe afectar la carga
        logger.exception('No se pudo enviar el correo de la carga de diésel %s', carga_id)
        return False, f'No se pudo enviar el correo: {e}'


def programar_correo_carga(carga):
    """Programa el correo para después del commit, en un hilo aparte (el
    despachador no espera al servidor de correo). Devuelve a quién se manda."""
    destinatarios = separar_correos(carga.permisionario.correo if carga.permisionario_id else '')
    if not destinatarios:
        return []
    pk = carga.pk

    def _hilo():
        try:
            enviar_correo_carga(pk)
        finally:
            connection.close()  # el hilo abre su propia conexión a la base

    transaction.on_commit(lambda: threading.Thread(target=_hilo, daemon=True).start())
    return destinatarios
