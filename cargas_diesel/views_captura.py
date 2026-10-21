"""
Captura de diesel desde el celular (PWA de Next en /diesel/captura) y los
catálogos que usa: Permisionarios (con sus unidades de Catálogos), Thermos y
Despachadores (usuarios con el permiso "Acceso carga diesel").

La captura tiene dos apartados: Unidad (unidades de Catálogos, km y litros) y
Thermo (catálogo de thermos, horas y litros). Las unidades son las mismas de
remisiones; su vínculo con el permisionario y con la unidad de diesel vive en
esta app, así que remisiones no cambia.
"""
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from ternium.models import Unidad as UnidadCatalogo

from .models import (
    CargaDiesel, Patio, PerfilUsuarioDiesel, Permisionario, PermisionarioUnidad, Thermo, Totem, Unidad,
)
from .views import get_patios_usuario

PERM_CAPTURA = 'cargas_diesel.acceso_carga_diesel'


def puede_capturar(user):
    return user.is_superuser or user.has_perm(PERM_CAPTURA) or user.has_perm('ternium.acceso_diesel')


def puede_administrar(user):
    """Quien entra a Catálogos administra Permisionarios, Thermos y Despachadores."""
    return user.is_superuser or user.has_perm('ternium.acceso_catalogos')


def _sin_permiso(mensaje='No tienes permiso para esta acción.'):
    return Response({'detail': mensaje}, status=status.HTTP_403_FORBIDDEN)


def _primer_error(errores):
    """El primer mensaje de los errores de un serializer, para mostrarlo tal cual."""
    if isinstance(errores, dict):
        for valor in errores.values():
            return _primer_error(valor)
    if isinstance(errores, list) and errores:
        return _primer_error(errores[0])
    return str(errores)


def _nombre(user):
    return user.get_full_name() or user.username


def _etiqueta_unidad(u):
    return f"{u.internal_id} ({u.license_plate})" if u.license_plate else u.internal_id


def _perm_dict(p):
    return {'id': p.pk, 'nombre': p.nombre} if p else None


def es_3r_recycling(permisionario):
    """Flota propia: a sus thermos no se les piden horas, solo los litros."""
    return bool(permisionario) and ' '.join(permisionario.nombre.upper().split()).startswith('3R RECYCLING')


def _permisionario_activo(thermo):
    p = thermo.permisionario
    return p if p and p.activo else None


# ─────────────────────────────────────────────
# CAPTURA DESDE EL CELULAR
# ─────────────────────────────────────────────
class CapturaDatosAPIView(APIView):
    """GET: lo que necesita la pantalla de captura: despachador, patios, las
    unidades y los thermos (los dos con la misma forma: nombre, detalle,
    permisionario y última lectura) y las cargas que el usuario registró hoy."""

    def get(self, request):
        if not puede_capturar(request.user):
            return _sin_permiso('No tienes el permiso "Acceso carga diesel".')

        # Un permisionario dado de baja ya no se ofrece ni se guarda en cargas nuevas.
        vinculos = {
            v.unidad_id: v.permisionario
            for v in PermisionarioUnidad.objects.select_related('permisionario').filter(permisionario__activo=True)
        }
        cargas_unidad = CargaDiesel.objects.filter(
            unidad=OuterRef('pk'), tipo_carga='unidad', odometro__isnull=False,
        ).order_by('-fecha_carga', '-pk')
        ultimo_km = {
            u.unidad_catalogo_id: u.ultimo_km
            for u in Unidad.objects.filter(unidad_catalogo__isnull=False).annotate(
                ultimo_km=Subquery(cargas_unidad.values('odometro')[:1]))
        }
        # pide_lectura: la unidad siempre pide km; el thermo pide horas salvo si es de 3R RECYCLING.
        unidades = [{
            'id': u.pk,
            'nombre': u.internal_id,
            'detalle': ' · '.join(x for x in (u.license_plate or '', u.get_asset_type_display()) if x),
            'permisionario': _perm_dict(vinculos.get(u.pk)),
            'pide_lectura': True,
            'ultima_lectura': float(ultimo_km[u.pk]) if ultimo_km.get(u.pk) is not None else None,
        } for u in UnidadCatalogo.objects.order_by('internal_id')]

        cargas_thermo = CargaDiesel.objects.filter(thermo=OuterRef('pk'), hrs_thermo__gt=0).order_by('-fecha_carga', '-pk')
        thermos = [{
            'id': t.pk,
            'nombre': t.identificador,
            'detalle': t.descripcion,
            'permisionario': _perm_dict(_permisionario_activo(t)),
            'pide_lectura': not es_3r_recycling(_permisionario_activo(t)),
            'ultima_lectura': float(t.ultimas_hrs) if t.ultimas_hrs is not None else None,
        } for t in Thermo.objects.filter(activo=True).select_related('permisionario').annotate(
            ultimas_hrs=Subquery(cargas_thermo.values('hrs_thermo')[:1]))]

        hoy = CargaDiesel.objects.filter(
            usuario=request.user, fecha_carga__date=timezone.localdate(),
        ).select_related('unidad', 'thermo').order_by('-fecha_carga', '-pk')[:30]

        return Response({
            'despachador': {'id': request.user.pk, 'nombre': _nombre(request.user)},
            'patios': [{'id': p.pk, 'nombre': p.nombre, 'codigo': p.codigo} for p in get_patios_usuario(request.user)],
            'unidades': unidades,
            'thermos': thermos,
            'hoy': [_carga_resumen(c) for c in hoy],
        })


