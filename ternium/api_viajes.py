"""
API endpoints para el módulo de Viajes / Carta de Traslado.
"""
import json
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q

from .models import Viaje, ItinerarioParada, ViajeMercancia, Unidad, Lugar, Empresa


def _require_auth(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'No autenticado'}, status=401)
    return None


def _empleado_lite(emp):
    return {
        'id': str(emp.id),
        'nombre': emp.nombre_completo,
        'rfc': getattr(emp, 'rfc', '') or '',
        'numero_licencia': getattr(emp, 'numero_licencia', '') or getattr(emp, 'licencia', '') or '',
    }


def _unidad_lite(u):
    return {
        'id': u.id,
        'internal_id': u.internal_id,
        'license_plate': u.license_plate or '',
        'make_model': u.make_model or '',
        'year': u.year,
        'asset_type': u.asset_type,
        'permiso_sct': u.permiso_sct or '',
        'no_permiso_sct': u.no_permiso_sct or '',
        'nombre_aseguradora': u.nombre_aseguradora or '',
        'no_poliza_seguro': u.no_poliza_seguro or '',
        'eco_remolque_1': u.eco_remolque_1 or '',
        'placa_remolque_1': u.placa_remolque_1 or '',
        'eco_remolque_2': u.eco_remolque_2 or '',
        'placa_remolque_2': u.placa_remolque_2 or '',
    }


def _lugar_lite(l):
    return {
        'id': l.id,
        'id_ubicacion': l.id_ubicacion or '',
        'nombre': l.nombre,
        'tipo': l.tipo,
        'rfc': l.rfc or '',
        'codigo_postal': l.codigo_postal or '',
        'direccion': l.direccion_completa(),
        'municipio': l.municipio or '',
        'estado': l.estado or '',
    }


def _parada_dict(p, rol=None):
    """
    rol = 'ORIGEN' | 'DESTINO' | None
    Si se pasa rol, el id_ubicacion se fuerza a ORnnnnnn / DEnnnnnn según el rol,
    independientemente del tipo registrado en el Lugar maestro.
    """
    base_code = p.lugar.id_ubicacion or ''
    if rol == 'ORIGEN' and base_code:
        # Tomamos los dígitos del id_ubicacion del maestro
        numeric = ''.join(ch for ch in base_code if ch.isdigit())
        codigo_role = f"OR{(numeric or str(p.lugar_id)).zfill(6)}"
    elif rol == 'DESTINO' and base_code:
        numeric = ''.join(ch for ch in base_code if ch.isdigit())
        codigo_role = f"DE{(numeric or str(p.lugar_id)).zfill(6)}"
    else:
        codigo_role = base_code
    return {
        'id': p.id,
        'orden': p.orden,
        'rol': rol or '',
        'lugar_id': p.lugar_id,
        'id_ubicacion': codigo_role,
        'id_ubicacion_master': base_code,
        'destino': p.lugar.nombre,
        'direccion': p.lugar.direccion_completa(),
        'codigo_postal': p.lugar.codigo_postal or '',
        'calle': p.lugar.calle or '',
        'numero_exterior': p.lugar.numero_exterior or '',
        'numero_interior': p.lugar.numero_interior or '',
        'colonia': p.lugar.colonia or '',
        'municipio': p.lugar.municipio or '',
        'estado': p.lugar.estado or '',
        'pais': p.lugar.pais or 'México',
        'rfc': p.lugar.rfc or '',
        'fecha_hora': p.fecha_hora.isoformat() if p.fecha_hora else '',
        'kms': str(p.kms or 0),
        'observaciones': p.observaciones or '',
    }


def _mercancia_dict(m, codigos_por_parada=None):
    """
    codigos_por_parada: dict {parada_id: codigo_role}
    Si se pasa, se prioriza ese código sobre el id_ubicacion del Lugar maestro.
    Eso asegura que el origen/destino del tramo se muestre como ORnnnnnn / DEnnnnnn.
    """
    cp = codigos_por_parada or {}
    origen_code = cp.get(m.parada_origen_id) if m.parada_origen_id else None
    destino_code = cp.get(m.parada_destino_id) if m.parada_destino_id else None
    if not origen_code and m.parada_origen and m.parada_origen.lugar:
        origen_code = m.parada_origen.lugar.id_ubicacion or ''
    if not destino_code and m.parada_destino and m.parada_destino.lugar:
        destino_code = m.parada_destino.lugar.id_ubicacion or ''
    return {
        'id': m.id,
        'parada_origen_id': m.parada_origen_id,
        'parada_destino_id': m.parada_destino_id,
        'origen_codigo': origen_code or '',
        'destino_codigo': destino_code or '',
        'clave_producto': m.clave_producto or '',
        'descripcion': m.descripcion,
        'cantidad': str(m.cantidad),
        'peso_kg': str(m.peso_kg),
        'unidad_medida': m.unidad_medida or 'H87',
        'material_peligroso': m.material_peligroso,
        'notas': m.notas or '',
    }


