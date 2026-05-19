
# =========================================================================
# CATÁLOGOS CRUD API + PERFIL + PERMISOS  (appended to api_views.py)
# =========================================================================
from .models import Profile

def _json_body(request):
    try:
        return json.loads(request.body), None
    except Exception:
        return None, JsonResponse({'error': 'JSON invalido'}, status=400)

def _perm_check(request, perm):
    if request.user.is_superuser:
        return None
    if not request.user.has_perm(perm):
        return JsonResponse({'error': 'FORBIDDEN', 'detail': f'Permiso requerido: {perm}'}, status=403)
    return None

# ── EMPRESAS ─────────────────────────────────────────────────────────────
@csrf_exempt
@login_required
def api_cat_empresas(request):
    if request.method == 'GET':
        qs = Empresa.objects.all().order_by('nombre')
        q = request.GET.get('q', '')
        if q:
            qs = qs.filter(nombre__icontains=q)
        return JsonResponse({'results': [{'id': e.id, 'nombre': e.nombre, 'prefijo': e.prefijo or ''} for e in qs]})
    if request.method == 'POST':
        err = _perm_check(request, 'ternium.add_empresa')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        nombre = body.get('nombre', '').strip()
        prefijo = body.get('prefijo', '').strip().upper()
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        if Empresa.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'error': 'Ya existe una empresa con ese nombre'}, status=400)
        e = Empresa.objects.create(nombre=nombre, prefijo=prefijo or None)
        return JsonResponse({'id': e.id, 'nombre': e.nombre, 'prefijo': e.prefijo or ''}, status=201)
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

@csrf_exempt
@login_required
def api_cat_empresa_detail(request, pk):
    e = get_object_or_404(Empresa, pk=pk)
    if request.method == 'GET':
        return JsonResponse({'id': e.id, 'nombre': e.nombre, 'prefijo': e.prefijo or ''})
    if request.method in ('PUT', 'PATCH'):
        err = _perm_check(request, 'ternium.change_empresa')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        if 'nombre' in body: e.nombre = body['nombre'].strip()
        if 'prefijo' in body: e.prefijo = body['prefijo'].strip().upper() or None
        e.save()
        return JsonResponse({'id': e.id, 'nombre': e.nombre, 'prefijo': e.prefijo or ''})
    if request.method == 'DELETE':
        err = _perm_check(request, 'ternium.delete_empresa')
        if err: return err
        e.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── LUGARES ──────────────────────────────────────────────────────────────
def _lugar_to_dict(l):
    return {'id': l.id, 'nombre': l.nombre, 'tipo': l.tipo, 'es_patio': l.es_patio,
            'rfc': l.rfc or '', 'municipio': l.municipio or '', 'estado': l.estado or ''}

@csrf_exempt
@login_required
def api_cat_lugares(request):
    if request.method == 'GET':
        qs = Lugar.objects.all().order_by('nombre')
        q = request.GET.get('q', '')
        if q: qs = qs.filter(nombre__icontains=q)
        return JsonResponse({'results': [_lugar_to_dict(l) for l in qs]})
    if request.method == 'POST':
        err = _perm_check(request, 'ternium.add_lugar')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        if Lugar.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'error': 'Ya existe un lugar con ese nombre'}, status=400)
        l = Lugar.objects.create(
            nombre=nombre,
            tipo=body.get('tipo', 'DESTINO'),
            es_patio=bool(body.get('es_patio', False)),
            rfc=body.get('rfc', '') or None,
            municipio=body.get('municipio', '') or None,
            estado=body.get('estado', '') or None,
        )
        return JsonResponse(_lugar_to_dict(l), status=201)
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

@csrf_exempt
@login_required
def api_cat_lugar_detail(request, pk):
    l = get_object_or_404(Lugar, pk=pk)
    if request.method == 'GET':
        return JsonResponse(_lugar_to_dict(l))
    if request.method in ('PUT', 'PATCH'):
        err = _perm_check(request, 'ternium.change_lugar')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        for field in ('nombre', 'tipo', 'rfc', 'municipio', 'estado'):
            if field in body: setattr(l, field, body[field])
        if 'es_patio' in body: l.es_patio = bool(body['es_patio'])
        l.save()
        return JsonResponse(_lugar_to_dict(l))
    if request.method == 'DELETE':
        err = _perm_check(request, 'ternium.delete_lugar')
        if err: return err
        l.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── LINEAS DE TRANSPORTE ─────────────────────────────────────────────────
