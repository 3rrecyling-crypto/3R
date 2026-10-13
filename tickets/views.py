# tickets/views.py
# API JSON de la mesa de ayuda (la consume Next.js con la sesión de Django).
#
#   GET  /api/tickets/                  lista + indicadores (POST = crear ticket)
#   GET  /api/tickets/<id>/             detalle con conversación y archivos
#   POST /api/tickets/<id>/comentarios/ comentario con archivos opcionales
#   POST /api/tickets/<id>/actualizar/  estado, prioridad, responsable, seguimiento
#
# Cualquier usuario crea tickets y ve los suyos. Quien "atiende" (staff,
# superusuario o permiso tickets.atender_tickets) ve todos y les da seguimiento.
import datetime
import json
import os

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Ticket, TicketArchivo, TicketComentario

User = get_user_model()

MAX_ARCHIVOS = 10
MAX_BYTES = 10 * 1024 * 1024  # 10 MB por archivo
EXTENSIONES = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.heic', '.bmp',
    '.doc', '.docx', '.xls', '.xlsx', '.csv', '.ppt', '.pptx', '.txt',
    '.zip', '.rar', '.7z', '.mp4', '.mov', '.webm', '.xml', '.json',
}
ORDEN_PRIORIDAD = Case(
    When(prioridad=Ticket.Prioridad.CRITICA, then=Value(0)),
    When(prioridad=Ticket.Prioridad.ALTA, then=Value(1)),
    When(prioridad=Ticket.Prioridad.MEDIA, then=Value(2)),
    default=Value(3), output_field=IntegerField(),
)


class ErrorTicket(Exception):
    def __init__(self, detalle, status=400):
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _puede_atender(user):
    return user.is_superuser or user.is_staff or user.has_perm('tickets.atender_tickets')


def _nombre(user):
    if not user:
        return ''
    return user.get_full_name().strip() or user.username


def _iso(valor):
    return valor.isoformat() if valor else None


def _url(request, archivo):
    try:
        url = archivo.archivo.url
    except Exception:
        return None
    return request.build_absolute_uri(url) if url.startswith('/') else url


def _archivo_dict(request, a):
    return {
        'id': a.id, 'nombre': a.nombre, 'tamano': a.tamano, 'url': _url(request, a),
        'subido_por': _nombre(a.subido_por), 'subido_en': _iso(a.subido_en),
        'comentario_id': a.comentario_id,
    }


def _ticket_dict(t):
    return {
        'id': t.id, 'folio': t.folio,
        'titulo': t.titulo,
        'tipo': t.tipo, 'tipo_display': t.get_tipo_display(),
        'modulo': t.modulo, 'modulo_display': t.get_modulo_display(),
        'prioridad': t.prioridad, 'prioridad_display': t.get_prioridad_display(),
        'estado': t.estado, 'estado_display': t.get_estado_display(),
        'abierto': t.abierto,
        'en_atencion': t.en_atencion,
        'por_cerrar': t.estado == Ticket.Estado.RESUELTO,
        'solicitante': _nombre(t.solicitante), 'solicitante_id': t.solicitante_id,
        'asignado_a': _nombre(t.asignado_a), 'asignado_a_id': t.asignado_a_id,
        'fecha_recepcion': _iso(t.fecha_recepcion),
        'fecha_seguimiento': _iso(t.fecha_seguimiento),
        'fecha_resolucion': _iso(t.fecha_resolucion),
        'fecha_cierre': _iso(t.fecha_cierre),
        'actualizado_en': _iso(t.actualizado_en),
        'dias_transcurridos': t.dias_transcurridos,
        'dias_resolucion': t.dias_resolucion,
        'seguimiento_vencido': t.seguimiento_vencido,
    }


def _catalogos():
    return {
        'tipos': [{'value': v, 'label': l} for v, l in Ticket.Tipo.choices],
        'prioridades': [{'value': v, 'label': l} for v, l in Ticket.Prioridad.choices],
        'estados': [{'value': v, 'label': l} for v, l in Ticket.Estado.choices],
        # Los que soporte puede asignar (cerrar y cancelar le tocan al solicitante)
        'estados_soporte': [{'value': v, 'label': l} for v, l in Ticket.Estado.choices if v in Ticket.ESTADOS_SOPORTE],
        'modulos': [{'value': v, 'label': l} for v, l in Ticket.Modulo.choices],
    }


def _visibles(user):
    qs = Ticket.objects.select_related('solicitante', 'asignado_a')
    return qs if _puede_atender(user) else qs.filter(solicitante=user)


def _ticket_de(request, pk):
    """El ticket si el usuario puede verlo; si no, 404 (no se revela que existe)."""
    t = _visibles(request.user).filter(pk=pk).first()
    if not t:
        raise ErrorTicket('El ticket no existe o no tienes acceso a él.', status=404)
    return t


