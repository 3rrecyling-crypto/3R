"""
api/views/compras.py
"""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.pagination import DynamicPagePagination
from api.serializers.compras import (
    ProveedorSerializer, CategoriaSerializer, UnidadMedidaSerializer,
    ArticuloSerializer, ArticuloProveedorSerializer,
    SolicitudCompraSerializer, DetalleSolicitudSerializer,
    OrdenCompraSerializer, DetalleOrdenCompraSerializer,
)
from compras.models import (
    Proveedor, Categoria, UnidadMedida, Articulo,
    ArticuloProveedor, SolicitudCompra, DetalleSolicitud,
    OrdenCompra, DetalleOrdenCompra,
)


class ProveedorViewSet(viewsets.ModelViewSet):
    serializer_class = ProveedorSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['razon_social', 'rfc', 'contacto']

    def get_queryset(self):
        qs = Proveedor.objects.order_by('razon_social')
        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(activo=activo.lower() == 'true')
        return qs


class CategoriaComprasViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]


class UnidadMedidaViewSet(viewsets.ModelViewSet):
    queryset = UnidadMedida.objects.all().order_by('nombre')
    serializer_class = UnidadMedidaSerializer
    permission_classes = [IsAuthenticated]


class ArticuloViewSet(viewsets.ModelViewSet):
    serializer_class = ArticuloSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'sku', 'descripcion']

    def get_queryset(self):
        qs = Articulo.objects.prefetch_related('articuloproveedor_set__proveedor').order_by('nombre')
        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(activo=activo.lower() == 'true')
        tipo = self.request.query_params.get('tipo')
        if tipo:
            qs = qs.filter(tipo=tipo.upper())
        return qs


class SolicitudCompraViewSet(viewsets.ModelViewSet):
    serializer_class = SolicitudCompraSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-id']

    def get_queryset(self):
        qs = SolicitudCompra.objects.prefetch_related('detalles').order_by('-id')
        estatus = self.request.query_params.get('estatus')
        if estatus:
            qs = qs.filter(estatus=estatus.upper())
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(solicitante=self.request.user)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        sol = self.get_object()
        if sol.estatus != 'PENDIENTE':
            return Response({'detail': 'Solo se pueden aprobar solicitudes pendientes.'}, status=400)
        sol.estatus = 'APROBADO'
        sol.aprobado_por = request.user
        from django.utils import timezone
        sol.fecha_aprobacion = timezone.now()
        sol.save(update_fields=['estatus', 'aprobado_por', 'fecha_aprobacion'])
        return Response({'detail': 'Solicitud aprobada.'})

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        sol = self.get_object()
        sol.estatus = 'RECHAZADO'
        sol.save(update_fields=['estatus'])
        return Response({'detail': 'Solicitud rechazada.'})


class OrdenCompraViewSet(viewsets.ModelViewSet):
    serializer_class = OrdenCompraSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-id']

    def get_queryset(self):
        qs = OrdenCompra.objects.prefetch_related('detalles').select_related('proveedor').order_by('-id')
        estatus = self.request.query_params.get('estatus')
        if estatus:
            qs = qs.filter(estatus=estatus.upper())
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    @action(detail=True, methods=['post'])
    def marcar_auditada(self, request, pk=None):
        oc = self.get_object()
        oc.estatus = 'AUDITADO'
        oc.save(update_fields=['estatus'])
        return Response({'detail': 'Orden marcada como auditada.'})