def _carga_resumen(c):
    return {
        'id': c.pk,
        'hora': timezone.localtime(c.fecha_carga).strftime('%H:%M'),
        'equipo': c.equipo,
        'tipo_carga': c.tipo_carga,
        'litros': float(c.litros_thermo if c.tipo_carga == 'thermo' else c.litros_diesel),
        'odometro': float(c.odometro) if c.odometro is not None else None,
        'hrs_thermo': float(c.hrs_thermo),
        'rendimiento': float(c.rendimiento) if c.rendimiento is not None else None,
        'permisionario': c.permisionario_nombre,
    }


class CapturaCargaSerializer(serializers.Serializer):
    patio = serializers.PrimaryKeyRelatedField(queryset=Patio.objects.filter(activo=True))
    tipo_carga = serializers.ChoiceField(choices=CargaDiesel.TIPO_CARGA)
    # Apartado Unidad: unidad de Catálogos + kilometraje. Apartado Thermo: thermo + horas.
    unidad = serializers.PrimaryKeyRelatedField(queryset=UnidadCatalogo.objects.all(), required=False, allow_null=True)
    thermo = serializers.PrimaryKeyRelatedField(queryset=Thermo.objects.filter(activo=True), required=False, allow_null=True)
    odometro = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    hrs_thermo = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0, required=False, allow_null=True)
    litros = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0.01'))
    cinchos_anteriores = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    cinchos_actuales = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    foto_odometro = serializers.ImageField(required=False, allow_null=True)
    foto_bomba = serializers.ImageField(required=False, allow_null=True)
    foto_thermo = serializers.ImageField(required=False, allow_null=True)
    foto_horas_thermo = serializers.ImageField(required=False, allow_null=True)

    def validate(self, data):
        user = self.context['request'].user
        if not get_patios_usuario(user).filter(pk=data['patio'].pk).exists():
            raise serializers.ValidationError('No tienes acceso a ese patio.')
        if data['tipo_carga'] == 'unidad':
            if not data.get('unidad'):
                raise serializers.ValidationError('Elige la unidad.')
            if data.get('odometro') is None:
                raise serializers.ValidationError('Escribe el kilometraje de la unidad.')
        else:
            if not data.get('thermo'):
                raise serializers.ValidationError('Elige el thermo.')
            if es_3r_recycling(_permisionario_activo(data['thermo'])):
                data['hrs_thermo'] = Decimal('0')  # flota propia: solo los litros
            elif data.get('hrs_thermo') is None:
                raise serializers.ValidationError('Escribe las horas del thermo.')
        return data


