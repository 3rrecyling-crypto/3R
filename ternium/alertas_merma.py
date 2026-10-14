"""
Alertas de merma: una notificación por remisión cuando algún material supera
su umbral (ConfiguracionAlertaMerma; 1 % si el material no tiene uno propio).

Reglas:
  - Solo cuentan los materiales que ya tienen descarga capturada (peso de
    descarga o de rechazo). Sin descarga la merma saldría 100 % y sería falsa.
  - Las remisiones canceladas no generan alerta.
  - Se alerta cuando la merma es MAYOR O IGUAL al umbral.
  - Una sola vez por remisión (RemisionAlertaMermaLog). El registro se crea
    solo si el correo salió; si falla, se reintenta en la siguiente edición.
  - Correo a los destinatarios de /admin/alertas-merma y aviso en el Centro de
    Alertas (campana) para el staff.

La usan igual el HTML de Django (views.py) y la API de Next (api_views.py),
siempre después de guardar (transaction.on_commit).
"""
from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from .models import (
    Alerta, ConfiguracionAlertaMerma, DestinatarioAlertaMerma, Remision, RemisionAlertaMermaLog,
)

logger = logging.getLogger(__name__)

UMBRAL_DEFAULT = 1.0


def materiales_con_merma(remision):
    """[{material, peso_ld, peso_dlv, peso_rechazado, merma_kg, pct_merma, umbral}] de los
    materiales con descarga capturada cuya merma es ≥ a su umbral."""
    alertas = []
    for det in remision.detalles.select_related('material').all():
        if not det.material:
            continue
        peso_ld = float(det.peso_ld or 0)
        peso_dlv = float(det.peso_dlv or 0)
        peso_rechazado = float(det.peso_rechazado or 0)
        if peso_ld <= 0 or (peso_dlv <= 0 and peso_rechazado <= 0):
            continue  # sin carga o sin descarga capturada todavía
        merma_kg = peso_ld - (peso_dlv + peso_rechazado)
        if merma_kg <= 0:
            continue
        pct = merma_kg / peso_ld * 100
        try:
            umbral = float(det.material.config_alerta_merma.porcentaje_umbral)
        except ConfiguracionAlertaMerma.DoesNotExist:
            umbral = UMBRAL_DEFAULT
        if round(pct, 2) >= umbral:
            alertas.append({
                'material': det.material.nombre, 'peso_ld': peso_ld, 'peso_dlv': peso_dlv,
                'peso_rechazado': peso_rechazado, 'merma_kg': merma_kg, 'pct_merma': pct, 'umbral': umbral,
            })
    return alertas


def _txt(v, fallback='—'):
    s = str(v).strip() if v is not None else ''
    return s or fallback


def _fecha(d, formato='%d/%m/%Y'):
    if not d:
        return '—'
    try:
        if hasattr(d, 'tzinfo') and getattr(d, 'tzinfo', None) is not None:
            d = timezone.localtime(d)
        return d.strftime(formato)
    except Exception:
        return str(d)


def _num(n, dec=2):
    try:
        return f'{float(n):,.{dec}f}' if n is not None else '—'
    except (TypeError, ValueError):
        return '—'