@csrf_exempt
@login_required
def api_cat_lineas(request):
    if request.method == 'GET':
        qs = LineaTransporte.objects.all().order_by('nombre')
        q = request.GET.get('q', '')
        if q: qs = qs.filter(nombre__icontains=q)
        return JsonResponse({'results': [{'id': lt.id, 'nombre': lt.nombre} for lt in qs]})
    if request.method == 'POST':
        err = _perm_check(request, 'ternium.add_lineatransporte')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        if LineaTransporte.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'error': 'Ya existe una linea con ese nombre'}, status=400)
        lt = LineaTransporte.objects.create(nombre=nombre)
        return JsonResponse({'id': lt.id, 'nombre': lt.nombre}, status=201)
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

@csrf_exempt
@login_required
def api_cat_linea_detail(request, pk):
    lt = get_object_or_404(LineaTransporte, pk=pk)
    if request.method == 'GET':
        return JsonResponse({'id': lt.id, 'nombre': lt.nombre})
    if request.method in ('PUT', 'PATCH'):
        err = _perm_check(request, 'ternium.change_lineatransporte')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        if 'nombre' in body: lt.nombre = body['nombre'].strip()
        lt.save()
        return JsonResponse({'id': lt.id, 'nombre': lt.nombre})
    if request.method == 'DELETE':
        err = _perm_check(request, 'ternium.delete_lineatransporte')
        if err: return err
        lt.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── OPERADORES ───────────────────────────────────────────────────────────
@csrf_exempt
@login_required
def api_cat_operadores(request):
    if request.method == 'GET':
        qs = Operador.objects.all().order_by('nombre')
        q = request.GET.get('q', '')
        if q: qs = qs.filter(nombre__icontains=q)
        return JsonResponse({'results': [{'id': o.id, 'nombre': o.nombre, 'folio': o.folio or ''} for o in qs]})
    if request.method == 'POST':
        err = _perm_check(request, 'ternium.add_operador')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        if Operador.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'error': 'Ya existe un operador con ese nombre'}, status=400)
        o = Operador.objects.create(nombre=nombre, folio=body.get('folio', '') or None)
        return JsonResponse({'id': o.id, 'nombre': o.nombre, 'folio': o.folio or ''}, status=201)
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

@csrf_exempt
@login_required
def api_cat_operador_detail(request, pk):
    o = get_object_or_404(Operador, pk=pk)
    if request.method == 'GET':
        return JsonResponse({'id': o.id, 'nombre': o.nombre, 'folio': o.folio or ''})
    if request.method in ('PUT', 'PATCH'):
        err = _perm_check(request, 'ternium.change_operador')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        if 'nombre' in body: o.nombre = body['nombre'].strip()
        if 'folio' in body: o.folio = body['folio'].strip() or None
        o.save()
        return JsonResponse({'id': o.id, 'nombre': o.nombre, 'folio': o.folio or ''})
    if request.method == 'DELETE':
        err = _perm_check(request, 'ternium.delete_operador')
        if err: return err
        o.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── MATERIALES ───────────────────────────────────────────────────────────
@csrf_exempt
@login_required
def api_cat_materiales(request):
    if request.method == 'GET':
        qs = Material.objects.all().order_by('nombre')
        q = request.GET.get('q', '')
        if q: qs = qs.filter(nombre__icontains=q)
        return JsonResponse({'results': [{'id': m.id, 'nombre': m.nombre,
            'clave_sat': m.clave_sat or '', 'clave_unidad_sat': m.clave_unidad_sat or ''} for m in qs]})
    if request.method == 'POST':
        err = _perm_check(request, 'ternium.add_material')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        if Material.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'error': 'Ya existe un material con ese nombre'}, status=400)
        m = Material.objects.create(
            nombre=nombre,
            clave_sat=body.get('clave_sat', '') or None,
            clave_unidad_sat=body.get('clave_unidad_sat', 'KGM') or 'KGM',
        )
        return JsonResponse({'id': m.id, 'nombre': m.nombre,
            'clave_sat': m.clave_sat or '', 'clave_unidad_sat': m.clave_unidad_sat or ''}, status=201)
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

