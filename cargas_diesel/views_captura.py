"""
Captura de diesel desde el celular (PWA de Next en /diesel/captura) y los
catálogos que usa: Permisionarios (con sus unidades de Catálogos), Thermos y
Despachadores (usuarios con el permiso "App PWA diésel", acceso_carga_diesel).

La captura tiene dos apartados: Unidad (unidades de Catálogos, km y litros) y
Thermo (el despachador lo escribe; si es nuevo se da de alta solo; solo litros, sin horas).
En los dos el nombre del operador es obligatorio. Las unidades son las mismas de
remisiones; su vínculo con el permisionario y con la unidad de diesel vive en
esta app, así que remisiones no cambia.
"""
import io
import mimetypes
import os
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import FileResponse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from ternium.borrado import es_staff, revisar_borrado, uso as uso_registro
from ternium.models import Unidad as UnidadCatalogo

from . import archivos
from .correo_carga import correo_invalido, programar_correo_carga, separar_correos
from .models import (
    CargaDiesel, FotoComplementaria, Patio, PerfilUsuarioDiesel, Permisionario, PermisionarioUnidad, Thermo, Totem,
    Unidad, es_3r_nombre,
)
from .views import get_patios_usuario

PERM_CAPTURA = 'cargas_diesel.acceso_carga_diesel'


def puede_capturar(user):
    return user.is_superuser or user.has_perm(PERM_CAPTURA) or user.has_perm('ternium.acceso_diesel')


def puede_administrar(user):
    """Quien entra a Catálogos administra (agrega y edita) Permisionarios, Thermos y Despachadores,
    como en los demás catálogos."""
    return user.is_superuser or user.has_perm('ternium.acceso_catalogos')


def puede_registrar_olvidadas(user):
    """Quien entra a Control Diésel registra desde el sistema la carga que se le pasó a un
    despachador: a nombre de él y con la fecha y hora en que se hizo."""
    return user.is_superuser or user.has_perm('ternium.acceso_diesel')


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
    """Flota propia de 3R RECYCLING: sus unidades piden kilometraje y foto del odómetro."""
    return bool(permisionario) and es_3r_nombre(permisionario.nombre)


def es_3r_transporte(permisionario):
    """Unidades de 3R TRANSPORTE: el kilometraje y la foto del odómetro son obligatorios."""
    return bool(permisionario) and ' '.join(permisionario.nombre.upper().split()).startswith('3R TRANSPORTE')


# Por ahora el kilometraje y la foto del odómetro se piden en las unidades de 3R RECYCLING
# pero no se exigen. En True vuelven a ser obligatorios.
ODOMETRO_OBLIGATORIO = False


def pide_odometro(permisionario):
    """Unidades que llevan kilometraje (y foto del odómetro); las de los demás permisionarios no."""
    return es_3r_recycling(permisionario) or es_3r_transporte(permisionario)


def odometro_obligatorio(permisionario):
    """3R TRANSPORTE siempre; 3R RECYCLING solo si se exige (ODOMETRO_OBLIGATORIO)."""
    return es_3r_transporte(permisionario) or (ODOMETRO_OBLIGATORIO and es_3r_recycling(permisionario))


def _permisionario_activo(thermo):
    p = thermo.permisionario
    return p if p and p.activo else None


def _permisionario_de_unidad(unidad_cat):
    vinculo = PermisionarioUnidad.objects.select_related('permisionario').filter(
        unidad=unidad_cat, permisionario__activo=True,
    ).first()
    return vinculo.permisionario if vinculo else None


def normalizar_thermo(texto):
    """Identificador del thermo como lo escribe el despachador: en mayúsculas y sin espacios de más."""
    return ' '.join(str(texto or '').split()).upper()[:50]