def _datos(remision):
    unidad = remision.unidad if remision.unidad_id else None
    contenedor = remision.contenedor if remision.contenedor_id else None
    return [
        ('IDENTIFICACIÓN', [
            ('Folio de remisión', _txt(remision.remision)),
            ('Unidad de negocio', _txt(remision.empresa.nombre if remision.empresa_id else None)),
            ('Cliente', _txt(remision.cliente.nombre if remision.cliente_id else None)),
            ('Fecha', _fecha(remision.fecha)),
            ('Estatus', remision.get_status_display()),
            ('Folio Medline', _txt(remision.folio_medline)),
            ('Folio de salida', _txt(remision.folio_salida)),
        ]),
        ('TRANSPORTE', [
            ('Operador', _txt(remision.operador.nombre if remision.operador_id else remision.operador_manual)),
            ('Línea de transporte', _txt(remision.linea_transporte.nombre if remision.linea_transporte_id else None)),
            ('Unidad', _txt(unidad.internal_id if unidad else remision.unidad_manual)),
            ('Placas unidad', _txt(remision.placas_unidad_manual or (unidad.license_plate if unidad else None))),
            ('Contenedor', _txt(contenedor.nombre if contenedor else remision.contenedor_manual)),
            ('Placas contenedor', _txt(remision.placas_contenedor_manual or (contenedor.placas if contenedor else None))),
        ]),
        ('RUTA Y TIEMPOS', [
            ('Origen', _txt(remision.origen.nombre if remision.origen_id else None)),
            ('Destino', _txt(remision.destino.nombre if remision.destino_id else None)),
            ('Inicia carga', _fecha(remision.inicia_ld, '%d/%m/%Y %H:%M')),
            ('Termina carga', _fecha(remision.termina_ld, '%d/%m/%Y %H:%M')),
            ('Folio de carga', _txt(remision.folio_ld)),
            ('Inicia descarga', _fecha(remision.inicia_dlv, '%d/%m/%Y %H:%M')),
            ('Termina descarga', _fecha(remision.termina_dlv, '%d/%m/%Y %H:%M')),
            ('Folio de descarga', _txt(remision.folio_dlv)),
        ]),
        ('BÁSCULA Y FACTURA', [
            ('Peso báscula', f'{_num(remision.peso_bascula, 3)} kg' if remision.peso_bascula is not None else '—'),
            ('Factura', _txt(remision.factura_nombre)),
            ('Comentario', _txt(remision.comentario)),
        ]),
    ]