def _role_code(lugar, prefix):
    """Convierte el id_ubicacion del lugar maestro al rol del viaje (OR/DE)."""
    if not lugar:
        return ''
    base = lugar.id_ubicacion or ''
    if not base:
        return ''
    numeric = ''.join(ch for ch in base if ch.isdigit())
    if not numeric:
        numeric = str(getattr(lugar, 'id', 0))
    return f"{prefix}{numeric.zfill(6)}"


def _viaje_dict(v, full=False):
    base = {
        'id': v.id,
        'numero_viaje': v.numero_viaje or v.id,
        'id_viaje': v.id_viaje,
        'folio_carga': v.folio_carga or '',
        'fecha_viaje': str(v.fecha_viaje) if v.fecha_viaje else '',
        'operador_id': str(v.operador_id),
        'operador': v.operador.nombre_completo if v.operador_id else '',
        'unidad_id': v.unidad_id,
        'unidad': f"{v.unidad.internal_id} ({v.unidad.license_plate or 'S/P'})" if v.unidad_id else '',
        'origen_id': v.origen_id,
        'origen': v.origen.nombre if v.origen_id else '',
        'origen_codigo': _role_code(v.origen, 'OR') if v.origen_id else '',
        'destino_id': v.destino_id,
        'destino': v.destino.nombre if v.destino_id else '',
        'destino_codigo': _role_code(v.destino, 'DE') if v.destino_id else '',
        'empresa_id': v.empresa_id,
        'empresa': v.empresa.nombre if v.empresa_id else '',
        'estado': v.estado,
        'observaciones': v.observaciones or '',
        'sueldo_operador': str(v.sueldo_operador or 0),
        'mismo_origen_destino': v.mismo_origen_destino,
        'creado_en': v.creado_en.isoformat() if v.creado_en else '',
        'kms_totales': str(v.kms_totales),
    }
    if full:
        base['unidad_data'] = _unidad_lite(v.unidad)
        base['operador_data'] = _empleado_lite(v.operador)
        base['origen_data'] = _lugar_lite(v.origen)
        base['destino_data'] = _lugar_lite(v.destino)
        base['empresa_data'] = {
            'id': v.empresa.id, 'nombre': v.empresa.nombre,
            'rfc': getattr(v.empresa, 'rfc', '') or '',
            'direccion': getattr(v.empresa, 'direccion', '') or '',
        } if v.empresa_id else None
        # Compute rol por parada: 1ra = ORIGEN, última = DESTINO, intermedias = None
        paradas_list = list(v.paradas.all())
        paradas_dicts = []
        codigos_por_parada = {}
        for idx, p in enumerate(paradas_list):
            if idx == 0:
                rol = 'ORIGEN'
            elif idx == len(paradas_list) - 1:
                rol = 'DESTINO'
            else:
                rol = None
            d = _parada_dict(p, rol=rol)
            codigos_por_parada[p.id] = d['id_ubicacion']
            paradas_dicts.append(d)
        base['paradas'] = paradas_dicts
        # Las mercancías heredan el código del rol de su parada origen/destino del viaje
        base['mercancias'] = [_mercancia_dict(m, codigos_por_parada) for m in v.mercancias.all()]
    return base


# ─── Operadores (filtrado por puesto OPERADOR) ────────────────────────────────

@require_GET
def api_operadores(request):
    """GET /ternium/api/operadores/?search=  — empleados con puesto que contenga 'OPERADOR'."""
    err = _require_auth(request)
    if err:
        return err
    from RH.models import Empleado
    qs = Empleado.objects.filter(activo=True, puesto__nombre__icontains='OPERADOR').select_related('puesto')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(nombre__icontains=search) | Q(apellido__icontains=search))
    qs = qs.order_by('apellido', 'nombre')[:200]
    return JsonResponse({'results': [_empleado_lite(e) for e in qs]})


# ─── Viajes ───────────────────────────────────────────────────────────────────