def fotos_obligatorias(tipo_carga, permisionario):
    """Las fotos de inicio y final de la bomba siempre; la del odómetro si el km es obligatorio."""
    if tipo_carga == 'thermo':
        return ['foto_thermo', 'foto_thermo_final']
    return ['foto_bomba', 'foto_bomba_final'] + (['foto_odometro'] if odometro_obligatorio(permisionario) else [])


AVISO_FOTO = {
    'foto_bomba': 'Toma la foto de inicio de la bomba (en 0).',
    'foto_bomba_final': 'Toma la foto final de la bomba (al terminar la carga).',
    'foto_thermo': 'Toma la foto de inicio de la bomba del thermo (en 0).',
    'foto_thermo_final': 'Toma la foto final de la bomba del thermo (al terminar la carga).',
    'foto_odometro': 'Toma la foto del odómetro (obligatoria en unidades de 3R TRANSPORTE).',
}


# ─────────────────────────────────────────────
# CAPTURA DESDE EL CELULAR
# ─────────────────────────────────────────────
class CapturaDatosAPIView(APIView):
    """GET: lo que necesita la pantalla de captura: despachador, patios, las
    unidades y los thermos (los dos con la misma forma: nombre, detalle,
    permisionario y última lectura) y las cargas que el usuario registró hoy."""

    def get(self, request):
        if not puede_capturar(request.user):
            return _sin_permiso('No tienes el permiso "App PWA diésel".')

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
        # pide_lectura: solo las unidades de 3R RECYCLING y 3R TRANSPORTE piden km (y foto del
        # odómetro); las de permisionarios no. A ningún thermo se le piden horas (solo litros).
        unidades = [{
            'id': u.pk,
            'nombre': u.internal_id,
            'detalle': ' · '.join(x for x in (u.license_plate or '', u.get_asset_type_display()) if x),
            'permisionario': _perm_dict(vinculos.get(u.pk)),
            'pide_lectura': pide_odometro(vinculos.get(u.pk)),
            'lectura_obligatoria': odometro_obligatorio(vinculos.get(u.pk)),
            'fotos_obligatorias': fotos_obligatorias('unidad', vinculos.get(u.pk)),
            'ultima_lectura': float(ultimo_km[u.pk]) if ultimo_km.get(u.pk) is not None else None,
        } for u in UnidadCatalogo.objects.order_by('internal_id')]

        thermos = [{
            'id': t.pk,
            'nombre': t.identificador,
            'detalle': t.descripcion,
            'permisionario': _perm_dict(_permisionario_activo(t)),
            'pide_lectura': False,
            'lectura_obligatoria': False,
            'fotos_obligatorias': fotos_obligatorias('thermo', _permisionario_activo(t)),
            'ultima_lectura': None,
        } for t in Thermo.objects.filter(activo=True).select_related('permisionario')]

        hoy = CargaDiesel.objects.filter(
            usuario=request.user, fecha_carga__date=timezone.localdate(),
        ).select_related('unidad', 'thermo', 'patio', 'usuario').prefetch_related('fotos_complementarias') \
            .order_by('-fecha_carga', '-pk')[:30]

        datos = {
            'despachador': {'id': request.user.pk, 'nombre': _nombre(request.user)},
            'patios': [{'id': p.pk, 'nombre': p.nombre, 'codigo': p.codigo} for p in get_patios_usuario(request.user)],
            'unidades': unidades,
            'thermos': thermos,
            # Para elegir el permisionario de la carga de thermo.
            'permisionarios': [{'id': p.pk, 'nombre': p.nombre}
                               for p in Permisionario.objects.filter(activo=True).order_by('nombre')],
            'max_complementarias': FotoComplementaria.MAXIMO,
            'hoy': [_carga_resumen(c) for c in hoy],
        }
        # Para registrar desde el sistema la carga que se le pasó a un despachador.
        if puede_registrar_olvidadas(request.user):
            datos['despachadores'] = [
                {'id': u.pk, 'nombre': _nombre(u), 'patios': list(get_patios_usuario(u).values_list('pk', flat=True))}
                for u in _despachadores()
            ]
        return Response(datos)