def _correo(remision, alertas):
    """(asunto, texto, html) del correo de alerta."""
    total_ld, total_dlv, total_rech = (float(remision.total_peso_ld), float(remision.total_peso_dlv),
                                       float(remision.total_peso_rechazado))
    pct_global = float(remision.porcentaje_merma)
    peor = max(alertas, key=lambda a: a['pct_merma'])
    base = getattr(settings, 'NEXT_APP_URL', 'https://app.3recycling.com.mx').rstrip('/')
    enlace = f'{base}/detalle-remision/{remision.id}'
    asunto = f"⚠️ Merma {peor['pct_merma']:.2f}% · Remisión {remision.remision}"

    lineas_alerta = [
        f"  • {a['material']}: {a['merma_kg']:,.2f} kg perdidos ({a['pct_merma']:.2f}% — umbral {a['umbral']:.2f}%)"
        for a in alertas
    ]
    detalle = []
    for det in remision.detalles.select_related('material').all():
        pld, pdlv, prec = float(det.peso_ld or 0), float(det.peso_dlv or 0), float(det.peso_rechazado or 0)
        mkg = pld - (pdlv + prec)
        mpct = mkg / pld * 100 if pld > 0 else 0
        detalle.append((det.material.nombre if det.material else '—', pld, pdlv, prec, mkg, mpct))

    texto = [
        f'ALERTA DE MERMA — REMISIÓN {remision.remision}',
        '',
        'Materiales que alcanzan o superan su umbral de merma:',
        *lineas_alerta,
        '',
        f'Totales: carga {total_ld:,.2f} kg · descarga {total_dlv:,.2f} kg · rechazo {total_rech:,.2f} kg · '
        f'merma global {pct_global:.2f}%',
        '',
    ]
    for titulo, filas in _datos(remision):
        texto.append(f'— {titulo} —')
        texto += [f'  {k}: {v}' for k, v in filas]
        texto.append('')
    texto.append('— DETALLE POR MATERIAL —')
    texto += [f'  • {m}: carga {a:,.2f} kg | descarga {b:,.2f} kg | rechazo {c:,.2f} kg | merma {d:+,.2f} kg ({e:+.2f}%)'
              for m, a, b, c, d, e in detalle]
    texto += ['', f'Revisa la remisión en el sistema: {enlace}']

    celda = 'padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:13px'
    filas_alerta = ''.join(
        f"<tr><td style='{celda}'><b>{escape(a['material'])}</b></td>"
        f"<td style='{celda};text-align:right'>{a['merma_kg']:,.2f} kg</td>"
        f"<td style='{celda};text-align:right;color:#C0392B'><b>{a['pct_merma']:.2f}%</b></td>"
        f"<td style='{celda};text-align:right'>{a['umbral']:.2f}%</td></tr>" for a in alertas)
    secciones = ''.join(
        f"<h3 style='font-size:13px;color:#1F4E79;margin:18px 0 6px'>{escape(t)}</h3><table style='border-collapse:collapse;width:100%'>"
        + ''.join(f"<tr><td style='{celda};color:#6b7280;width:40%'>{escape(k)}</td><td style='{celda}'>{escape(v)}</td></tr>"
                  for k, v in filas)
        + '</table>' for t, filas in _datos(remision))
    filas_detalle = ''.join(
        f"<tr><td style='{celda}'>{escape(m)}</td><td style='{celda};text-align:right'>{a:,.2f}</td>"
        f"<td style='{celda};text-align:right'>{b:,.2f}</td><td style='{celda};text-align:right'>{c:,.2f}</td>"
        f"<td style='{celda};text-align:right'>{d:+,.2f}</td><td style='{celda};text-align:right'>{e:+.2f}%</td></tr>"
        for m, a, b, c, d, e in detalle)
    encabezado = "style='padding:6px 10px;background:#1F4E79;color:#fff;font-size:12px;text-align:left'"
    html = f"""<div style='font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:auto;color:#111827'>
<div style='background:#1F4E79;color:#fff;padding:16px 20px;border-radius:8px 8px 0 0'>
  <div style='font-size:12px;opacity:.85'>3R Recycling · Alerta de merma</div>
  <div style='font-size:20px;font-weight:bold'>Remisión {escape(remision.remision)}</div>
</div>
<div style='border:1px solid #e5e7eb;border-top:0;padding:16px 20px;border-radius:0 0 8px 8px'>
  <p style='font-size:14px'>Estos materiales alcanzaron o superaron su umbral de merma:</p>
  <table style='border-collapse:collapse;width:100%'>
    <tr><th {encabezado}>Material</th><th {encabezado}>Merma</th><th {encabezado}>%</th><th {encabezado}>Umbral</th></tr>
    {filas_alerta}
  </table>
  <p style='font-size:13px;margin-top:14px'>Totales: carga <b>{total_ld:,.2f} kg</b> · descarga <b>{total_dlv:,.2f} kg</b> ·
  rechazo <b>{total_rech:,.2f} kg</b> · merma global <b>{pct_global:.2f}%</b></p>
  {secciones}
  <h3 style='font-size:13px;color:#1F4E79;margin:18px 0 6px'>DETALLE POR MATERIAL (kg)</h3>
  <table style='border-collapse:collapse;width:100%'>
    <tr><th {encabezado}>Material</th><th {encabezado}>Carga</th><th {encabezado}>Descarga</th><th {encabezado}>Rechazo</th><th {encabezado}>Merma</th><th {encabezado}>%</th></tr>
    {filas_detalle}
  </table>
  <p style='margin-top:20px'><a href='{enlace}' style='background:#1F4E79;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-size:13px'>Ver la remisión</a></p>
</div></div>"""
    return asunto, '\n'.join(texto), html