def _validar_archivos(archivos):
    if len(archivos) > MAX_ARCHIVOS:
        raise ErrorTicket(f'Puedes adjuntar hasta {MAX_ARCHIVOS} archivos a la vez.')
    for f in archivos:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in EXTENSIONES:
            raise ErrorTicket(f'«{f.name}»: tipo de archivo no permitido.')
        if f.size > MAX_BYTES:
            raise ErrorTicket(f'«{f.name}» pesa más de 10 MB.')


def _guardar_archivos(ticket, archivos, usuario, comentario=None):
    for f in archivos:
        TicketArchivo.objects.create(
            ticket=ticket, comentario=comentario, archivo=f,
            nombre=os.path.basename(f.name)[:255], tamano=f.size, subido_por=usuario,
        )


def _bitacora(ticket, usuario, mensaje):
    TicketComentario.objects.create(ticket=ticket, autor=usuario, tipo=TicketComentario.Tipo.SISTEMA, mensaje=mensaje)


def _cambiar_estado(ticket, nuevo, usuario):
    """Cambia el estado, mantiene las fechas de resolución y cierre y lo deja en la bitácora."""
    if nuevo == ticket.estado:
        return
    anterior = ticket.get_estado_display()
    ticket.estado = nuevo
    ahora = timezone.now()
    if nuevo == Ticket.Estado.RESUELTO:
        ticket.fecha_resolucion = ahora
    elif nuevo in Ticket.ESTADOS_EN_ATENCION:
        ticket.fecha_resolucion = None  # se reabrió: la resolución anterior ya no cuenta
    ticket.fecha_cierre = ahora if nuevo in Ticket.ESTADOS_FINALES else None
    _bitacora(ticket, usuario, f'Estado: {anterior} → {ticket.get_estado_display()}')


def _json(request):
    try:
        return json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise ErrorTicket('Datos no válidos.')


def _con_errores(vista):
    """401 en JSON si no hay sesión, y ErrorTicket -> respuesta JSON con su status."""
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'detail': 'No autenticado.'}, status=401)
        try:
            return vista(request, *args, **kwargs)
        except ErrorTicket as e:
            return JsonResponse({'detail': e.detalle}, status=e.status)
    envoltura.__name__ = vista.__name__
    return envoltura


# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(['GET', 'POST'])
@_con_errores
def tickets(request):
    if request.method == 'POST':
        return _crear(request)

    user = request.user
    atiende = _puede_atender(user)
    p = request.GET
    base = _visibles(user)
    if atiende and p.get('alcance') == 'mios':
        base = base.filter(solicitante=user)

    # Indicadores sobre todo lo visible (sin los filtros de la tabla)
    hoy = timezone.localdate()
    en_atencion = base.filter(estado__in=Ticket.ESTADOS_EN_ATENCION)
    resueltos = base.filter(fecha_resolucion__isnull=False)
    duraciones = [
        (timezone.localdate(s) - timezone.localdate(r)).days
        for r, s in resueltos.order_by('-fecha_resolucion').values_list('fecha_recepcion', 'fecha_resolucion')[:200]
    ]
    resumen = {
        'en_atencion': en_atencion.count(),
        'en_proceso': base.filter(estado=Ticket.Estado.EN_PROCESO).count(),
        'vencidos': en_atencion.filter(fecha_seguimiento__lt=hoy).count(),
        'sin_asignar': en_atencion.filter(asignado_a__isnull=True).count(),
        'por_cerrar': base.filter(estado=Ticket.Estado.RESUELTO).count(),
        'cerrados_30d': base.filter(estado=Ticket.Estado.CERRADO,
                                    fecha_cierre__gte=timezone.now() - datetime.timedelta(days=30)).count(),
        'promedio_dias_resolucion': round(sum(duraciones) / len(duraciones), 1) if duraciones else None,
    }

    qs = base
    estado = p.get('estado', '')
    if estado == 'abiertos':
        qs = qs.exclude(estado__in=Ticket.ESTADOS_FINALES)
    elif estado == 'cerrados':
        qs = qs.filter(estado__in=Ticket.ESTADOS_FINALES)
    elif estado in Ticket.Estado.values:
        qs = qs.filter(estado=estado)
    if p.get('tipo') in Ticket.Tipo.values:
        qs = qs.filter(tipo=p['tipo'])
    if p.get('prioridad') in Ticket.Prioridad.values:
        qs = qs.filter(prioridad=p['prioridad'])
    if p.get('modulo') in Ticket.Modulo.values:
        qs = qs.filter(modulo=p['modulo'])
    if p.get('vencidos') == '1':
        qs = qs.filter(estado__in=Ticket.ESTADOS_EN_ATENCION, fecha_seguimiento__lt=hoy)
    if atiende and p.get('asignado') == 'yo':
        qs = qs.filter(asignado_a=user)
    elif atiende and p.get('asignado') == 'nadie':
        qs = qs.filter(asignado_a__isnull=True)
    q = p.get('q', '').strip()
    if q:
        qs = qs.filter(Q(folio__icontains=q) | Q(titulo__icontains=q) | Q(descripcion__icontains=q))

    orden = p.get('orden', 'recientes')
    if orden == 'antiguos':
        qs = qs.order_by('fecha_recepcion', 'pk')
    elif orden == 'prioridad':
        qs = qs.annotate(_prio=ORDEN_PRIORIDAD).order_by('_prio', 'fecha_recepcion')
    elif orden == 'seguimiento':
        qs = qs.order_by(Case(When(fecha_seguimiento__isnull=True, then=Value(1)), default=Value(0)),
                         'fecha_seguimiento', 'fecha_recepcion')
    else:
        qs = qs.order_by('-fecha_recepcion', '-pk')

    qs = qs.annotate(
        num_archivos=Count('archivos', distinct=True),
        num_comentarios=Count('comentarios', filter=Q(comentarios__tipo=TicketComentario.Tipo.COMENTARIO), distinct=True),
    )
    try:
        page = max(1, int(p.get('page', 1)))
        page_size = min(100, max(1, int(p.get('page_size', 20))))
    except ValueError:
        page, page_size = 1, 20
    total = qs.count()
    filas = qs[(page - 1) * page_size: page * page_size]

    results = []
    for t in filas:
        d = _ticket_dict(t)
        d['num_archivos'] = t.num_archivos
        d['num_comentarios'] = t.num_comentarios
        results.append(d)

    return JsonResponse({
        'results': results, 'count': total, 'page': page, 'page_size': page_size,
        'resumen': resumen, 'puede_atender': atiende, 'catalogos': _catalogos(),
    })