@require_GET
def api_viajes_list(request):
    """GET /ternium/api/viajes/?search=&estado=&page=&page_size="""
    err = _require_auth(request)
    if err:
        return err
    qs = Viaje.objects.select_related('operador', 'unidad', 'origen', 'destino', 'empresa').order_by('-fecha_viaje', '-creado_en')
    estado = request.GET.get('estado', '')
    if estado:
        qs = qs.filter(estado=estado.upper())
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(id_viaje__icontains=search) |
            Q(folio_carga__icontains=search) |
            Q(operador__nombre__icontains=search) |
            Q(operador__apellido__icontains=search) |
            Q(unidad__internal_id__icontains=search)
        )
    try:
        page_size = min(int(request.GET.get('page_size', 20)), 100)
        page = max(int(request.GET.get('page', 1)), 1)
    except ValueError:
        page_size, page = 20, 1
    total = qs.count()
    offset = (page - 1) * page_size
    return JsonResponse({
        'count': total,
        'results': [_viaje_dict(v) for v in qs[offset:offset + page_size]],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_viaje_crear(request):
    """POST /ternium/api/viajes/crear/"""
    err = _require_auth(request)
    if err:
        return err
    try:
        try:
            body = json.loads(request.body or '{}')
        except ValueError:
            body = dict(request.POST.items())

        fecha_str = (body.get('fecha_viaje') or '').strip()
        if not fecha_str:
            return JsonResponse({'error': 'Falta la fecha del viaje.'}, status=400)
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Formato de fecha inválido (AAAA-MM-DD).'}, status=400)

        from RH.models import Empleado
        operador_id = body.get('operador_id')
        unidad_id = body.get('unidad_id')
        origen_id = body.get('origen_id')
        destino_id = body.get('destino_id')
        if not (operador_id and unidad_id and origen_id and destino_id):
            return JsonResponse({'error': 'Operador, Unidad, Origen y Destino son obligatorios.'}, status=400)

        operador = get_object_or_404(Empleado, pk=operador_id)
        unidad = get_object_or_404(Unidad, pk=unidad_id)
        origen = get_object_or_404(Lugar, pk=origen_id)
        destino = get_object_or_404(Lugar, pk=destino_id)
        empresa = None
        empresa_id = body.get('empresa_id')
        if empresa_id:
            try:
                empresa = Empresa.objects.get(pk=empresa_id)
            except Empresa.DoesNotExist:
                empresa = None

        with transaction.atomic():
            v = Viaje.objects.create(
                fecha_viaje=fecha,
                folio_carga=(body.get('folio_carga') or '').strip() or None,
                operador=operador,
                unidad=unidad,
                origen=origen,
                destino=destino,
                empresa=empresa,
                estado=body.get('estado', 'PLANIFICADO'),
                observaciones=(body.get('observaciones') or '').strip() or None,
                creado_por=request.user if request.user.is_authenticated else None,
            )
            # Paradas iniciales: origen (orden 1) y destino (orden 2)
            ItinerarioParada.objects.create(viaje=v, lugar=origen, orden=1, kms=0)
            ItinerarioParada.objects.create(viaje=v, lugar=destino, orden=2, kms=0)
        return JsonResponse(_viaje_dict(v, full=True), status=201)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'{type(exc).__name__}: {exc}'}, status=400)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_viaje_detail(request, pk):
    err = _require_auth(request)
    if err:
        return err
    v = get_object_or_404(
        Viaje.objects.select_related('operador', 'unidad', 'origen', 'destino', 'empresa').prefetch_related('paradas__lugar', 'mercancias'),
        pk=pk,
    )
    if request.method == 'GET':
        return JsonResponse(_viaje_dict(v, full=True))
    if request.method == 'DELETE':
        v.delete()
        return JsonResponse({'ok': True})
    # PATCH
    try:
        try:
            body = json.loads(request.body or '{}')
        except ValueError:
            body = dict(request.POST.items())
        for k in ('folio_carga', 'observaciones', 'estado'):
            if k in body:
                setattr(v, k, (body[k] or '').strip() or (None if k != 'estado' else v.estado))
        if 'fecha_viaje' in body and body['fecha_viaje']:
            try:
                v.fecha_viaje = datetime.strptime(body['fecha_viaje'], '%Y-%m-%d').date()
            except ValueError:
                pass
        if 'sueldo_operador' in body:
            try:
                v.sueldo_operador = Decimal(str(body['sueldo_operador'] or '0'))
            except Exception:
                v.sueldo_operador = Decimal('0')
        # Permitir actualizar origen / destino (FK Lugar)
        if 'origen_id' in body and body['origen_id']:
            try:
                v.origen_id = int(body['origen_id'])
            except (ValueError, TypeError):
                pass
        if 'destino_id' in body and body['destino_id']:
            try:
                v.destino_id = int(body['destino_id'])
            except (ValueError, TypeError):
                pass
        # Permitir cambiar operador (FK RH.Empleado) y unidad (FK Unidad)
        if 'operador_id' in body and body['operador_id']:
            try:
                from RH.models import Empleado
                v.operador = Empleado.objects.get(pk=body['operador_id'])
            except Empleado.DoesNotExist:
                pass
        if 'unidad_id' in body and body['unidad_id']:
            try:
                v.unidad_id = int(body['unidad_id'])
            except (ValueError, TypeError):
                pass
        v.save()
        return JsonResponse(_viaje_dict(v, full=True))
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)


