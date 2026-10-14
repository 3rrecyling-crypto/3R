"""
Panel "Consumo de IA" (solo staff): conversaciones y peticiones de Reportes con
IA, tokens y dinero gastado por usuario. Lee la bitácora RegistroReporteIA.

Los costos se guardan en USD (lo que cobra Anthropic) y se muestran también en
MXN con el tipo de cambio de Configuración (bancos_tc_default).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import RegistroReporteIA

POR_PAGINA = 25
TOKENS = ('tokens_entrada', 'tokens_salida', 'tokens_cache_lectura', 'tokens_cache_escritura')


def _es_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _solo_staff(vista):
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'detail': 'No autenticado.'}, status=401)
        if not _es_staff(request.user):
            return JsonResponse({'detail': 'Solo el personal de staff puede ver el consumo de IA.'}, status=403)
        return vista(request, *args, **kwargs)
    envoltura.__name__ = vista.__name__
    return envoltura


def _tipo_cambio():
    try:
        from api.models import ConfiguracionSistema
        tc = ConfiguracionSistema.get_config().bancos_tc_default
        return Decimal(str(tc)) if tc else Decimal('17')
    except Exception:
        return Decimal('17')


def _fecha(texto, defecto):
    try:
        return dt.date.fromisoformat(str(texto)[:10]) if texto else defecto
    except ValueError:
        return defecto


def _nombre(usuario):
    if not usuario:
        return '(usuario eliminado)'
    return usuario.get_full_name() or usuario.username


def _sumas():
    return {
        'peticiones': Count('id'),
        **{t: Coalesce(Sum(t), 0) for t in TOKENS},
        'costo_usd': Coalesce(Sum('costo_usd'), Decimal('0')),
    }


def _dinero(usd, tc):
    usd = Decimal(usd or 0)
    return {'costo_usd': float(round(usd, 6)), 'costo_mxn': float(round(usd * tc, 4))}


def _registro_dict(r, tc, completo=False):
    datos = {
        'id': r.id,
        'fecha': timezone.localtime(r.creado_en).isoformat(),
        'usuario_id': r.usuario_id,
        'usuario': _nombre(r.usuario),
        'conversacion': r.conversacion,
        'pregunta': r.pregunta if completo else r.pregunta[:240],
        'respuesta': r.respuesta if completo else r.respuesta[:240],
        'motor': r.motor,
        'proveedor': r.proveedor,
        'modelo': r.modelo,
        'num_consultas': r.num_consultas,
        'llamadas_modelo': r.llamadas_modelo,
        **{t: getattr(r, t) for t in TOKENS},
        'tokens_total': sum(getattr(r, t) for t in TOKENS),
        'medido': r.medido,
        'duracion_ms': r.duracion_ms,
        'avisos': r.avisos,
        **_dinero(r.costo_usd, tc),
    }
    if completo:
        datos['consultas'] = r.consultas
    return datos


@require_http_methods(['GET'])
@_solo_staff
def api_consumo_ia(request):
    """GET ?desde&hasta&usuario&q&conversacion&page → totales, por usuario, por día y peticiones."""
    hoy = timezone.localdate()
    desde = _fecha(request.GET.get('desde'), hoy - dt.timedelta(days=29))
    hasta = _fecha(request.GET.get('hasta'), hoy)
    if desde > hasta:
        desde, hasta = hasta, desde
    tc = _tipo_cambio()

    periodo = RegistroReporteIA.objects.filter(creado_en__date__gte=desde, creado_en__date__lte=hasta)

    # Totales del periodo (para todos los usuarios)
    t = periodo.aggregate(**_sumas(), usuarios=Count('usuario', distinct=True),
                          conversaciones=Count('conversacion', distinct=True, filter=~Q(conversacion='')),
                          sin_medir=Count('id', filter=Q(medido=False)))
    totales = {
        'peticiones': t['peticiones'], 'usuarios': t['usuarios'], 'conversaciones': t['conversaciones'],
        **{k: t[k] for k in TOKENS},
        'tokens_total': sum(t[k] for k in TOKENS),
        'sin_medir': t['sin_medir'],
        **_dinero(t['costo_usd'], tc),
        'costo_promedio_usd': float(round(t['costo_usd'] / t['peticiones'], 6)) if t['peticiones'] else 0.0,
    }

    por_usuario = []
    for fila in (periodo.values('usuario', 'usuario__username', 'usuario__first_name', 'usuario__last_name')
                 .annotate(**_sumas(), ultima=Max('creado_en'),
                           conversaciones=Count('conversacion', distinct=True, filter=~Q(conversacion='')))
                 .order_by('-costo_usd', '-peticiones')):
        nombre = ' '.join(x for x in (fila['usuario__first_name'], fila['usuario__last_name']) if x).strip()
        por_usuario.append({
            'usuario_id': fila['usuario'],
            'usuario': nombre or fila['usuario__username'] or '(usuario eliminado)',
            'username': fila['usuario__username'] or '',
            'peticiones': fila['peticiones'], 'conversaciones': fila['conversaciones'],
            **{k: fila[k] for k in TOKENS},
            'tokens_total': sum(fila[k] for k in TOKENS),
            **_dinero(fila['costo_usd'], tc),
            'ultima': timezone.localtime(fila['ultima']).isoformat() if fila['ultima'] else None,
        })

    por_dia = [
        {'dia': f['dia'].isoformat(), 'peticiones': f['peticiones'], **_dinero(f['costo_usd'], tc),
         'tokens_total': sum(f[k] for k in TOKENS)}
        for f in periodo.annotate(dia=TruncDate('creado_en')).values('dia').annotate(**_sumas()).order_by('dia')
    ]

    # Peticiones (con filtros de usuario, conversación y texto)
    registros = periodo.select_related('usuario')
    usuario = request.GET.get('usuario', '')
    if usuario.isdigit():
        registros = registros.filter(usuario_id=int(usuario))
    conversacion = request.GET.get('conversacion', '').strip()
    if conversacion:
        registros = registros.filter(conversacion=conversacion)
    q = ' '.join(request.GET.get('q', '').split())[:100]
    if q:
        registros = registros.filter(Q(pregunta__icontains=q) | Q(respuesta__icontains=q))
    paginas = Paginator(registros.order_by('-creado_en'), POR_PAGINA)
    pagina = paginas.get_page(request.GET.get('page') or 1)

    return JsonResponse({
        'periodo': {'desde': desde.isoformat(), 'hasta': hasta.isoformat()},
        'tipo_cambio': float(tc),
        'totales': totales,
        'por_usuario': por_usuario,
        'por_dia': por_dia,
        'registros': {
            'results': [_registro_dict(r, tc) for r in pagina.object_list],
            'count': paginas.count, 'page': pagina.number, 'pages': paginas.num_pages,
        },
    })


@require_http_methods(['GET'])
@_solo_staff
def api_consumo_ia_detalle(request, pk):
    """Una petición completa (respuesta y consultas) y la conversación a la que pertenece."""
    tc = _tipo_cambio()
    registro = RegistroReporteIA.objects.select_related('usuario').filter(pk=pk).first()
    if not registro:
        return JsonResponse({'detail': 'No existe ese registro.'}, status=404)
    if registro.conversacion:
        hilo = (RegistroReporteIA.objects.select_related('usuario')
                .filter(conversacion=registro.conversacion, usuario_id=registro.usuario_id).order_by('creado_en'))
    else:
        hilo = [registro]
    turnos = [_registro_dict(r, tc, completo=True) for r in hilo]
    return JsonResponse({
        'registro': _registro_dict(registro, tc, completo=True),
        'conversacion': turnos,
        'conversacion_total': _dinero(sum((Decimal(r.costo_usd) for r in hilo), Decimal('0')), tc),
        'tipo_cambio': float(tc),
    })