def _crear(request):
    d = request.POST
    titulo = (d.get('titulo') or '').strip()
    descripcion = (d.get('descripcion') or '').strip()
    if not titulo:
        raise ErrorTicket('Escribe un asunto para el ticket.')
    if len(titulo) > 150:
        raise ErrorTicket('El asunto no puede pasar de 150 caracteres.')
    if len(descripcion) < 10:
        raise ErrorTicket('Describe la solicitud con al menos 10 caracteres.')
    tipo = d.get('tipo') if d.get('tipo') in Ticket.Tipo.values else Ticket.Tipo.OTRO
    prioridad = d.get('prioridad') if d.get('prioridad') in Ticket.Prioridad.values else Ticket.Prioridad.MEDIA
    modulo = d.get('modulo') if d.get('modulo') in Ticket.Modulo.values else Ticket.Modulo.GENERAL
    archivos = request.FILES.getlist('archivos')
    _validar_archivos(archivos)

    with transaction.atomic():
        t = Ticket.objects.create(
            tipo=tipo, prioridad=prioridad, modulo=modulo, titulo=titulo,
            descripcion=descripcion, solicitante=request.user,
        )
        t.asignar_folio()
        _bitacora(t, request.user, f'Ticket recibido: {t.get_tipo_display()} · prioridad {t.get_prioridad_display()}.')
        _guardar_archivos(t, archivos, request.user)
    return JsonResponse(_ticket_dict(t), status=201)


@require_http_methods(['GET'])
@_con_errores
def ticket_detalle(request, pk):
    t = _ticket_de(request, pk)
    atiende = _puede_atender(request.user)
    archivos = list(t.archivos.select_related('subido_por'))
    comentarios = []
    for c in t.comentarios.select_related('autor'):
        comentarios.append({
            'id': c.id, 'tipo': c.tipo, 'mensaje': c.mensaje,
            'autor': _nombre(c.autor) or 'Sistema',
            'autor_es_solicitante': bool(c.autor_id and c.autor_id == t.solicitante_id),
            'creado_en': _iso(c.creado_en),
            'archivos': [_archivo_dict(request, a) for a in archivos if a.comentario_id == c.id],
        })
    data = _ticket_dict(t)
    data.update({
        'descripcion': t.descripcion,
        'archivos': [_archivo_dict(request, a) for a in archivos if a.comentario_id is None],
        'comentarios': comentarios,
        'permisos': {
            'atender': atiende,
            'es_solicitante': t.solicitante_id == request.user.id,
            'comentar': atiende or t.solicitante_id == request.user.id,
        },
        'catalogos': _catalogos(),
    })
    if atiende:
        responsables = (User.objects.filter(is_active=True)
                        .filter(Q(is_staff=True) | Q(is_superuser=True)
                                | Q(user_permissions__codename='atender_tickets')
                                | Q(groups__permissions__codename='atender_tickets'))
                        .distinct().order_by('first_name', 'username'))
        data['responsables'] = [{'id': u.id, 'nombre': _nombre(u)} for u in responsables]
    return JsonResponse(data)