def enviar_alerta_merma(remision):
    """Envía la alerta si aplica. Devuelve (enviada, motivo). Nunca lanza."""
    try:
        if remision.status == 'CANCELADO':
            return False, 'La remisión está cancelada.'
        if RemisionAlertaMermaLog.objects.filter(remision=remision).exists():
            return False, 'Ya se envió la alerta de esta remisión.'
        alertas = materiales_con_merma(remision)
        if not alertas:
            return False, 'Ningún material alcanza su umbral de merma.'
        destinatarios = list(DestinatarioAlertaMerma.objects.values_list('email', flat=True))
        if not destinatarios:
            logger.warning('Alerta de merma sin destinatarios — remisión %s', remision.remision)
            return False, 'No hay correos configurados en Alertas de Merma.'

        asunto, texto, html = _correo(remision, alertas)
        correo = EmailMultiAlternatives(asunto, texto, settings.DEFAULT_FROM_EMAIL, destinatarios)
        correo.attach_alternative(html, 'text/html')
        correo.send(fail_silently=False)

        resumen = '\n'.join(f"{a['material']}: {a['merma_kg']:,.2f} kg ({a['pct_merma']:.2f}% — umbral {a['umbral']:.2f}%)"
                            for a in alertas)
        with transaction.atomic():
            _, creado = RemisionAlertaMermaLog.objects.get_or_create(
                remision=remision, defaults={'materiales_alertados': len(alertas), 'detalle': resumen})
            if creado:
                peor = max(alertas, key=lambda a: a['pct_merma'])
                Alerta.objects.create(
                    tipo='warning',
                    title=f"Merma {peor['pct_merma']:.2f}% · Remisión {remision.remision}"[:200],
                    desc=f"{remision.empresa.nombre if remision.empresa_id else ''} · "
                         f"{remision.origen.nombre if remision.origen_id else '—'} → "
                         f"{remision.destino.nombre if remision.destino_id else '—'}\n{resumen}",
                )
        logger.info('Alerta de merma enviada — remisión %s a %d correos', remision.remision, len(destinatarios))
        return True, f'Alerta enviada a {len(destinatarios)} correo(s).'
    except Exception as e:  # el correo nunca debe tumbar el guardado de la remisión
        logger.exception('No se pudo enviar la alerta de merma de la remisión %s', getattr(remision, 'pk', None))
        return False, f'No se pudo enviar el correo: {e}'


# ════════════════════════════════════════════════════════════════════════════
# API para la página /admin/alertas-merma (superusuario)
# ════════════════════════════════════════════════════════════════════════════

def _solo_superusuario(vista):
    import json
    from django.http import JsonResponse

    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'detail': 'No autenticado.'}, status=401)
        if not request.user.is_superuser:
            return JsonResponse({'detail': 'Solo administradores.'}, status=403)
        try:
            request.datos = json.loads(request.body or b'{}') if request.method == 'POST' else {}
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({'detail': 'Datos no válidos.'}, status=400)
        return vista(request, *args, **kwargs)
    envoltura.__name__ = vista.__name__
    return envoltura


def _correo_configurado():
    return bool(getattr(settings, 'EMAIL_HOST_USER', None) and getattr(settings, 'EMAIL_HOST_PASSWORD', None)) \
        or 'smtp' not in getattr(settings, 'EMAIL_BACKEND', '')


def remisiones_pendientes(dias=30, tope=3000):
    """Remisiones recientes (por fecha de inicio de descarga) con merma ≥ umbral y sin alerta enviada."""
    from django.db.models import Prefetch
    from django.db.models.functions import Coalesce, TruncDate
    from .models import DetalleRemision
    desde = timezone.localdate() - dt.timedelta(days=dias)
    qs = (Remision.objects.exclude(status='CANCELADO').filter(alerta_merma_log__isnull=True)
          .annotate(fecha_ref=Coalesce(TruncDate('inicia_dlv'), 'fecha')).filter(fecha_ref__gte=desde)
          .select_related('empresa', 'origen', 'destino')
          .prefetch_related(Prefetch('detalles', queryset=DetalleRemision.objects.select_related(
              'material', 'material__config_alerta_merma')))
          .order_by('-fecha_ref', '-pk')[:tope])
    pendientes = []
    for r in qs:
        alertas = materiales_con_merma(r)
        if alertas:
            peor = max(alertas, key=lambda a: a['pct_merma'])
            pendientes.append({
                'remision_id': r.pk, 'remision': r.remision, 'fecha': r.fecha_ref.isoformat() if r.fecha_ref else None,
                'empresa': r.empresa.nombre if r.empresa_id else '', 'origen': r.origen.nombre if r.origen_id else '',
                'destino': r.destino.nombre if r.destino_id else '', 'status': r.get_status_display(),
                'materiales': [f"{a['material']} {a['pct_merma']:.2f}%" for a in alertas],
                'merma_max': round(peor['pct_merma'], 2),
            })
    return pendientes


