"""
Configuración de tótems de diésel (Next: /diesel/configuracion). Solo staff.

Cada patio tiene un tótem. Desde aquí se da de alta un tótem (con su patio), se
cambian los nombres, la capacidad en litros, la alerta y el nivel actual.
El nivel nunca se sobrescribe a mano: el cambio se registra como un ajuste de
inventario (entrada o salida por la diferencia, con su motivo) para que quede
quién lo hizo, cuándo y por qué, igual que en Ajustes de Inventario.
"""
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AjusteInventario, Patio, Totem

MAX_LITROS = Decimal('99999999.99')  # max_digits=10, decimal_places=2


class EsStaff(BasePermission):
    message = 'Solo el staff puede cambiar la configuración de diésel.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class ErrorConfig(Exception):
    pass


def _litros(valor, campo, minimo=Decimal('0')):
    try:
        n = Decimal(str(valor).replace(',', '').strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ErrorConfig(f'{campo}: escribe una cantidad en litros.')
    if n < minimo or n > MAX_LITROS:
        raise ErrorConfig(f'{campo}: debe ser de {minimo:,.0f} L o más.' if n < minimo else f'{campo}: es demasiado grande.')
    return n


def _texto(valor, campo, largo):
    t = ' '.join(str(valor or '').split())
    if not t:
        raise ErrorConfig(f'Escribe {campo}.')
    if len(t) > largo:
        raise ErrorConfig(f'{campo.capitalize()}: máximo {largo} caracteres.')
    return t


def _codigo_libre(base, excluir=None):
    """Código único del patio (máx. 10): el que pidieron o uno sacado del nombre."""
    base = re.sub(r'[^A-Z0-9]', '', base.upper())[:10] or 'PATIO'
    existe = lambda c: Patio.objects.filter(codigo=c).exclude(pk=excluir).exists()  # noqa: E731
    if not existe(base):
        return base
    for n in range(2, 1000):
        c = f'{base[:10 - len(str(n))]}{n}'
        if not existe(c):
            return c
    raise ErrorConfig('No se pudo generar un código para el patio.')


def _sugerir_codigo(nombre):
    palabras = [p for p in re.sub(r'[^A-Za-z0-9 ]', ' ', _sin_acentos(nombre)).split() if p.lower() not in ('patio', 'de', 'del', 'la', 'el')]
    return ''.join(p[:3] for p in palabras)[:10] or 'PATIO'


def _sin_acentos(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def _ajustar_nivel(totem, nuevo, motivo, user):
    """Registra la diferencia contra el nivel actual como ajuste (entrada o salida)."""
    actual = totem.cantidad_diesel
    if nuevo == actual:
        return None
    return AjusteInventario.objects.create(
        patio=totem.patio, tipo_combustible='diesel',
        tipo_movimiento='entrada' if nuevo > actual else 'salida',
        litros=abs(nuevo - actual), motivo=motivo[:255], usuario=user,
    )


def _dato(patio):
    t = getattr(patio, 'totem', None)
    return {
        'patio_id': patio.pk, 'patio': patio.nombre, 'codigo': patio.codigo, 'activo': patio.activo,
        'totem': {
            'id': t.pk, 'nombre': t.nombre,
            'capacidad': float(t.capacidad_diesel), 'alerta': float(t.alerta_diesel), 'cantidad': float(t.cantidad_diesel),
            'porcentaje': t.porcentaje_diesel(), 'estado': t.estado_diesel(), 'alerta_activa': t.alerta_activa_diesel(),
            'actualizado': timezone.localtime(t.updated_at).strftime('%Y-%m-%d %H:%M'),
        } if t else None,
    }


def _respuesta_error(e):
    return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TotemsConfigAPIView(APIView):
    """GET: todos los patios con su tótem.
    POST {patio_id?} o {patio, codigo?}, {nombre, capacidad, alerta, cantidad?}: da de alta un tótem
    (en un patio sin tótem, o con un patio nuevo). La cantidad inicial entra como ajuste."""
    permission_classes = [EsStaff]

    def get(self, request):
        patios = Patio.objects.select_related('totem').order_by('-activo', 'nombre')
        return Response([_dato(p) for p in patios])

    def post(self, request):
        d = request.data
        try:
            nombre = _texto(d.get('nombre') or 'Tótem Principal', 'el nombre del tótem', 100)
            capacidad = _litros(d.get('capacidad'), 'Capacidad', Decimal('1'))
            alerta = _litros(d.get('alerta') or 0, 'Alerta')
            cantidad = _litros(d.get('cantidad') or 0, 'Nivel inicial')
            if alerta >= capacidad:
                raise ErrorConfig('La alerta debe ser menor a la capacidad.')
            if cantidad > capacidad:
                raise ErrorConfig('El nivel inicial no puede ser mayor a la capacidad.')
            with transaction.atomic():
                if d.get('patio_id'):
                    patio = Patio.objects.select_for_update().filter(pk=d.get('patio_id')).first()
                    if not patio:
                        raise ErrorConfig('Ese patio no existe.')
                    if Totem.objects.filter(patio=patio).exists():
                        raise ErrorConfig(f'{patio.nombre} ya tiene tótem.')
                else:
                    nombre_patio = _texto(d.get('patio'), 'el nombre del patio', 100)
                    if Patio.objects.filter(nombre__iexact=nombre_patio).exists():
                        raise ErrorConfig(f'Ya existe un patio llamado "{nombre_patio}".')
                    codigo = _codigo_libre(d.get('codigo') or _sugerir_codigo(nombre_patio))
                    patio = Patio.objects.create(nombre=nombre_patio, codigo=codigo)
                totem = Totem.objects.create(patio=patio, nombre=nombre, capacidad_diesel=capacidad, alerta_diesel=alerta)
                if cantidad:
                    _ajustar_nivel(totem, cantidad, 'Nivel inicial al dar de alta el tótem', request.user)
        except ErrorConfig as e:
            return _respuesta_error(e)
        patio = Patio.objects.select_related('totem').get(pk=patio.pk)
        return Response(_dato(patio), status=status.HTTP_201_CREATED)


class TotemConfigDetalleAPIView(APIView):
    """PATCH {patio?, activo?, nombre?, capacidad?, alerta?, cantidad?, motivo?} del tótem de un patio.
    Si cambia la cantidad, se registra un ajuste por la diferencia (el motivo es obligatorio)."""
    permission_classes = [EsStaff]

    def patch(self, request, patio_id):
        d = request.data
        try:
            with transaction.atomic():
                patio = Patio.objects.select_for_update().filter(pk=patio_id).first()
                if not patio:
                    return Response({'detail': 'Ese patio no existe.'}, status=status.HTTP_404_NOT_FOUND)
                if 'patio' in d:
                    nombre_patio = _texto(d.get('patio'), 'el nombre del patio', 100)
                    if Patio.objects.filter(nombre__iexact=nombre_patio).exclude(pk=patio.pk).exists():
                        raise ErrorConfig(f'Ya existe un patio llamado "{nombre_patio}".')
                    patio.nombre = nombre_patio
                if 'activo' in d:
                    patio.activo = d.get('activo') in (True, 'true', '1', 1)
                patio.save(update_fields=['nombre', 'activo'])

                totem = Totem.objects.select_for_update().filter(patio=patio).first()
                if totem:
                    if 'nombre' in d:
                        totem.nombre = _texto(d.get('nombre'), 'el nombre del tótem', 100)
                    if 'capacidad' in d:
                        totem.capacidad_diesel = _litros(d.get('capacidad'), 'Capacidad', Decimal('1'))
                    if 'alerta' in d:
                        totem.alerta_diesel = _litros(d.get('alerta'), 'Alerta')
                    nuevo = _litros(d.get('cantidad'), 'Nivel actual') if d.get('cantidad') not in (None, '') else totem.cantidad_diesel
                    if totem.alerta_diesel >= totem.capacidad_diesel:
                        raise ErrorConfig('La alerta debe ser menor a la capacidad.')
                    if nuevo > totem.capacidad_diesel:
                        raise ErrorConfig(f'El nivel ({nuevo:,.0f} L) no puede ser mayor a la capacidad ({totem.capacidad_diesel:,.0f} L).')
                    totem.save()
                    if nuevo != totem.cantidad_diesel:
                        motivo = ' '.join(str(d.get('motivo') or '').split())
                        if not motivo:
                            raise ErrorConfig('Escribe el motivo del cambio de nivel (queda como ajuste de inventario).')
                        _ajustar_nivel(totem, nuevo, f'Configuración: {motivo}', request.user)
                elif any(k in d for k in ('nombre', 'capacidad', 'alerta', 'cantidad')):
                    raise ErrorConfig('Este patio no tiene tótem: dalo de alta primero.')
        except ErrorConfig as e:
            return _respuesta_error(e)
        patio = Patio.objects.select_related('totem').get(pk=patio_id)
        return Response(_dato(patio))