@require_http_methods(['POST'])
@_con_errores
def ticket_comentar(request, pk):
    t = _ticket_de(request, pk)
    atiende = _puede_atender(request.user)
    if not (atiende or t.solicitante_id == request.user.id):
        raise ErrorTicket('No puedes comentar este ticket.', status=403)
    if not t.abierto and not atiende:
        raise ErrorTicket('El ticket ya está cerrado.', status=403)
    mensaje = (request.POST.get('mensaje') or '').strip()
    archivos = request.FILES.getlist('archivos')
    if not mensaje and not archivos:
        raise ErrorTicket('Escribe un mensaje o adjunta un archivo.')
    _validar_archivos(archivos)

    with transaction.atomic():
        c = TicketComentario.objects.create(ticket=t, autor=request.user, mensaje=mensaje)
        _guardar_archivos(t, archivos, request.user, comentario=c)
        # Si se esperaba información del solicitante y ya respondió, vuelve a revisión.
        if t.estado == Ticket.Estado.EN_ESPERA and t.solicitante_id == request.user.id:
            _cambiar_estado(t, Ticket.Estado.EN_REVISION, request.user)
        t.save()  # actualiza "actualizado_en" (y el estado, si cambió)
    return JsonResponse({'ok': True, 'id': c.id}, status=201)


@require_http_methods(['POST'])
@_con_errores
def ticket_actualizar(request, pk):
    t = _ticket_de(request, pk)
    d = _json(request)
    user = request.user

    with transaction.atomic():
        accion = d.get('accion')
        if accion:
            # Acciones del solicitante: él confirma y cierra el ticket (o lo reabre o cancela).
            if t.solicitante_id != user.id:
                raise ErrorTicket('Solo quien levantó el ticket puede cerrarlo, reabrirlo o cancelarlo.', status=403)
            if accion == 'cerrar' and t.estado == Ticket.Estado.RESUELTO:
                _cambiar_estado(t, Ticket.Estado.CERRADO, user)
            elif accion == 'reabrir' and t.estado == Ticket.Estado.RESUELTO:
                _cambiar_estado(t, Ticket.Estado.EN_REVISION, user)
            elif accion == 'cancelar' and t.en_atencion:
                _cambiar_estado(t, Ticket.Estado.CANCELADO, user)
            else:
                raise ErrorTicket('Esta acción no está disponible para el ticket.', status=403)
        elif _puede_atender(user):
            if t.estado in (Ticket.Estado.CERRADO, Ticket.Estado.CANCELADO):
                raise ErrorTicket(f'El ticket ya está {t.get_estado_display().lower()}.', status=403)
            if 'estado' in d and d['estado'] != t.estado:
                if d['estado'] in (Ticket.Estado.CERRADO, Ticket.Estado.CANCELADO):
                    raise ErrorTicket('Cerrar o cancelar el ticket le corresponde a quien lo levantó. '
                                      'Márcalo como «Resuelto» para que lo confirme.', status=403)
                if d['estado'] not in Ticket.ESTADOS_SOPORTE:
                    raise ErrorTicket('Estado no válido.')
                _cambiar_estado(t, d['estado'], user)
            if 'prioridad' in d and d['prioridad'] != t.prioridad:
                if d['prioridad'] not in Ticket.Prioridad.values:
                    raise ErrorTicket('Prioridad no válida.')
                anterior = t.get_prioridad_display()
                t.prioridad = d['prioridad']
                _bitacora(t, user, f'Prioridad: {anterior} → {t.get_prioridad_display()}')
            if 'asignado_a' in d:
                nuevo = d['asignado_a'] or None
                if nuevo != t.asignado_a_id:
                    responsable = User.objects.filter(pk=nuevo, is_active=True).first() if nuevo else None
                    if nuevo and not responsable:
                        raise ErrorTicket('El responsable no existe.')
                    anterior = _nombre(t.asignado_a) or 'Sin asignar'
                    t.asignado_a = responsable
                    _bitacora(t, user, f'Responsable: {anterior} → {_nombre(responsable) or "Sin asignar"}')
            if 'fecha_seguimiento' in d:
                valor = d['fecha_seguimiento'] or None
                try:
                    nueva = datetime.date.fromisoformat(valor) if valor else None
                except ValueError:
                    raise ErrorTicket('Fecha de seguimiento no válida.')
                if nueva != t.fecha_seguimiento:
                    t.fecha_seguimiento = nueva
                    texto = nueva.strftime('%d/%m/%Y') if nueva else 'sin fecha'
                    _bitacora(t, user, f'Fecha de seguimiento: {texto}')
        else:
            raise ErrorTicket('No puedes modificar este ticket.', status=403)
        t.save()

    return JsonResponse(_ticket_dict(t))