def api_historial(request):
    from django.http import JsonResponse
    try:
        dias = max(1, min(int(request.GET.get('dias') or 30), 365))
    except ValueError:
        dias = 30
    enviadas = [{
        'remision_id': log.remision_id, 'remision': log.remision.remision,
        'empresa': log.remision.empresa.nombre if log.remision.empresa_id else '',
        'enviada_en': timezone.localtime(log.enviada_en).isoformat(),
        'materiales': log.materiales_alertados, 'detalle': log.detalle,
    } for log in RemisionAlertaMermaLog.objects.select_related('remision', 'remision__empresa').order_by('-enviada_en')[:100]]
    return JsonResponse({
        'correo': {'configurado': _correo_configurado(), 'remitente': settings.DEFAULT_FROM_EMAIL,
                   'destinatarios': DestinatarioAlertaMerma.objects.count()},
        'enviadas': enviadas,
        'pendientes': remisiones_pendientes(dias),
        'dias': dias,
    })


def api_prueba(request):
    """Correo de prueba a los destinatarios configurados (o a uno indicado)."""
    from django.http import JsonResponse
    destino = (request.datos.get('email') or '').strip().lower()
    destinatarios = [destino] if destino else list(DestinatarioAlertaMerma.objects.values_list('email', flat=True))
    if not destinatarios:
        return JsonResponse({'ok': False, 'detail': 'Agrega al menos un correo para recibir las alertas.'}, status=400)
    try:
        correo = EmailMultiAlternatives(
            'Prueba · Alertas de merma 3R Recycling',
            'Este es un correo de prueba de las alertas de merma. Si lo recibiste, el envío funciona.',
            settings.DEFAULT_FROM_EMAIL, destinatarios)
        correo.send(fail_silently=False)
    except Exception as e:
        logger.exception('Falló el correo de prueba de alertas de merma')
        return JsonResponse({'ok': False, 'detail': f'El servidor de correo rechazó el envío: {e}'}, status=502)
    return JsonResponse({'ok': True, 'detail': f'Correo de prueba enviado a {", ".join(destinatarios)}.'})


def api_enviar(request):
    """Envía las alertas de las remisiones indicadas (las pendientes que eligió el usuario)."""
    from django.http import JsonResponse
    ids = [int(i) for i in (request.datos.get('remision_ids') or []) if str(i).isdigit()][:50]
    resultados = []
    for r in Remision.objects.filter(pk__in=ids).select_related(
            'empresa', 'cliente', 'origen', 'destino', 'operador', 'linea_transporte', 'unidad', 'contenedor'):
        enviada, motivo = enviar_alerta_merma(r)
        resultados.append({'remision_id': r.pk, 'remision': r.remision, 'enviada': enviada, 'motivo': motivo})
    return JsonResponse({'resultados': resultados, 'enviadas': sum(1 for x in resultados if x['enviada'])})


api_historial = require_http_methods(['GET'])(_solo_superusuario(api_historial))
api_prueba = require_http_methods(['POST'])(_solo_superusuario(api_prueba))
api_enviar = require_http_methods(['POST'])(_solo_superusuario(api_enviar))


def programar_alerta_merma(remision):
    """Evalúa y envía la alerta cuando termine de guardarse la remisión (después
    del commit, para no mandar correos de cambios que se revierten)."""
    pk = remision.pk

    def _enviar():
        actual = Remision.objects.filter(pk=pk).select_related(
            'empresa', 'cliente', 'origen', 'destino', 'operador', 'linea_transporte', 'unidad', 'contenedor',
        ).first()
        if actual:
            enviar_alerta_merma(actual)

    transaction.on_commit(_enviar)
