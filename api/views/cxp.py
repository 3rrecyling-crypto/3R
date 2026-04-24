"""
api/views/cxp.py
"""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import DynamicPagePagination
from api.serializers.cxp import FacturaCxPSerializer, PagoSerializer
from cuentas_por_pagar.models import Factura, Pago


class FacturaCxPViewSet(viewsets.ModelViewSet):
    serializer_class = FacturaCxPSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['folio_cxp', 'numero_factura', 'proveedor__razon_social']
    ordering = ['-id']

    def get_queryset(self):
        qs = Factura.objects.select_related('proveedor').prefetch_related('pagos').order_by('-id')
        estatus = self.request.query_params.get('estatus')
        if estatus:
            qs = qs.filter(estatus=estatus.upper())
        pagada = self.request.query_params.get('pagada')
        if pagada is not None:
            qs = qs.filter(pagada=pagada.lower() == 'true')
        proveedor_id = self.request.query_params.get('proveedor')
        if proveedor_id:
            qs = qs.filter(proveedor_id=proveedor_id)
        return qs

    @action(detail=True, methods=['post'])
    def registrar_pago(self, request, pk=None):
        factura = self.get_object()
        serializer = PagoSerializer(data={**request.data, 'factura': factura.pk})
        serializer.is_valid(raise_exception=True)
        pago = serializer.save(registrado_por=request.user)

        # Actualizar estado de la factura
        total_pagado = sum(p.monto_pagado for p in factura.pagos.all())
        if total_pagado >= factura.monto:
            factura.pagada = True
            factura.estatus = 'PAGADA'
        else:
            factura.estatus = 'PAGO_PARCIAL'
        factura.save(update_fields=['pagada', 'estatus'])

        return Response(PagoSerializer(pago).data, status=201)


class AlertasCxPView(APIView):
    """
    GET /api/v1/cxp/alertas/
    Facturas por vencer en los próximos N días (configurable).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from api.models import ConfiguracionSistema
        cfg = ConfiguracionSistema.get_config()
        dias = cfg.cxp_dias_alerta_vencimiento

        hoy = timezone.now().date()
        from datetime import timedelta
        limite = hoy + timedelta(days=dias)

        por_vencer = Factura.objects.filter(
            pagada=False,
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=limite,
        ).select_related('proveedor').order_by('fecha_vencimiento')

        vencidas = Factura.objects.filter(
            pagada=False,
            fecha_vencimiento__lt=hoy,
        ).select_related('proveedor').order_by('fecha_vencimiento')

        return Response({
            'por_vencer_en_%d_dias' % dias: FacturaCxPSerializer(por_vencer, many=True).data,
            'vencidas': FacturaCxPSerializer(vencidas, many=True).data,
            'total_por_vencer': por_vencer.count(),
            'total_vencidas': vencidas.count(),
        })