# Fotos fijas de una carga: campo → nombre (en el orden en que se comparten).
FOTOS_CARGA = [
    ('foto_bomba', 'Foto inicio (Bomba)'), ('foto_bomba_final', 'Foto final (Bomba)'), ('foto_odometro', 'Odómetro'),
    ('foto_thermo', 'Foto inicio (Thermo)'), ('foto_thermo_final', 'Foto final (Thermo)'),
    ('foto_horas_thermo', 'Horas del thermo'), ('foto_sticker', 'Sticker'), ('foto_motor', 'Motor'),
]


def fotos_de_carga(c):
    """Las fotos de la carga (fijas y complementarias) como [{clave, nombre}]; la clave sirve
    para descargarla en /api/captura/cargas/<id>/fotos/<clave>/ (y compartirla por WhatsApp)."""
    fotos = [{'clave': campo, 'nombre': nombre} for campo, nombre in FOTOS_CARGA if getattr(c, campo)]
    fotos += [{'clave': f'c{f.pk}', 'nombre': f'Complementaria {n}'}
              for n, f in enumerate(c.fotos_complementarias.all(), 1) if f.foto]
    return fotos


def _totem_carga(c):
    """Diésel del tótem antes y después de la carga y el % en que quedó (None si la carga es de
    antes de que se guardara)."""
    if c.totem_antes is None or c.totem_despues is None:
        return None
    return {
        'antes': float(c.totem_antes),
        'cargado': float(c.litros_diesel + c.litros_thermo),
        'despues': float(c.totem_despues),
        'porcentaje': round(float(c.totem_despues / c.totem_capacidad) * 100) if c.totem_capacidad else None,
    }


DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
MAX_RELLENOS = 14  # en el mensaje de WhatsApp


def _litros(c):
    return float(c.litros_thermo if c.tipo_carga == 'thermo' else c.litros_diesel)


def _semana_carga(c):
    """Semana (lunes a domingo, número ISO) de la carga y los rellenos de esa misma unidad o thermo
    en la semana hasta esta carga: si se manda después, no se mezclan los posteriores."""
    if not (c.unidad_id or c.thermo_id):
        return None
    local = timezone.localtime(c.fecha_carga)
    lunes = timezone.make_aware(datetime.combine(local.date() - timedelta(days=local.weekday()), time.min))
    equipo = {'unidad_id': c.unidad_id} if c.unidad_id else {'thermo_id': c.thermo_id}
    semana = list(CargaDiesel.objects.filter(**equipo, fecha_carga__gte=lunes).filter(
        Q(fecha_carga__lt=c.fecha_carga) | Q(fecha_carga=c.fecha_carga, pk__lte=c.pk),
    ).order_by('fecha_carga', 'pk'))
    rellenos = []
    for r in semana[-MAX_RELLENOS:]:
        hora = timezone.localtime(r.fecha_carga)
        rellenos.append({'dia': f'{DIAS[hora.weekday()]} {hora:%d/%m}', 'hora': f'{hora:%H:%M}',
                         'litros': _litros(r), 'esta': r.pk == c.pk})
    return {
        'numero': local.isocalendar()[1],
        'rellenos': rellenos,
        'omitidos': max(len(semana) - MAX_RELLENOS, 0),
        'cargas': len(semana),
        'litros': round(sum(_litros(r) for r in semana), 2),
    }