# ─── Itinerario (paradas) ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_parada_crear(request, viaje_id):
    """POST /ternium/api/viajes/<viaje_id>/paradas/"""
    err = _require_auth(request)
    if err:
        return err
    v = get_object_or_404(Viaje, pk=viaje_id)
    try:
        body = json.loads(request.body or '{}')
    except ValueError:
        body = {}
    lugar_id = body.get('lugar_id')
    if not lugar_id:
        return JsonResponse({'error': 'Falta lugar_id'}, status=400)
    lugar = get_object_or_404(Lugar, pk=lugar_id)
    fecha_hora = None
    if body.get('fecha_hora'):
        try:
            fecha_hora = datetime.fromisoformat(body['fecha_hora'].replace('Z', '+00:00'))
        except ValueError:
            fecha_hora = None
    try:
        kms = Decimal(str(body.get('kms') or 0))
    except (InvalidOperation, TypeError):
        kms = Decimal(0)
    next_orden = (v.paradas.count() + 1)
    try:
        next_orden = int(body.get('orden') or next_orden)
    except (ValueError, TypeError):
        pass
    p = ItinerarioParada.objects.create(
        viaje=v, lugar=lugar, orden=next_orden,
        fecha_hora=fecha_hora, kms=kms,
        observaciones=(body.get('observaciones') or '').strip() or None,
    )
    return JsonResponse(_parada_dict(p), status=201)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
def api_parada_detail(request, pk):
    err = _require_auth(request)
    if err:
        return err
    p = get_object_or_404(ItinerarioParada.objects.select_related('lugar', 'viaje'), pk=pk)
    if request.method == 'DELETE':
        p.delete()
        return JsonResponse({'ok': True})
    try:
        body = json.loads(request.body or '{}')
    except ValueError:
        body = {}
    if 'lugar_id' in body:
        try:
            p.lugar = Lugar.objects.get(pk=body['lugar_id'])
        except Lugar.DoesNotExist:
            pass
    if 'orden' in body:
        try: p.orden = int(body['orden'])
        except (ValueError, TypeError): pass
    if 'kms' in body:
        try: p.kms = Decimal(str(body['kms']))
        except (InvalidOperation, TypeError): pass
    if 'fecha_hora' in body:
        try:
            p.fecha_hora = datetime.fromisoformat((body['fecha_hora'] or '').replace('Z', '+00:00')) if body['fecha_hora'] else None
        except ValueError:
            pass
    if 'observaciones' in body:
        p.observaciones = (body['observaciones'] or '').strip() or None
    p.save()
    return JsonResponse(_parada_dict(p))


# ─── Mercancías ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_mercancia_crear(request, viaje_id):
    """POST /ternium/api/viajes/<viaje_id>/mercancias/"""
    err = _require_auth(request)
    if err:
        return err
    v = get_object_or_404(Viaje, pk=viaje_id)
    try:
        body = json.loads(request.body or '{}')
    except ValueError:
        body = {}
    descripcion = (body.get('descripcion') or '').strip()
    if not descripcion:
        return JsonResponse({'error': 'La descripción es obligatoria.'}, status=400)
    try:
        cantidad = Decimal(str(body.get('cantidad') or 1))
        peso = Decimal(str(body.get('peso_kg') or 0))
    except (InvalidOperation, TypeError):
        return JsonResponse({'error': 'Cantidad o peso inválidos.'}, status=400)

    m = ViajeMercancia.objects.create(
        viaje=v,
        parada_origen_id=body.get('parada_origen_id') or None,
        parada_destino_id=body.get('parada_destino_id') or None,
        clave_producto=(body.get('clave_producto') or '').strip() or None,
        descripcion=descripcion,
        cantidad=cantidad, peso_kg=peso,
        unidad_medida=(body.get('unidad_medida') or 'H87'),
        material_peligroso=bool(body.get('material_peligroso')),
        notas=(body.get('notas') or '').strip() or None,
    )
    return JsonResponse(_mercancia_dict(m), status=201)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