@csrf_exempt
@login_required
def api_cat_material_detail(request, pk):
    m = get_object_or_404(Material, pk=pk)
    if request.method == 'GET':
        return JsonResponse({'id': m.id, 'nombre': m.nombre,
            'clave_sat': m.clave_sat or '', 'clave_unidad_sat': m.clave_unidad_sat or ''})
    if request.method in ('PUT', 'PATCH'):
        err = _perm_check(request, 'ternium.change_material')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        if 'nombre' in body: m.nombre = body['nombre'].strip()
        if 'clave_sat' in body: m.clave_sat = body['clave_sat'].strip() or None
        if 'clave_unidad_sat' in body: m.clave_unidad_sat = body['clave_unidad_sat'].strip() or 'KGM'
        m.save()
        return JsonResponse({'id': m.id, 'nombre': m.nombre,
            'clave_sat': m.clave_sat or '', 'clave_unidad_sat': m.clave_unidad_sat or ''})
    if request.method == 'DELETE':
        err = _perm_check(request, 'ternium.delete_material')
        if err: return err
        m.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── UNIDADES ─────────────────────────────────────────────────────────────
_UNIDAD_TEXT_FIELDS = (
    'internal_id', 'license_plate', 'make_model', 'color', 'vin',
    'asset_type', 'ownership', 'operational_status',
    'insurance_policy', 'circulation_license',
    'permiso_sct', 'no_permiso_sct',
    'nombre_aseguradora', 'no_poliza_seguro',
    'eco_remolque_1', 'placa_remolque_1', 'eco_remolque_2', 'placa_remolque_2',
    'notes',
)
_UNIDAD_DATE_FIELDS = ('acquisition_date', 'insurance_due_date', 'license_due_date')

def _unidad_to_dict(u):
    out = {'id': u.id}
    for f in _UNIDAD_TEXT_FIELDS:
        out[f] = getattr(u, f, None) or ''
    for f in _UNIDAD_DATE_FIELDS:
        v = getattr(u, f, None)
        out[f] = v.isoformat() if v else ''
    out['year'] = u.year or ''
    return out

@csrf_exempt
@login_required
def api_cat_unidades(request):
    if request.method == 'GET':
        qs = Unidad.objects.all().order_by('internal_id')
        q = request.GET.get('q', '')
        if q: qs = qs.filter(Q(internal_id__icontains=q) | Q(license_plate__icontains=q))
        return JsonResponse({'results': [_unidad_to_dict(u) for u in qs]})
    if request.method == 'POST':
        err = _perm_check(request, 'ternium.add_unidad')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        internal_id = (body.get('internal_id') or '').strip()
        if not internal_id:
            return JsonResponse({'error': 'El ID interno es requerido'}, status=400)
        if Unidad.objects.filter(internal_id__iexact=internal_id).exists():
            return JsonResponse({'error': 'Ya existe una unidad con ese ID'}, status=400)
        kwargs = {'internal_id': internal_id}
        for f in _UNIDAD_TEXT_FIELDS:
            if f == 'internal_id': continue
            if f in body:
                v = (body.get(f) or '').strip() if isinstance(body.get(f), str) else body.get(f)
                kwargs[f] = v or None
        for f in _UNIDAD_DATE_FIELDS:
            if f in body and body[f]:
                kwargs[f] = body[f]
        if body.get('year') not in (None, '', 0):
            try: kwargs['year'] = int(body['year'])
            except Exception: pass
        kwargs.setdefault('asset_type', 'TRACTOR')
        kwargs.setdefault('operational_status', 'ACTIVO')
        kwargs.setdefault('ownership', 'PROPIA')
        u = Unidad.objects.create(**kwargs)
        return JsonResponse(_unidad_to_dict(u), status=201)
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

@csrf_exempt
@login_required
def api_cat_unidad_detail(request, pk):
    u = get_object_or_404(Unidad, pk=pk)
    if request.method == 'GET':
        return JsonResponse(_unidad_to_dict(u))
    if request.method in ('PUT', 'PATCH'):
        err = _perm_check(request, 'ternium.change_unidad')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        for f in _UNIDAD_TEXT_FIELDS:
            if f in body:
                v = body[f]
                if isinstance(v, str):
                    v = v.strip()
                setattr(u, f, v or None)
        for f in _UNIDAD_DATE_FIELDS:
            if f in body:
                setattr(u, f, body[f] or None)
        if 'year' in body:
            try: u.year = int(body['year']) if body['year'] not in (None, '') else None
            except Exception: u.year = None
        u.save()
        return JsonResponse(_unidad_to_dict(u))
    if request.method == 'DELETE':
        err = _perm_check(request, 'ternium.delete_unidad')
        if err: return err
        u.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── CONTENEDORES ─────────────────────────────────────────────────────────