def _carga_resumen(c):
    local = timezone.localtime(c.fecha_carga)
    return {
        'id': c.pk,
        'fecha': local.strftime('%d/%m/%Y'),
        'hora': local.strftime('%H:%M'),
        'equipo': c.equipo,
        'tipo_carga': c.tipo_carga,
        'litros': _litros(c),
        'odometro': float(c.odometro) if c.odometro is not None else None,
        'hrs_thermo': float(c.hrs_thermo),
        # Solo la flota de 3R maneja rendimiento; las unidades de permisionarios son ajenas.
        'rendimiento': float(c.rendimiento) if c.rendimiento is not None and es_3r_nombre(c.permisionario_nombre) else None,
        'permisionario': c.permisionario_nombre,
        'operador': c.operador_nombre,
        'patio': c.patio.nombre,
        'despachador': _nombre(c.usuario),
        'semana': _semana_carga(c),
        'totem': _totem_carga(c),
        'fotos': fotos_de_carga(c),
    }


class CapturaCargaSerializer(serializers.Serializer):
    patio = serializers.PrimaryKeyRelatedField(queryset=Patio.objects.filter(activo=True))
    tipo_carga = serializers.ChoiceField(choices=CargaDiesel.TIPO_CARGA)
    # Apartado Unidad: unidad de Catálogos + kilometraje. Apartado Thermo: thermo + litros (sin horas).
    unidad = serializers.PrimaryKeyRelatedField(queryset=UnidadCatalogo.objects.all(), required=False, allow_null=True)
    thermo = serializers.PrimaryKeyRelatedField(queryset=Thermo.objects.filter(activo=True), required=False, allow_null=True)
    # El despachador escribe el thermo: si ya existe se usa (con su permisionario); si no, se da de alta solo.
    thermo_texto = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    # Thermo: el permisionario que elige el despachador (obligatorio). Si no se manda (versión
    # anterior de la app), se usa el del thermo.
    permisionario = serializers.PrimaryKeyRelatedField(
        queryset=Permisionario.objects.filter(activo=True), required=False, allow_null=True)
    odometro = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    hrs_thermo = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0, required=False, allow_null=True)
    litros = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0.01'))
    cinchos_anteriores = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    cinchos_actuales = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    foto_odometro = serializers.ImageField(required=False, allow_null=True)
    foto_bomba = serializers.ImageField(required=False, allow_null=True)
    foto_bomba_final = serializers.ImageField(required=False, allow_null=True)
    foto_thermo = serializers.ImageField(required=False, allow_null=True)
    foto_thermo_final = serializers.ImageField(required=False, allow_null=True)
    foto_horas_thermo = serializers.ImageField(required=False, allow_null=True)
    operador = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    # Fotos extra que el despachador anexa si aplican (varias con la misma clave).
    fotos_complementarias = serializers.ListField(
        child=serializers.ImageField(), required=False, default=list, max_length=FotoComplementaria.MAXIMO,
        error_messages={'max_length': f'Máximo {FotoComplementaria.MAXIMO} fotos complementarias.'},
    )
    # Carga que se le pasó al despachador, registrada desde el sistema: a nombre de él y con la
    # fecha y hora en que se hizo. La app no los manda (la carga es de quien la captura, ahora).
    despachador = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), required=False, allow_null=True)
    fecha_carga = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, data):
        data['operador'] = ' '.join(data.get('operador', '').split()).upper()  # texto libre, en MAYÚSCULAS
        user = self.context['request'].user
        if not get_patios_usuario(user).filter(pk=data['patio'].pk).exists():
            raise serializers.ValidationError('No tienes acceso a ese patio.')
        despachador, fecha = data.get('despachador'), data.get('fecha_carga')
        if despachador or fecha:
            if not puede_registrar_olvidadas(user):
                raise serializers.ValidationError('No tienes permiso para registrar cargas a nombre de un despachador.')
            if not despachador:
                raise serializers.ValidationError('Elige el despachador que hizo la carga.')
            if not fecha:
                raise serializers.ValidationError('Escribe la fecha y hora de la carga.')
            if not despachador.has_perm(PERM_CAPTURA) or not get_patios_usuario(despachador).filter(pk=data['patio'].pk).exists():
                raise serializers.ValidationError(f'{_nombre(despachador)} no es despachador de ese patio.')
            if fecha > timezone.now() + timedelta(minutes=5):
                raise serializers.ValidationError('La fecha de la carga no puede ser futura.')
        if data['tipo_carga'] == 'unidad':
            if not data.get('unidad'):
                raise serializers.ValidationError('Elige la unidad.')
            permisionario = _permisionario_de_unidad(data['unidad'])
            # Solo las unidades de 3R RECYCLING y 3R TRANSPORTE llevan kilometraje; las de permisionarios no.
            if not pide_odometro(permisionario):
                data['odometro'] = None
            elif odometro_obligatorio(permisionario) and data.get('odometro') is None:
                raise serializers.ValidationError('Escribe el kilometraje de la unidad.')
        else:
            texto = normalizar_thermo(data.get('thermo_texto'))
            data['thermo_nuevo'] = ''
            if texto:
                existente = Thermo.objects.select_related('permisionario').filter(identificador__iexact=texto).first()
                data['thermo'] = existente
                data['thermo_nuevo'] = '' if existente else texto
            elif not data.get('thermo'):
                raise serializers.ValidationError('Escribe el thermo.')
            if 'permisionario' in self.initial_data:
                permisionario = data.get('permisionario')
                if not permisionario:
                    raise serializers.ValidationError('Elige el permisionario.')
            else:
                permisionario = _permisionario_activo(data['thermo']) if data['thermo'] else None
            data['hrs_thermo'] = Decimal('0')  # a ningún thermo se le piden horas: solo los litros
        if not data['operador']:
            raise serializers.ValidationError('Escribe el nombre del operador.')
        for foto in fotos_obligatorias(data['tipo_carga'], permisionario):
            if not data.get(foto):
                raise serializers.ValidationError(AVISO_FOTO[foto])
        data['permisionario'] = permisionario
        return data