class CapturaCargaAPIView(APIView):
    """POST (multipart): registra una carga de Unidad o de Thermo. El despachador
    es el usuario que la registra y el permisionario sale de la unidad o del thermo."""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if not puede_capturar(request.user):
            return _sin_permiso('No tienes el permiso "Acceso carga diesel".')
        ser = CapturaCargaSerializer(data=request.data, context={'request': request})
        if not ser.is_valid():
            return Response({'detail': _primer_error(ser.errors)}, status=status.HTTP_400_BAD_REQUEST)
        d = ser.validated_data
        es_thermo = d['tipo_carga'] == 'thermo'

        with transaction.atomic():
            # Bloquea el tótem: dos cargas a la vez no deben dejar mal el inventario.
            totem = Totem.objects.select_for_update().filter(patio=d['patio']).first()
            if not totem:
                return Response({'detail': 'Este patio no tiene un tótem configurado.'}, status=status.HTTP_400_BAD_REQUEST)
            if totem.cantidad_diesel < d['litros']:
                return Response({'detail': f"Diésel insuficiente en el tótem: hay {totem.cantidad_diesel} L."},
                                status=status.HTTP_400_BAD_REQUEST)

            unidad = thermo = permisionario = None
            if es_thermo:
                thermo = d['thermo']
                permisionario = _permisionario_activo(thermo)
            else:
                unidad = Unidad.para_unidad_catalogo(d['unidad'])
                if unidad.patio_id is None:
                    unidad.patio = d['patio']
                    unidad.save(update_fields=['patio'])
                vinculo = PermisionarioUnidad.objects.select_related('permisionario').filter(
                    unidad=d['unidad'], permisionario__activo=True,
                ).first()
                permisionario = vinculo.permisionario if vinculo else None

            carga = CargaDiesel(
                patio=d['patio'], unidad=unidad, thermo=thermo,
                usuario=request.user, persona_relleno=request.user, tipo_carga=d['tipo_carga'],
                odometro=None if es_thermo else d['odometro'],
                hrs_thermo=d['hrs_thermo'] if es_thermo else 0,
                litros_diesel=0 if es_thermo else d['litros'],
                litros_thermo=d['litros'] if es_thermo else 0,
                cinchos_anteriores=d['cinchos_anteriores'], cinchos_actuales=d['cinchos_actuales'],
                permisionario=permisionario, permisionario_nombre=permisionario.nombre if permisionario else '',
            )
            for campo in ('foto_odometro', 'foto_bomba', 'foto_thermo', 'foto_horas_thermo'):
                if d.get(campo):
                    setattr(carga, campo, d[campo])
            carga.rendimiento = carga.calcular_rendimiento()
            carga.calcular_costo()
            carga.save()
            carga.descontar_del_totem()

        return Response(_carga_resumen(carga), status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────
# CATÁLOGO: PERMISIONARIOS
# ─────────────────────────────────────────────
def _permisionario_dict(p):
    vinculos = sorted(p.unidades_asignadas.all(), key=lambda v: v.unidad.internal_id)
    return {
        'id': p.pk, 'nombre': p.nombre, 'rfc': p.rfc, 'telefono': p.telefono, 'activo': p.activo,
        'unidades': [v.unidad_id for v in vinculos],
        'unidades_detalle': [{'id': v.unidad_id, 'nombre': _etiqueta_unidad(v.unidad)} for v in vinculos],
        # Los thermos se asignan desde su propio catálogo; aquí solo se muestran.
        'thermos_detalle': [{'id': t.pk, 'nombre': t.identificador} for t in p.thermos.all()],
    }


def _permisionarios():
    return Permisionario.objects.prefetch_related('unidades_asignadas__unidad', 'thermos')


def _guardar_permisionario(p, body):
    """Aplica los campos que vengan en body. Regresa un mensaje de error o None."""
    if 'nombre' in body:
        p.nombre = str(body.get('nombre') or '').strip()
    if not p.nombre:
        return 'El nombre es requerido.'
    for campo, largo in (('rfc', 13), ('telefono', 20)):
        if campo in body:
            setattr(p, campo, str(body.get(campo) or '').strip()[:largo])
    if 'activo' in body:
        p.activo = bool(body['activo'])

    ids = None
    if 'unidades' in body:
        ids = {int(i) for i in (body.get('unidades') or []) if str(i).isdigit()}
        ocupadas = PermisionarioUnidad.objects.filter(unidad_id__in=ids).select_related('unidad', 'permisionario')
        if p.pk:
            ocupadas = ocupadas.exclude(permisionario=p)
        ocupada = ocupadas.first()
        if ocupada:
            return (f"La unidad {ocupada.unidad.internal_id} ya es de {ocupada.permisionario.nombre}. "
                    "Quítala de ese permisionario primero.")

    with transaction.atomic():
        p.save()
        if ids is not None:
            p.unidades_asignadas.exclude(unidad_id__in=ids).delete()
            actuales = set(p.unidades_asignadas.values_list('unidad_id', flat=True))
            nuevas = UnidadCatalogo.objects.filter(pk__in=ids - actuales).values_list('pk', flat=True)
            PermisionarioUnidad.objects.bulk_create([PermisionarioUnidad(permisionario=p, unidad_id=i) for i in nuevas])
    return None


class PermisionariosAPIView(APIView):
    parser_classes = [JSONParser]

    def get(self, request):
        if not puede_administrar(request.user):
            return _sin_permiso()
        return Response({'results': [_permisionario_dict(p) for p in _permisionarios()]})

    def post(self, request):
        if not puede_administrar(request.user):
            return _sin_permiso()
        p = Permisionario()
        error = _guardar_permisionario(p, request.data)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_permisionario_dict(_permisionarios().get(pk=p.pk)), status=status.HTTP_201_CREATED)