def api_mercancia_detail(request, pk):
    err = _require_auth(request)
    if err:
        return err
    m = get_object_or_404(ViajeMercancia, pk=pk)
    if request.method == 'DELETE':
        m.delete()
        return JsonResponse({'ok': True})
    try:
        body = json.loads(request.body or '{}')
    except ValueError:
        body = {}
    for k in ('descripcion', 'clave_producto', 'unidad_medida', 'notas'):
        if k in body:
            setattr(m, k, (body[k] or '').strip() or None)
    if 'cantidad' in body:
        try: m.cantidad = Decimal(str(body['cantidad']))
        except (InvalidOperation, TypeError): pass
    if 'peso_kg' in body:
        try: m.peso_kg = Decimal(str(body['peso_kg']))
        except (InvalidOperation, TypeError): pass
    if 'material_peligroso' in body:
        m.material_peligroso = bool(body['material_peligroso'])
    if 'parada_origen_id' in body:
        m.parada_origen_id = body['parada_origen_id'] or None
    if 'parada_destino_id' in body:
        m.parada_destino_id = body['parada_destino_id'] or None
    m.save()
    return JsonResponse(_mercancia_dict(m))


# ─── PDF: Carta de Traslado (sin timbrar) ─────────────────────────────────────

@require_GET
def api_viaje_pdf(request, pk):
    """GET /ternium/api/viajes/<pk>/pdf/ — Devuelve el PDF de la carta de traslado."""
    err = _require_auth(request)
    if err:
        return err
    v = get_object_or_404(
        Viaje.objects.select_related('operador', 'unidad', 'origen', 'destino', 'empresa').prefetch_related('paradas__lugar', 'mercancias'),
        pk=pk,
    )
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether,
        )
    except ImportError:
        return JsonResponse({'error': 'reportlab no está instalado. pip install reportlab'}, status=500)

    import os
    from django.conf import settings as dj_settings

    # Catálogo SAT de unidades para resolver "Medida" (KGM → Kilogramo, H87 → Pieza, etc.)
    try:
        from facturacion.models import CatalogoSAT
        unidades_codes = {m.unidad_medida for m in v.mercancias.all() if m.unidad_medida}
        sat_units = {
            c.clave: c.descripcion
            for c in CatalogoSAT.objects.filter(tipo='ClaveUnidad', clave__in=unidades_codes)
        }
    except Exception:
        sat_units = {}

    # ─── Paleta refinada: blanco / negro / 3 grises armónicos ─────────────
    BRAND        = colors.HexColor('#0a7d3a')   # verde 3R (solo logo / banda fina)
    BRAND_DARK   = colors.HexColor('#075d2c')
    GRAY_BAND    = colors.HexColor('#d4d4d4')   # título de sección
    GRAY_HEADER  = colors.HexColor('#ebebeb')   # header de columnas
    GRAY_LINE    = colors.HexColor('#b8b8b8')   # bordes principales
    GRAY_LINE_LT = colors.HexColor('#d8d8d8')   # bordes internos
    GRAY_LIGHT   = colors.HexColor('#fafafa')   # zebra muy sutil

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=12*mm, rightMargin=12*mm,
        topMargin=10*mm, bottomMargin=14*mm,
        title=f"Carta de Traslado {v.id_viaje}",
        author="3R Recycling",
    )

    # ─── Estilos refinados ─────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    s_micro = ParagraphStyle('micro', parent=styles['Normal'], fontSize=6.5, leading=8.5,
                              fontName='Helvetica', textColor=colors.HexColor('#555555'))
    s_small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8.5, leading=11,
                              fontName='Helvetica', textColor=colors.black)
    s_bold  = ParagraphStyle('bold',  parent=styles['Normal'], fontSize=9, leading=12,
                              fontName='Helvetica-Bold', textColor=colors.black)
    s_section = ParagraphStyle('section', parent=styles['Normal'], fontSize=9.5, leading=12,
                                fontName='Helvetica-Bold', textColor=colors.black, alignment=TA_CENTER)
    # Header de columna con tracking ligero
    s_cellh = ParagraphStyle('cellh', parent=styles['Normal'], fontSize=7, leading=9,
                              fontName='Helvetica-Bold', textColor=colors.black, alignment=TA_CENTER)
    s_cell  = ParagraphStyle('cell',  parent=styles['Normal'], fontSize=8, leading=10,
                              fontName='Helvetica', textColor=colors.black, alignment=TA_LEFT, wordWrap='CJK')
    s_cellc = ParagraphStyle('cellc', parent=styles['Normal'], fontSize=8, leading=10,
                              fontName='Helvetica', textColor=colors.black, alignment=TA_CENTER, wordWrap='CJK')

    story = []

    # ─── Datos de la empresa emisora ──────────────────────────────────────
    empresa_nombre = v.empresa.nombre if v.empresa_id and v.empresa else '3R recycling'
    empresa_rfc = (getattr(v.empresa, 'rfc', '') or 'RRE1801236N0') if v.empresa_id else 'RRE1801236N0'
    empresa_dir_lineas = [
        'GARZA SADA #3921, Col. Contry',
        'CP 64860, Monterrey, Nuevo León, México',
    ]
    if v.empresa_id and v.empresa:
        # Si Empresa tiene un campo direccion, lo usamos
        dir_emp = getattr(v.empresa, 'direccion', '')
        if dir_emp:
            empresa_dir_lineas = [dir_emp]

    # ─── Header refinado: logo + empresa centrada + bloque derecho ─────────
    logo_path = os.path.join(dj_settings.BASE_DIR, 'static', 'r3_recycling', 'img', 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=32*mm, height=32*mm)
            logo.hAlign = 'CENTER'
        except Exception:
            logo = Spacer(32*mm, 32*mm)
    else:
        logo = Spacer(32*mm, 32*mm)

    # Bloque central: nombre grande, RFC en mono, dirección en gris suave
    empresa_block = Paragraph(
        f'<para align="center" leading="14">'
        f'<font color="#000000" size="16"><b>{empresa_nombre}</b></font><br/>'
        f'<font color="#555555" size="8"><b>RFC:</b> {empresa_rfc}</font><br/>'
        f'<font color="#000000" size="8.5">{"<br/>".join(empresa_dir_lineas)}</font>'
        f'</para>',
        s_small
    )

    # Bloque derecho: 4 grupos etiqueta-valor con tipografía mejorada
    folio_display = f"{v.folio_carga}" if v.folio_carga else (v.id_viaje or '')
    fmt_fecha = ''
    if v.fecha_viaje:
        try:
            fmt_fecha = v.fecha_viaje.strftime('%d / %m / %Y')
        except Exception:
            fmt_fecha = str(v.fecha_viaje)
    label_st = ParagraphStyle('hl', parent=s_cellc, fontSize=7, leading=8.5,
                               fontName='Helvetica-Bold', textColor=colors.HexColor('#444444'))
    value_st = ParagraphStyle('hv', parent=s_cellc, fontSize=10, leading=12,
                               fontName='Helvetica-Bold', textColor=colors.black)
    doc_block_data = [
        [Paragraph('CARTA DE TRASLADO', label_st)],
        [Paragraph(folio_display or '—', value_st)],
        [Paragraph('FECHA', label_st)],
        [Paragraph(fmt_fecha or '—', value_st)],
        [Paragraph('FOLIO DE CARGA', label_st)],
        [Paragraph(v.folio_carga or '—', value_st)],
        [Paragraph('VIAJE', label_st)],
        [Paragraph(str(v.numero_viaje or v.id), value_st)],
    ]
    doc_block = Table(doc_block_data, colWidths=[52*mm])
    doc_block.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), GRAY_HEADER),
        ('BACKGROUND', (0,2), (-1,2), GRAY_HEADER),
        ('BACKGROUND', (0,4), (-1,4), GRAY_HEADER),
        ('BACKGROUND', (0,6), (-1,6), GRAY_HEADER),
        ('BOX', (0,0), (-1,-1), 0.5, GRAY_LINE),
        ('LINEBELOW', (0,0), (-1,-2), 0.25, GRAY_LINE_LT),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))

    head = Table([[logo, empresa_block, doc_block]], colWidths=[40*mm, 94*mm, 52*mm])
    head.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(head)
    # Línea divisoria sutil bajo el header
    divider = Table([['']], colWidths=[186*mm], rowHeights=[0.4])
    divider.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), GRAY_LINE)]))
    story.append(Spacer(1, 4))
    story.append(divider)
    story.append(Spacer(1, 6))

    # ─── Helper: título de sección centrado en gris (más alto, mejor jerarquía)
    PAGE_W = 186*mm
    def section_title(text):
        t = Table([[Paragraph(text, s_section)]], colWidths=[PAGE_W])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), GRAY_BAND),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, GRAY_LINE),
            ('LINEABOVE', (0,0), (-1,-1), 0.5, GRAY_LINE),
            ('LINEBEFORE', (0,0), (-1,-1), 0.5, GRAY_LINE),
            ('LINEAFTER', (0,0), (-1,-1), 0.5, GRAY_LINE),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        return t

    # ─── Helper: estilo de tabla con encabezado gris + zebra suave ────────
    def table_style_v2(num_cols):
        return TableStyle([
            # Header
            ('BACKGROUND', (0,0), (-1,0), GRAY_HEADER),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 7),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('VALIGN', (0,0), (-1,0), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,0), 6),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('LINEBELOW', (0,0), (-1,0), 0.5, GRAY_LINE),
            # Filas de datos
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
            ('VALIGN', (0,1), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,1), (-1,-1), 5),
            ('BOTTOMPADDING', (0,1), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            # Bordes
            ('BOX', (0,0), (-1,-1), 0.5, GRAY_LINE),
            ('INNERGRID', (0,0), (-1,-1), 0.25, GRAY_LINE_LT),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GRAY_LIGHT]),
        ])

    # ─── Cliente ──────────────────────────────────────────────────────────
    story.append(section_title('Cliente'))
    cli = Table([
        [Paragraph('Razón Social', s_cellh), Paragraph('RFC', s_cellh), Paragraph('Dirección', s_cellh)],
        [Paragraph(empresa_nombre, s_cell), Paragraph(empresa_rfc, s_cellc), Paragraph(', '.join(empresa_dir_lineas), s_cell)],
    ], colWidths=[40*mm, 30*mm, 116*mm])
    cli.setStyle(table_style_v2(3))
    story.append(cli)

    # ─── Autotransporte Federal (9 columnas, sin Remolque 2) ──────────────
    story.append(section_title('Autotransporte Federal'))
    u = v.unidad
    auto = Table([
        [
            Paragraph('Económico', s_cellh),
            Paragraph('Placa VM', s_cellh),
            Paragraph('Permiso SCT', s_cellh),
            Paragraph('No. Permiso SCT', s_cellh),
            Paragraph('Nombre Aseguradora', s_cellh),
            Paragraph('No. Póliza Seguro', s_cellh),
            Paragraph('Año Modelo VM', s_cellh),
            Paragraph('Eco. Remolque 1', s_cellh),
            Paragraph('Placa Remolque 1', s_cellh),
        ],
        [
            Paragraph(u.internal_id or '', s_cellc),
            Paragraph(u.license_plate or '', s_cellc),
            Paragraph(u.permiso_sct or '', s_cellc),
            Paragraph(u.no_permiso_sct or '', s_cellc),
            Paragraph(u.nombre_aseguradora or '', s_cellc),
            Paragraph(u.no_poliza_seguro or '', s_cellc),
            Paragraph(str(u.year or ''), s_cellc),
            Paragraph(u.eco_remolque_1 or '', s_cellc),
            Paragraph(u.placa_remolque_1 or '', s_cellc),
        ],
    ], colWidths=[18*mm, 18*mm, 20*mm, 23*mm, 28*mm, 23*mm, 20*mm, 19*mm, 17*mm], repeatRows=1)
    auto.setStyle(table_style_v2(9))
    story.append(auto)

    # ─── Figura de Transporte ─────────────────────────────────────────────
    story.append(section_title('Figura de Transporte'))
    op = v.operador
    fig = Table([
        [Paragraph('RFC', s_cellh), Paragraph('Nombre del Operador', s_cellh), Paragraph('No. Licencia', s_cellh)],
        [
            Paragraph(getattr(op, 'rfc', '') or '—', s_cellc),
            Paragraph(op.nombre_completo, s_cell),
            Paragraph(getattr(op, 'numero_licencia', '') or getattr(op, 'licencia', '') or '—', s_cellc),
        ],
    ], colWidths=[40*mm, 110*mm, 36*mm])
    fig.setStyle(table_style_v2(3))
    story.append(fig)

    # ─── Ubicaciones ──────────────────────────────────────────────────────
    story.append(section_title('Ubicaciones'))
    # Recalcular paradas con rol OR/DE
    paradas_list = list(v.paradas.all())
    def role_code_for_idx(idx, total, lugar):
        base = lugar.id_ubicacion or ''
        numeric = ''.join(ch for ch in base if ch.isdigit()) or str(lugar.id)
        if idx == 0:
            return f"OR{numeric.zfill(6)}"
        if idx == total - 1:
            return f"DE{numeric.zfill(6)}"
        return base or numeric
    codigos_por_parada = {}
    ub_rows = [[
        Paragraph('Ubicación', s_cellh),
        Paragraph('RFC', s_cellh),
        Paragraph('Nombre', s_cellh),
        Paragraph('Dirección', s_cellh),
        Paragraph('Fecha / Hora', s_cellh),
    ]]
    for idx, p in enumerate(paradas_list):
        codigo = role_code_for_idx(idx, len(paradas_list), p.lugar)
        codigos_por_parada[p.id] = codigo
        ub_rows.append([
            Paragraph(codigo, s_cellc),
            Paragraph(p.lugar.rfc or '—', s_cellc),
            Paragraph(p.lugar.nombre, s_cell),
            Paragraph(p.lugar.direccion_completa() or '—', s_cell),
            Paragraph(p.fecha_hora.strftime('%d/%m/%Y %H:%M') if p.fecha_hora else '—', s_cellc),
        ])
    ub = Table(ub_rows, colWidths=[22*mm, 28*mm, 48*mm, 62*mm, 26*mm], repeatRows=1)
    ub.setStyle(table_style_v2(5))
    story.append(ub)

    # ─── Mercancia ────────────────────────────────────────────────────────
    story.append(section_title('Mercancía'))
    mc_rows = [
        [
            Paragraph('Clave / Producto', s_cellh),
            Paragraph('Descripción', s_cellh),
            Paragraph('Medida', s_cellh),
            Paragraph('Cantidad', s_cellh),
            Paragraph('Peso (kg)', s_cellh),
            Paragraph('Remitente', s_cellh),
            Paragraph('ID Ubic.', s_cellh),
            Paragraph('Destinatario', s_cellh),
            Paragraph('ID Ubic.', s_cellh),
            Paragraph('KMs', s_cellh),
        ]
    ]
    for m in v.mercancias.all():
        try:
            cant = float(m.cantidad or 0)
            peso = float(m.peso_kg or 0)
        except (TypeError, ValueError):
            cant, peso = 0.0, 0.0
        # Medida: código SAT + descripción del catálogo
        um_code = m.unidad_medida or ''
        um_desc = sat_units.get(um_code, '') if um_code else ''
        medida_text = f"{um_code}- {um_desc}" if um_desc else um_code

        clave_text = f"{m.clave_producto or ''} - {m.descripcion or ''}".strip(' -')
        remitente_nombre = m.parada_origen.lugar.nombre if m.parada_origen and m.parada_origen.lugar else ''
        remitente_id = codigos_por_parada.get(m.parada_origen_id, '') if m.parada_origen_id else ''
        destinatario_nombre = m.parada_destino.lugar.nombre if m.parada_destino and m.parada_destino.lugar else ''
        destinatario_id = codigos_por_parada.get(m.parada_destino_id, '') if m.parada_destino_id else ''
        # Kms: usamos los kms de la parada destino (tramo)
        tramo_kms = 0.0
        if m.parada_destino_id:
            try:
                tramo_kms = float(m.parada_destino.kms or 0)
            except (TypeError, ValueError):
                tramo_kms = 0.0

        mc_rows.append([
            Paragraph(clave_text, s_cell),
            Paragraph(m.descripcion or '', s_cell),
            Paragraph(medida_text, s_cell),
            Paragraph(f'{cant:g}', s_cellc),
            Paragraph(f'{peso:g}', s_cellc),
            Paragraph(remitente_nombre, s_cell),
            Paragraph(remitente_id, s_cellc),
            Paragraph(destinatario_nombre, s_cell),
            Paragraph(destinatario_id, s_cellc),
            Paragraph(f'{tramo_kms:g}', s_cellc),
        ])
    if len(mc_rows) == 1:
        mc_rows.append([Paragraph('—', s_cell)] + [Paragraph('Sin mercancías registradas', s_cell)] + [''] * 8)

    mc = Table(mc_rows, colWidths=[
        22*mm,   # Clave / Producto
        26*mm,   # Descripción
        26*mm,   # Medida (texto SAT)
        12*mm,   # Cantidad
        12*mm,   # Peso (kg)
        18*mm,   # Remitente
        16*mm,   # ID Ubic (fits OR000004 en una línea)
        26*mm,   # Destinatario (fits "PATIO SANTA ROSA")
        16*mm,   # ID Ubic
        12*mm,   # KMs
    ], repeatRows=1)
    mc.setStyle(table_style_v2(10))
    story.append(mc)

    # ─── Observaciones ────────────────────────────────────────────────────
    story.append(section_title('Observaciones'))
    obs_text = v.observaciones if v.observaciones else ''
    obs_table = Table([[Paragraph(obs_text.replace('\n', '<br/>') or '&nbsp;', s_small)]],
                      colWidths=[PAGE_W])
    obs_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.25, GRAY_LINE),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(obs_table)

    # ─── Pie: línea separadora + metadata de generación ───────────────────
    from datetime import datetime as _dt
    story.append(Spacer(1, 10))
    pie_divider = Table([['']], colWidths=[PAGE_W], rowHeights=[0.3])
    pie_divider.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), GRAY_LINE)]))
    story.append(pie_divider)
    story.append(Spacer(1, 3))
    pie = Paragraph(
        f'<para align="center"><font color="#666666" size="6.5">'
        f'<b>3R Recycling</b> · Carta de Traslado interna · Generado el {_dt.now().strftime("%d/%m/%Y a las %H:%M")}'
        f'</font></para>',
        s_micro
    )
    story.append(pie)

    doc.build(story)
    buffer.seek(0)
    resp = HttpResponse(buffer.read(), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="carta-traslado-{v.folio_carga or v.id_viaje}.pdf"'
    return resp