@csrf_exempt
@login_required
def api_cat_contenedores(request):
    if request.method == 'GET':
        qs = Contenedor.objects.all().order_by('nombre')
        q = request.GET.get('q', '')
        if q: qs = qs.filter(Q(nombre__icontains=q) | Q(placas__icontains=q))
        return JsonResponse({'results': [{'id': c.id, 'nombre': c.nombre, 'placas': c.placas or ''} for c in qs]})
    if request.method == 'POST':
        err = _perm_check(request, 'ternium.add_contenedor')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        if Contenedor.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'error': 'Ya existe un contenedor con ese nombre'}, status=400)
        c = Contenedor.objects.create(nombre=nombre, placas=body.get('placas', '').strip())
        return JsonResponse({'id': c.id, 'nombre': c.nombre, 'placas': c.placas or ''}, status=201)
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

@csrf_exempt
@login_required
def api_cat_contenedor_detail(request, pk):
    c = get_object_or_404(Contenedor, pk=pk)
    if request.method == 'GET':
        return JsonResponse({'id': c.id, 'nombre': c.nombre, 'placas': c.placas or ''})
    if request.method in ('PUT', 'PATCH'):
        err = _perm_check(request, 'ternium.change_contenedor')
        if err: return err
        body, err = _json_body(request)
        if err: return err
        if 'nombre' in body: c.nombre = body['nombre'].strip()
        if 'placas' in body: c.placas = body['placas'].strip()
        c.save()
        return JsonResponse({'id': c.id, 'nombre': c.nombre, 'placas': c.placas or ''})
    if request.method == 'DELETE':
        err = _perm_check(request, 'ternium.delete_contenedor')
        if err: return err
        c.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── PERFIL DE USUARIO ────────────────────────────────────────────────────
@csrf_exempt
@login_required
def api_perfil(request):
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    if request.method == 'GET':
        avatar_url = None
        try:
            if profile.avatar and profile.avatar.name:
                avatar_url = profile.avatar.url
        except Exception:
            pass
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_superuser': user.is_superuser,
            'is_staff': user.is_staff,
            'area': profile.area or '',
            'telefono': profile.telefono or '',
            'empresa': profile.empresa or '',
            'avatar_url': avatar_url,
            'grupos': [{'id': g.id, 'name': g.name} for g in user.groups.all()],
            'empresas_autorizadas': [{'id': e.id, 'nombre': e.nombre} for e in profile.empresas_autorizadas.all()],
        })
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
        except Exception:
            body = {}
        user.first_name = body.get('first_name', user.first_name)
        user.last_name = body.get('last_name', user.last_name)
        user.email = body.get('email', user.email)
        user.save()
        profile.area = body.get('area', profile.area)
        profile.telefono = body.get('telefono', profile.telefono)
        profile.empresa = body.get('empresa', profile.empresa)
        profile.save()
        return JsonResponse({'ok': True, 'message': 'Perfil actualizado correctamente'})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)

# ── GESTION DE PERMISOS POR USUARIO (ADMIN) ──────────────────────────────
_MODULE_PERMS = [
    ('ternium.view_remision',          'Ver Remisiones'),
    ('ternium.add_remision',           'Crear Remisiones'),
    ('ternium.change_remision',        'Editar Remisiones'),
    ('ternium.delete_remision',        'Eliminar Remisiones'),
    ('ternium.view_empresa',           'Ver Empresas'),
    ('ternium.add_empresa',            'Agregar Empresas'),
    ('ternium.change_empresa',         'Editar Empresas'),
    ('ternium.add_lugar',              'Agregar Lugares'),
    ('ternium.change_lugar',           'Editar Lugares'),
    ('ternium.add_operador',           'Agregar Operadores'),
    ('ternium.change_operador',        'Editar Operadores'),
    ('ternium.add_material',           'Agregar Materiales'),
    ('ternium.change_material',        'Editar Materiales'),
    ('ternium.add_unidad',             'Agregar Unidades'),
    ('ternium.change_unidad',          'Editar Unidades'),
    ('ternium.add_contenedor',         'Agregar Contenedores'),
    ('ternium.change_contenedor',      'Editar Contenedores'),
    ('ternium.view_registrologistico', 'Ver Logistica'),
    ('ternium.add_registrologistico',  'Crear Logistica'),
    ('ternium.view_entradamaquila',    'Ver Entradas Maquila'),
    ('ternium.add_entradamaquila',     'Crear Entradas Maquila'),
]