class CapturaCargaAPIView(APIView):
    """POST (multipart): registra una carga de Unidad o de Thermo. El despachador
    es el usuario que la registra y el permisionario sale de la unidad o del thermo.
    Desde el sistema (carga que se le pasó al despachador) llegan también el despachador
    y la fecha y hora de la carga."""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if not puede_capturar(request.user):
            return _sin_permiso('No tienes el permiso "App PWA diésel".')
        ser = CapturaCargaSerializer(data=request.data, context={'request': request})
        if not ser.is_valid():
            return Response({'detail': _primer_error(ser.errors)}, status=status.HTTP_400_BAD_REQUEST)
        d = ser.validated_data
        es_thermo = d['tipo_carga'] == 'thermo'
        try:
            return self._registrar(d, es_thermo, request)
        except archivos.ErrorArchivo as e:  # la carga no se guardó: que la vuelvan a mandar
            return Response({'detail': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    def _registrar(self, d, es_thermo, request):
        with transaction.atomic():
            # Bloquea el tótem: dos cargas a la vez no deben dejar mal el inventario.
            totem = Totem.objects.select_for_update().filter(patio=d['patio']).first()
            if not totem:
                return Response({'detail': 'Este patio no tiene un tótem configurado.'}, status=status.HTTP_400_BAD_REQUEST)
            if totem.cantidad_diesel < d['litros']:
                return Response({'detail': f"Diésel insuficiente en el tótem: hay {totem.cantidad_diesel} L."},
                                status=status.HTTP_400_BAD_REQUEST)

            unidad = thermo = None
            permisionario = d['permisionario']  # lo resolvió validate()
            if es_thermo:
                thermo = d['thermo']
                if not thermo:  # escrito por el despachador y nuevo: se da de alta con el permisionario elegido
                    thermo, _ = Thermo.objects.get_or_create(identificador=d['thermo_nuevo'],
                                                             defaults={'permisionario': permisionario})
                elif not thermo.activo:  # dado de baja pero se volvió a cargar: vuelve a estar activo
                    thermo.activo = True
                    thermo.save(update_fields=['activo'])
                # Un thermo sin permisionario se queda con el que eligieron; si ya tiene uno, el
                # catálogo no cambia (solo la carga lleva el elegido).
                if permisionario and not _permisionario_activo(thermo):
                    thermo.permisionario = permisionario
                    thermo.save(update_fields=['permisionario'])
            else:
                unidad = Unidad.para_unidad_catalogo(d['unidad'])
                if unidad.patio_id is None:
                    unidad.patio = d['patio']
                    unidad.save(update_fields=['patio'])

            despachador = d.get('despachador') or request.user
            carga = CargaDiesel(
                patio=d['patio'], unidad=unidad, thermo=thermo,
                usuario=despachador, persona_relleno=despachador, tipo_carga=d['tipo_carga'],
                odometro=None if es_thermo else d.get('odometro'),
                hrs_thermo=d['hrs_thermo'] if es_thermo else 0,
                litros_diesel=0 if es_thermo else d['litros'],
                litros_thermo=d['litros'] if es_thermo else 0,
                cinchos_anteriores=d['cinchos_anteriores'], cinchos_actuales=d['cinchos_actuales'],
                permisionario=permisionario, permisionario_nombre=permisionario.nombre if permisionario else '',
                operador_nombre=d['operador'],
            )
            fecha = d.get('fecha_carga')
            if fecha:  # carga olvidada: el rendimiento y el precio van contra lo anterior a esa fecha
                carga.fecha_carga = fecha
                carga.registrada_por, carga.registrada_en = request.user, timezone.now()
            # Las fotos van a S3 como las de remisiones (si falla una, no se guarda la carga).
            for campo in ('foto_odometro', 'foto_bomba', 'foto_bomba_final', 'foto_thermo', 'foto_thermo_final', 'foto_horas_thermo'):
                if d.get(campo):
                    archivos.subir(carga, campo, d[campo], f'la foto "{dict(FOTOS_CARGA)[campo]}"')
            carga.rendimiento = carga.calcular_rendimiento()
            carga.calcular_costo()
            carga.save()
            if fecha:  # auto_now_add le pone la hora de ahora al guardar
                carga.fecha_carga = fecha
                CargaDiesel.objects.filter(pk=carga.pk).update(fecha_carga=fecha)
                carga.recalcular_siguiente()  # queda en medio: es la anterior de la siguiente
            for n, foto in enumerate(d['fotos_complementarias'], 1):
                extra = FotoComplementaria(carga=carga)
                archivos.subir(extra, 'foto', foto, f'la foto "Complementaria {n}"')
                extra.save()
            carga.descontar_del_totem()
            # Correo al permisionario con el detalle y las fotos (sale después del commit).
            correo_a = programar_correo_carga(carga)

        return Response({**_carga_resumen(carga), 'correo_a': correo_a}, status=status.HTTP_201_CREATED)


def _carga_visible(user, pk):
    """La carga, si el usuario la puede ver: el despachador las suyas; quien administra diésel, todas
    (de sus patios)."""
    cargas = CargaDiesel.objects.filter(pk=pk, patio__in=get_patios_usuario(user))
    if not (user.is_superuser or user.has_perm('ternium.acceso_diesel')):
        cargas = cargas.filter(usuario=user)
    return cargas.select_related('patio', 'usuario').first()


class CargaResumenAPIView(APIView):
    """GET: datos de una carga para enviarla por WhatsApp (mensaje + fotos), igual que en
    "Mis cargas de hoy". Lo usa también el listado "Cargas de diésel" del sistema."""

    def get(self, request, pk):
        if not puede_capturar(request.user):
            return _sin_permiso('No tienes el permiso "App PWA diésel".')
        carga = _carga_visible(request.user, pk)
        if not carga:
            return Response({'detail': 'Carga no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_carga_resumen(carga))


class CargaFotoAPIView(APIView):
    """GET: una foto de la carga (clave = campo fijo como 'foto_bomba' o 'c<id>' para una
    complementaria). Pasa por la API para que el celular pueda compartirla por WhatsApp
    (las URLs del almacenamiento no siempre permiten leerlas desde otro dominio).
    El despachador solo ve las fotos de sus cargas; quien administra diésel, todas."""

    def get(self, request, pk, clave):
        if not puede_capturar(request.user):
            return _sin_permiso('No tienes el permiso "App PWA diésel".')
        carga = _carga_visible(request.user, pk)
        if not carga:
            return Response({'detail': 'Carga no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        if clave in dict(FOTOS_CARGA):
            archivo = getattr(carga, clave)
        elif clave.startswith('c') and clave[1:].isdigit():
            extra = carga.fotos_complementarias.filter(pk=int(clave[1:])).first()
            archivo = extra.foto if extra else None
        else:
            archivo = None
        if not archivo:
            return Response({'detail': 'Esa foto no existe.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            contenido = archivos.leer(archivo)
        except Exception:
            return Response({'detail': 'No se pudo leer la foto.'}, status=status.HTTP_404_NOT_FOUND)
        ext = os.path.splitext(archivo.name)[1].lower() or '.jpg'
        return FileResponse(io.BytesIO(contenido), content_type=mimetypes.guess_type(f'x{ext}')[0] or 'image/jpeg',
                            filename=f'{carga.equipo}-{clave}{ext}')


# ─────────────────────────────────────────────
# CATÁLOGO: PERMISIONARIOS
# ─────────────────────────────────────────────
def _permisionario_dict(p):
    vinculos = sorted(p.unidades_asignadas.all(), key=lambda v: v.unidad.internal_id)
    return {
        'id': p.pk, 'nombre': p.nombre, 'rfc': p.rfc, 'telefono': p.telefono, 'correo': p.correo, 'activo': p.activo,
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
    if 'correo' in body:
        texto = str(body.get('correo') or '')
        malo = correo_invalido(texto)
        if malo:
            return f'El correo "{malo}" no es válido.'
        p.correo = ', '.join(separar_correos(texto))
        if len(p.correo) > 500:
            return 'Son demasiados correos (máximo 500 caracteres).'
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
    """PUT/PATCH: actualiza solo los campos que vengan (activo=false lo da de baja).
    GET ?uso=1: qué lo usa. DELETE (solo staff, ?confirmar=1 si lo usan): lo elimina; sus
    cargas conservan el nombre del permisionario y sus thermos quedan sin permisionario."""
    parser_classes = [JSONParser]

    def get(self, request, pk):
        if not puede_administrar(request.user):
            return _sin_permiso()
        p = Permisionario.objects.filter(pk=pk).first()
        if not p:
            return Response({'detail': 'Permisionario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        if request.query_params.get('uso') == '1':
            return Response(uso_registro(p))
        return Response(_permisionario_dict(_permisionarios().get(pk=p.pk)))

    def delete(self, request, pk):
        if not es_staff(request.user):
            return Response({'detail': 'Solo el personal staff puede eliminar permisionarios.'}, status=status.HTTP_403_FORBIDDEN)
        p = Permisionario.objects.filter(pk=pk).first()
        if not p:
            return Response({'detail': 'Permisionario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        problema = revisar_borrado(p, f'el permisionario {p.nombre}', request.query_params.get('confirmar') == '1')
        if problema:
            return Response({'detail': problema[0]}, status=problema[1])
        p.delete()
        return Response({'ok': True})

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


def _despachadores():
    """Usuarios activos con el permiso de captura (directo o por grupo)."""
    perm = _permiso_captura()
    return User.objects.filter(
        Q(user_permissions=perm) | Q(groups__permissions=perm), is_active=True,
    ).distinct().select_related('perfil_diesel').order_by('first_name', 'username')


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
        return Response({'results': [_despachador_dict(u) for u in _despachadores()]})

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
