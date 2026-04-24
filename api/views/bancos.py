"""
api/views/bancos.py
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import DynamicPagePagination
from api.permissions import AccesoBancos
from api.serializers.bancos import (
    CuentaSerializer, UnidadNegocioSerializer, OperacionSerializer,
    CategoriaSerializer, SubCategoriaSerializer, TerceroSerializer,
    MovimientoSerializer, ResumenMensualSerializer, ComprobanteFiscalSerializer,
)
from flujo_bancos.models import (
    Cuenta, UnidadNegocio, Operacion, Categoria, SubCategoria,
    Movimiento, Tercero, ResumenMensual, ComprobanteFiscal,
)


class CuentaViewSet(viewsets.ModelViewSet):
    queryset = Cuenta.objects.all().order_by('nombre')
    serializer_class = CuentaSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]

    @action(detail=True, methods=['get'])
    def movimientos(self, request, pk=None):
        cuenta = self.get_object()
        qs = cuenta.movimientos.order_by('-fecha')
        fecha_desde = request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        fecha_hasta = request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        return Response(MovimientoSerializer(qs, many=True).data)


class UnidadNegocioViewSet(viewsets.ModelViewSet):
    queryset = UnidadNegocio.objects.all().order_by('nombre')
    serializer_class = UnidadNegocioSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]


class OperacionViewSet(viewsets.ModelViewSet):
    queryset = Operacion.objects.all().order_by('nombre')
    serializer_class = OperacionSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]


class SubCategoriaViewSet(viewsets.ModelViewSet):
    serializer_class = SubCategoriaSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]

    def get_queryset(self):
        qs = SubCategoria.objects.select_related('categoria').order_by('categoria__nombre', 'nombre')
        cat_id = self.request.query_params.get('categoria')
        if cat_id:
            qs = qs.filter(categoria_id=cat_id)
        return qs


class TerceroViewSet(viewsets.ModelViewSet):
    queryset = Tercero.objects.all().order_by('nombre')
    serializer_class = TerceroSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']


class MovimientoViewSet(viewsets.ModelViewSet):
    serializer_class = MovimientoSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['concepto', 'tercero__nombre']
    ordering = ['-fecha']

    def get_queryset(self):
        qs = Movimiento.objects.select_related(
            'cuenta', 'operacion', 'categoria', 'subcategoria', 'tercero'
        ).order_by('-fecha')

        cuenta_id = self.request.query_params.get('cuenta')
        if cuenta_id:
            qs = qs.filter(cuenta_id=cuenta_id)

        estatus = self.request.query_params.get('estatus')
        if estatus:
            qs = qs.filter(estatus=estatus.upper())

        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)

        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        tipo = self.request.query_params.get('tipo')  # 'ingreso' | 'egreso'
        if tipo == 'ingreso':
            qs = qs.filter(abono__gt=0)
        elif tipo == 'egreso':
            qs = qs.filter(cargo__gt=0)

        return qs


class ResumenMensualViewSet(viewsets.ModelViewSet):
    queryset = ResumenMensual.objects.all().order_by('-periodo')
    serializer_class = ResumenMensualSerializer
    permission_classes = [IsAuthenticated, AccesoBancos]


class ResumenBancosView(APIView):
    """GET /api/v1/bancos/resumen/ — saldos actuales de todas las cuentas."""
    permission_classes = [IsAuthenticated, AccesoBancos]

    def get(self, request):
        cuentas = Cuenta.objects.all()
        total_mxn = 0
        total_usd = 0
        detalle = []
        for c in cuentas:
            saldo = float(c.saldo_actual)
            detalle.append({
                'id': c.id,
                'nombre': c.nombre,
                'moneda': c.moneda,
                'saldo': saldo,
            })
            if c.moneda == 'MXN':
                total_mxn += saldo
            else:
                total_usd += saldo
        return Response({
            'total_mxn': round(total_mxn, 2),
            'total_usd': round(total_usd, 2),
            'cuentas': detalle,
        })
