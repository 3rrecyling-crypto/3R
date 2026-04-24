"""
api/views/diesel.py
"""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import DynamicPagePagination
from api.permissions import AccesoDiesel
from api.serializers.diesel import (
    PatioSerializer, ProveedorDieselSerializer, UnidadDieselSerializer,
    TotemSerializer, CompraCombustibleSerializer,
    AjusteInventarioSerializer, CargaDieselSerializer,
)
from cargas_diesel.models import (
    Patio, ProveedorDiesel, Unidad, Totem,
    CompraCombustible, AjusteInventario, CargaDiesel,
)


class PatioViewSet(viewsets.ModelViewSet):
    queryset = Patio.objects.filter(activo=True).order_by('nombre')
    serializer_class = PatioSerializer
    permission_classes = [IsAuthenticated, AccesoDiesel]


class ProveedorDieselViewSet(viewsets.ModelViewSet):
    queryset = ProveedorDiesel.objects.filter(activo=True).order_by('nombre')
    serializer_class = ProveedorDieselSerializer
    permission_classes = [IsAuthenticated, AccesoDiesel]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'rfc']


class UnidadDieselViewSet(viewsets.ModelViewSet):
    serializer_class = UnidadDieselSerializer
    permission_classes = [IsAuthenticated, AccesoDiesel]
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        qs = Unidad.objects.select_related('patio').filter(activo=True).order_by('numero_economico')
        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        return qs


class TotemViewSet(viewsets.ModelViewSet):
    queryset = Totem.objects.select_related('patio').all()
    serializer_class = TotemSerializer
    permission_classes = [IsAuthenticated, AccesoDiesel]

    @action(detail=True, methods=['get'])
    def estado(self, request, pk=None):
        totem = self.get_object()
        return Response(TotemSerializer(totem).data)


class CompraCombustibleViewSet(viewsets.ModelViewSet):
    serializer_class = CompraCombustibleSerializer
    permission_classes = [IsAuthenticated, AccesoDiesel]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha']

    def get_queryset(self):
        qs = CompraCombustible.objects.select_related('patio', 'proveedor').order_by('-fecha')
        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        tipo = self.request.query_params.get('tipo')
        if tipo:
            qs = qs.filter(tipo=tipo)
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(usuario=self.request.user)
        # Actualizar inventario en totem
        try:
            totem = obj.patio.totem
            if obj.tipo == 'diesel':
                totem.cantidad_diesel = (totem.cantidad_diesel or 0) + obj.litros
            elif obj.tipo == 'urea':
                totem.cantidad_urea = (totem.cantidad_urea or 0) + obj.litros
            totem.save(update_fields=['cantidad_diesel', 'cantidad_urea'])
        except Exception:
            pass


class AjusteInventarioViewSet(viewsets.ModelViewSet):
    serializer_class = AjusteInventarioSerializer
    permission_classes = [IsAuthenticated, AccesoDiesel]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha']

    def get_queryset(self):
        qs = AjusteInventario.objects.select_related('patio').order_by('-fecha')
        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)


class CargaDieselViewSet(viewsets.ModelViewSet):
    serializer_class = CargaDieselSerializer
    permission_classes = [IsAuthenticated, AccesoDiesel]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha_carga']

    def get_queryset(self):
        qs = CargaDiesel.objects.select_related('patio', 'unidad').order_by('-fecha_carga')
        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        unidad_id = self.request.query_params.get('unidad')
        if unidad_id:
            qs = qs.filter(unidad_id=unidad_id)
        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha_carga__gte=fecha_desde)
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha_carga__lte=fecha_hasta)
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(usuario=self.request.user)
        # Descontar del totem
        try:
            totem = obj.patio.totem
            totem.cantidad_diesel = max(0, (totem.cantidad_diesel or 0) - (obj.litros_diesel or 0))
            totem.cantidad_urea = max(0, (totem.cantidad_urea or 0) - (obj.litros_urea or 0))
            totem.save(update_fields=['cantidad_diesel', 'cantidad_urea'])
        except Exception:
            pass


class ResumenDieselView(APIView):
    """
    GET /api/v1/diesel/resumen/
    Estado de todos los totems + consumo del mes.
    """
    permission_classes = [IsAuthenticated, AccesoDiesel]

    def get(self, request):
        from django.utils import timezone
        from django.db.models import Sum
        hoy = timezone.now()
        totems = Totem.objects.select_related('patio').all()
        totem_data = TotemSerializer(totems, many=True).data

        consumo_mes = CargaDiesel.objects.filter(
            fecha_carga__year=hoy.year, fecha_carga__month=hoy.month
        ).aggregate(
            diesel=Sum('litros_diesel'),
            urea=Sum('litros_urea'),
        )

        return Response({
            'totems': totem_data,
            'consumo_mes': {
                'litros_diesel': float(consumo_mes['diesel'] or 0),
                'litros_urea': float(consumo_mes['urea'] or 0),
            }
        })