@login_required
def api_admin_usuarios(request):
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'FORBIDDEN'}, status=403)
    from django.contrib.auth.models import User as AuthUser
    users = AuthUser.objects.all().select_related('ternium_profile').prefetch_related(
        'groups', 'user_permissions'
    ).order_by('username')
    data = []
    for u in users:
        profile = getattr(u, 'ternium_profile', None)
        data.append({
            'id': u.id, 'username': u.username,
            'full_name': u.get_full_name() or u.username,
            'email': u.email, 'is_active': u.is_active,
            'is_superuser': u.is_superuser, 'is_staff': u.is_staff,
            'area': (profile.area or '') if profile else '',
            'empresa': (profile.empresa or '') if profile else '',
            'grupos': [g.name for g in u.groups.all()],
            'empresas_autorizadas': [{'id': e.id, 'nombre': e.nombre} for e in profile.empresas_autorizadas.all()] if profile else [],
        })
    return JsonResponse({'users': data})

@csrf_exempt
@login_required
def api_admin_usuario_permisos(request, pk):
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'FORBIDDEN'}, status=403)
    from django.contrib.auth.models import User as AuthUser, Permission
    from django.contrib.contenttypes.models import ContentType
    usuario = get_object_or_404(AuthUser, pk=pk)
    profile, _ = Profile.objects.get_or_create(user=usuario)
    if request.method == 'GET':
        user_perm_codes = set()
        for p in usuario.user_permissions.all():
            user_perm_codes.add(f"{p.content_type.app_label}.{p.codename}")
        all_empresas = [{'id': e.id, 'nombre': e.nombre} for e in Empresa.objects.all().order_by('nombre')]
        return JsonResponse({
            'id': usuario.id, 'username': usuario.username,
            'full_name': usuario.get_full_name(), 'email': usuario.email,
            'is_active': usuario.is_active, 'is_staff': usuario.is_staff,
            'is_superuser': usuario.is_superuser,
            'area': profile.area or '', 'empresa': profile.empresa or '', 'telefono': profile.telefono or '',
            'user_perms': list(user_perm_codes),
            'empresas_autorizadas': [e.id for e in profile.empresas_autorizadas.all()],
            'all_empresas': all_empresas,
            'available_perms': [{'codename': p[0], 'label': p[1]} for p in _MODULE_PERMS],
        })
    if request.method in ('PUT', 'PATCH', 'POST'):
        body, err = _json_body(request)
        if err: return err
        if 'is_active' in body: usuario.is_active = bool(body['is_active'])
        if 'is_staff' in body and request.user.is_superuser: usuario.is_staff = bool(body['is_staff'])
        usuario.save()
        if 'area' in body: profile.area = body['area']
        if 'empresa' in body: profile.empresa = body['empresa']
        if 'telefono' in body: profile.telefono = body['telefono']
        profile.save()
        if 'empresas_autorizadas' in body:
            ids = [int(i) for i in body['empresas_autorizadas'] if str(i).isdigit()]
            profile.empresas_autorizadas.set(Empresa.objects.filter(id__in=ids))
        if 'user_perms' in body:
            perm_codes = body['user_perms']
            perms_to_set = []
            for code in perm_codes:
                parts = code.split('.')
                if len(parts) == 2:
                    try:
                        ct = ContentType.objects.get(app_label=parts[0])
                        perm = Permission.objects.get(content_type=ct, codename=parts[1])
                        perms_to_set.append(perm)
                    except Exception:
                        pass
            usuario.user_permissions.set(perms_to_set)
        return JsonResponse({'ok': True, 'message': f'Usuario {usuario.username} actualizado'})
    return JsonResponse({'error': 'Metodo no permitido'}, status=405)