class PermisionarioDetalleAPIView(APIView):
    """PUT/PATCH: actualiza solo los campos que vengan (activo=false lo da de baja)."""
    parser_classes = [JSONParser]

    def _editar(self, request, pk):
        if not puede_administrar(request.user):
            return _sin_permiso()
        p = Permisionario.objects.filter(pk=pk).first()
        if not p:
            return Response({'detail': 'Permisionario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        error = _guardar_permisionario(p, request.data)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_permisionario_dict(_permisionarios().get(pk=p.pk)))

    put = _editar
    patch = _editar


class PermisionarioUnidadesAPIView(APIView):
    """GET: unidades de Catálogos con el permisionario que ya tienen (si tienen),
    para el selector de unidades del permisionario."""

    def get(self, request):
        if not puede_administrar(request.user):
            return _sin_permiso()
        vinculos = {v.unidad_id: v.permisionario for v in PermisionarioUnidad.objects.select_related('permisionario')}
        return Response({'results': [
            {
                'id': u.pk, 'nombre': _etiqueta_unidad(u),
                'permisionario_id': vinculos[u.pk].pk if u.pk in vinculos else None,
                'permisionario_nombre': vinculos[u.pk].nombre if u.pk in vinculos else '',
            }
            for u in UnidadCatalogo.objects.order_by('internal_id')
        ]})


# ─────────────────────────────────────────────
# CATÁLOGO: THERMOS
# ─────────────────────────────────────────────
def _thermo_dict(t):
    return {
        'id': t.pk, 'identificador': t.identificador, 'descripcion': t.descripcion,
        'numero_serie': t.numero_serie, 'activo': t.activo,
        # Texto para el <select> del formulario ('' = sin permisionario).
        'permisionario': str(t.permisionario_id) if t.permisionario_id else '',
        'permisionario_nombre': t.permisionario.nombre if t.permisionario_id else '',
    }


def _guardar_thermo(t, body):
    """Aplica los campos que vengan en body. Regresa un mensaje de error o None."""
    if 'identificador' in body:
        t.identificador = str(body.get('identificador') or '').strip()[:50]
    if not t.identificador:
        return 'El identificador es requerido.'
    repetido = Thermo.objects.filter(identificador__iexact=t.identificador)
    if t.pk:
        repetido = repetido.exclude(pk=t.pk)
    if repetido.exists():
        return f'Ya existe un thermo con el identificador {t.identificador}.'
    for campo, largo in (('descripcion', 150), ('numero_serie', 100)):
        if campo in body:
            setattr(t, campo, str(body.get(campo) or '').strip()[:largo])
    if 'permisionario' in body:
        pid = str(body.get('permisionario') or '')
        t.permisionario = Permisionario.objects.filter(pk=pid).first() if pid.isdigit() else None
    if 'activo' in body:
        t.activo = bool(body['activo'])
    t.save()
    return None


class ThermosAPIView(APIView):
    parser_classes = [JSONParser]

    def get(self, request):
        if not puede_administrar(request.user):
            return _sin_permiso()
        return Response({'results': [_thermo_dict(t) for t in Thermo.objects.select_related('permisionario')]})

    def post(self, request):
        if not puede_administrar(request.user):
            return _sin_permiso()
        t = Thermo()
        error = _guardar_thermo(t, request.data)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_thermo_dict(t), status=status.HTTP_201_CREATED)


class ThermoDetalleAPIView(APIView):
    """PUT/PATCH: actualiza solo los campos que vengan (activo=false lo da de baja)."""
    parser_classes = [JSONParser]

    def _editar(self, request, pk):
        if not puede_administrar(request.user):
            return _sin_permiso()
        t = Thermo.objects.filter(pk=pk).first()
        if not t:
            return Response({'detail': 'Thermo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        error = _guardar_thermo(t, request.data)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_thermo_dict(t))

    put = _editar
    patch = _editar


# ─────────────────────────────────────────────
# CATÁLOGO: DESPACHADORES (usuarios con el permiso de captura)
# ─────────────────────────────────────────────
def _permiso_captura():
    app, codename = PERM_CAPTURA.split('.')
    return Permission.objects.get(content_type__app_label=app, codename=codename)


def _despachador_dict(u, activo=True):
    perfil = getattr(u, 'perfil_diesel', None)
    patios = list(perfil.patios.order_by('nombre')) if perfil else []
    return {
        'id': u.pk, 'usuario': u.pk, 'username': u.username, 'nombre': _nombre(u), 'email': u.email,
        'activo': activo,
        'patios': [p.pk for p in patios],
        'patios_detalle': [{'id': p.pk, 'nombre': p.nombre} for p in patios],
    }


def _guardar_patios(user, body):
    if 'patios' not in body:
        return
    ids = [int(i) for i in (body.get('patios') or []) if str(i).isdigit()]
    perfil, _ = PerfilUsuarioDiesel.objects.get_or_create(user=user)
    perfil.patios.set(Patio.objects.filter(pk__in=ids))


class DespachadoresAPIView(APIView):
    parser_classes = [JSONParser]

    def get(self, request):
        if not puede_administrar(request.user):
            return _sin_permiso()
        perm = _permiso_captura()
        usuarios = User.objects.filter(
            Q(user_permissions=perm) | Q(groups__permissions=perm), is_active=True,
        ).distinct().select_related('perfil_diesel').order_by('first_name', 'username')
        return Response({'results': [_despachador_dict(u) for u in usuarios]})

    def post(self, request):
        """Da el permiso a un usuario existente y le asigna sus patios."""
        if not puede_administrar(request.user):
            return _sin_permiso()
        usuario = User.objects.filter(pk=request.data.get('usuario'), is_active=True).first()
        if not usuario:
            return Response({'detail': 'Elige el usuario que será despachador.'}, status=status.HTTP_400_BAD_REQUEST)
        usuario.user_permissions.add(_permiso_captura())
        _guardar_patios(usuario, request.data)
        return Response(_despachador_dict(usuario), status=status.HTTP_201_CREATED)


class DespachadorDetalleAPIView(APIView):
    """PUT/PATCH: cambia sus patios; activo=false le quita el permiso (y true se lo regresa)."""
    parser_classes = [JSONParser]

    def _editar(self, request, pk):
        if not puede_administrar(request.user):
            return _sin_permiso()
        usuario = User.objects.filter(pk=pk).first()
        if not usuario:
            return Response({'detail': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        activo = True
        if 'activo' in request.data:
            activo = bool(request.data['activo'])
            if activo:
                usuario.user_permissions.add(_permiso_captura())
            else:
                usuario.user_permissions.remove(_permiso_captura())
        _guardar_patios(usuario, request.data)
        return Response(_despachador_dict(usuario, activo=activo))

    put = _editar
    patch = _editar


class DespachadorOpcionesAPIView(APIView):
    """GET: usuarios activos que todavía no son despachadores y todos los patios
    activos, para el formulario de Despachadores."""

    def get(self, request):
        if not puede_administrar(request.user):
            return _sin_permiso()
        perm = _permiso_captura()
        ya = User.objects.filter(Q(user_permissions=perm) | Q(groups__permissions=perm)).values('pk')
        usuarios = User.objects.filter(is_active=True).exclude(pk__in=ya).order_by('first_name', 'username')
        return Response({
            'usuarios': [{'value': str(u.pk), 'label': f"{_nombre(u)} ({u.username})"} for u in usuarios],
            'patios': [{'id': p.pk, 'nombre': p.nombre} for p in Patio.objects.filter(activo=True)],
        })
