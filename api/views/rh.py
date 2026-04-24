"""
api/views/rh.py
ViewSets para el módulo RH.
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import DynamicPagePagination
from api.permissions import AccesoRH
from api.serializers.rh import (
    DepartamentoSerializer, PuestoSerializer, MotivoInactivacionSerializer,
    DivisionOperativaSerializer, TipoCargaSerializer, TipoViajeSerializer,
    EmpleadoListSerializer, EmpleadoDetailSerializer,
    HijoSerializer, SalarioSerializer,
    TipoDocumentoOperadorSerializer, DocumentoOperadorSerializer,
    HistorialLaboralSerializer, ContratoSerializer,
    MotivoBajaSerializer, BajaEmpleadoSerializer,
    VacacionSerializer, HistoricoVacacionesSerializer,
    PrestamoSerializer, PagoPrestamoSerializer,
    ControlVacanteSerializer,
)
from RH.models import (
    Departamento, Puesto, MotivoInactivacion,
    DivisionOperativa, TipoCarga, TipoViaje,
    Empleado, Hijo, Salario, TipoDocumentoOperador,
    DocumentoOperador, HistorialLaboral, Contrato,
    MotivoBaja, BajaEmpleado, Vacacion, HistoricoVacaciones,
    Prestamo, PagoPrestamo, ControlVacante,
)


# ─── CATÁLOGOS RH ────────────────────────────────────────────────────────────
class DepartamentoViewSet(viewsets.ModelViewSet):
    queryset = Departamento.objects.all().order_by('nombre')
    serializer_class = DepartamentoSerializer
    permission_classes = [IsAuthenticated, AccesoRH]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']


class PuestoViewSet(viewsets.ModelViewSet):
    queryset = Puesto.objects.all().order_by('nombre')
    serializer_class = PuestoSerializer
    permission_classes = [IsAuthenticated, AccesoRH]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']


class MotivoInactivacionViewSet(viewsets.ModelViewSet):
    queryset = MotivoInactivacion.objects.all()
    serializer_class = MotivoInactivacionSerializer
    permission_classes = [IsAuthenticated, AccesoRH]


class DivisionOperativaViewSet(viewsets.ModelViewSet):
    queryset = DivisionOperativa.objects.all().order_by('nombre')
    serializer_class = DivisionOperativaSerializer
    permission_classes = [IsAuthenticated, AccesoRH]


class TipoCargaViewSet(viewsets.ModelViewSet):
    queryset = TipoCarga.objects.all().order_by('nombre')
    serializer_class = TipoCargaSerializer
    permission_classes = [IsAuthenticated, AccesoRH]


class TipoViajeViewSet(viewsets.ModelViewSet):
    queryset = TipoViaje.objects.all().order_by('nombre')
    serializer_class = TipoViajeSerializer
    permission_classes = [IsAuthenticated, AccesoRH]


class TipoDocumentoOperadorViewSet(viewsets.ModelViewSet):
    queryset = TipoDocumentoOperador.objects.all().order_by('nombre')
    serializer_class = TipoDocumentoOperadorSerializer
    permission_classes = [IsAuthenticated, AccesoRH]


# ─── EMPLEADOS ───────────────────────────────────────────────────────────────
class EmpleadoViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccesoRH]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre', 'apellido', 'numero_empleado', 'email', 'RFC', 'CURP']
    ordering_fields = ['nombre', 'apellido', 'fecha_ingreso', 'numero_empleado']
    ordering = ['apellido', 'nombre']

    def get_serializer_class(self):
        if self.action == 'list':
            return EmpleadoListSerializer
        return EmpleadoDetailSerializer

    def get_queryset(self):
        qs = Empleado.objects.filter(
            eliminado=False
        ).select_related('puesto', 'departamento', 'supervisor').order_by('apellido', 'nombre')

        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(activo=activo.lower() == 'true')

        departamento = self.request.query_params.get('departamento')
        if departamento:
            qs = qs.filter(departamento_id=departamento)

        puesto = self.request.query_params.get('puesto')
        if puesto:
            qs = qs.filter(puesto_id=puesto)

        empresa = self.request.query_params.get('empresa')
        if empresa:
            qs = qs.filter(empresa=empresa)

        division = self.request.query_params.get('division')
        if division:
            qs = qs.filter(division_operativa__id=division)

        return qs

    @action(detail=True, methods=['get'])
    def salarios(self, request, pk=None):
        emp = self.get_object()
        return Response(SalarioSerializer(emp.salarios.order_by('-fecha_efectiva'), many=True).data)

    @action(detail=True, methods=['post'])
    def agregar_salario(self, request, pk=None):
        emp = self.get_object()
        serializer = SalarioSerializer(data={**request.data, 'empleado': emp.pk})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)

    @action(detail=True, methods=['get'])
    def documentos(self, request, pk=None):
        emp = self.get_object()
        return Response(DocumentoOperadorSerializer(emp.documentos.all(), many=True).data)

    @action(detail=True, methods=['get'])
    def historial(self, request, pk=None):
        emp = self.get_object()
        return Response(HistorialLaboralSerializer(emp.historial_laboral.order_by('-fecha_inicio'), many=True).data)

    @action(detail=True, methods=['get'])
    def contratos(self, request, pk=None):
        emp = self.get_object()
        return Response(ContratoSerializer(emp.contratos.order_by('-fecha_inicio'), many=True).data)

    @action(detail=True, methods=['get'])
    def vacaciones(self, request, pk=None):
        emp = self.get_object()
        return Response(VacacionSerializer(emp.vacaciones.order_by('-fecha_solicitud'), many=True).data)

    @action(detail=True, methods=['get'])
    def prestamos(self, request, pk=None):
        emp = self.get_object()
        return Response(PrestamoSerializer(emp.prestamos.order_by('-fecha_solicitud'), many=True).data)

    @action(detail=True, methods=['post'])
    def dar_baja(self, request, pk=None):
        emp = self.get_object()
        if not emp.activo:
            return Response({'detail': 'El empleado ya está dado de baja.'}, status=400)
        serializer = BajaEmpleadoSerializer(data={**request.data, 'empleado': emp.pk})
        serializer.is_valid(raise_exception=True)
        baja = serializer.save(registrado_por=request.user)
        emp.activo = False
        emp.save(update_fields=['activo'])
        return Response(BajaEmpleadoSerializer(baja).data, status=201)

    @action(detail=True, methods=['post'])
    def recontratar(self, request, pk=None):
        emp = self.get_object()
        if emp.activo:
            return Response({'detail': 'El empleado ya está activo.'}, status=400)
        emp.activo = True
        emp.save(update_fields=['activo'])
        return Response({'detail': 'Empleado recontratado.', 'id': str(emp.pk)})


# ─── BAJAS ───────────────────────────────────────────────────────────────────
class MotivoBajaViewSet(viewsets.ModelViewSet):
    """Árbol jerárquico de motivos de baja."""
    permission_classes = [IsAuthenticated, AccesoRH]

    def get_queryset(self):
        tipo = self.request.query_params.get('tipo')
        qs = MotivoBaja.objects.filter(activo=True)
        if tipo:
            qs = qs.filter(tipo_motivo=tipo.upper())
        return qs.order_by('nombre')

    def get_serializer_class(self):
        return MotivoBajaSerializer


class BajaEmpleadoViewSet(viewsets.ModelViewSet):
    serializer_class = BajaEmpleadoSerializer
    permission_classes = [IsAuthenticated, AccesoRH]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha_baja']

    def get_queryset(self):
        qs = BajaEmpleado.objects.select_related('empleado').order_by('-fecha_baja')
        empresa = self.request.query_params.get('empresa')
        if empresa:
            qs = qs.filter(empleado__empresa=empresa)
        return qs


# ─── VACACIONES ──────────────────────────────────────────────────────────────
class VacacionViewSet(viewsets.ModelViewSet):
    serializer_class = VacacionSerializer
    permission_classes = [IsAuthenticated, AccesoRH]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha_solicitud']

    def get_queryset(self):
        qs = Vacacion.objects.select_related('empleado').order_by('-fecha_solicitud')
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado.upper())
        empleado_id = self.request.query_params.get('empleado')
        if empleado_id:
            qs = qs.filter(empleado_id=empleado_id)
        return qs

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        vacacion = self.get_object()
        if vacacion.estado != 'PENDIENTE':
            return Response({'detail': 'Solo se pueden aprobar vacaciones pendientes.'}, status=400)
        vacacion.estado = 'APROBADO'
        vacacion.aprobado_por = request.user
        from django.utils import timezone
        vacacion.fecha_aprobacion = timezone.now()
        vacacion.save(update_fields=['estado', 'aprobado_por', 'fecha_aprobacion'])
        return Response({'detail': 'Vacaciones aprobadas.'})

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        vacacion = self.get_object()
        vacacion.estado = 'RECHAZADO'
        vacacion.save(update_fields=['estado'])
        return Response({'detail': 'Vacaciones rechazadas.'})


class HistoricoVacacionesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HistoricoVacacionesSerializer
    permission_classes = [IsAuthenticated, AccesoRH]

    def get_queryset(self):
        qs = HistoricoVacaciones.objects.select_related('empleado').all()
        empleado_id = self.request.query_params.get('empleado')
        if empleado_id:
            qs = qs.filter(empleado_id=empleado_id)
        return qs


# ─── PRÉSTAMOS ───────────────────────────────────────────────────────────────
class PrestamoViewSet(viewsets.ModelViewSet):
    serializer_class = PrestamoSerializer
    permission_classes = [IsAuthenticated, AccesoRH]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha_solicitud']

    def get_queryset(self):
        qs = Prestamo.objects.select_related('empleado').prefetch_related('pagos').order_by('-fecha_solicitud')
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado.upper())
        empleado_id = self.request.query_params.get('empleado')
        if empleado_id:
            qs = qs.filter(empleado_id=empleado_id)
        return qs

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        prestamo = self.get_object()
        if prestamo.estado != 'PENDIENTE':
            return Response({'detail': 'Solo se pueden aprobar préstamos pendientes.'}, status=400)
        prestamo.estado = 'APROBADO'
        prestamo.aprobado_por = request.user
        prestamo.save(update_fields=['estado', 'aprobado_por'])
        return Response({'detail': 'Préstamo aprobado.'})

    @action(detail=True, methods=['post'])
    def registrar_pago(self, request, pk=None):
        prestamo = self.get_object()
        serializer = PagoPrestamoSerializer(data={**request.data, 'prestamo': prestamo.pk})
        serializer.is_valid(raise_exception=True)
        pago = serializer.save(registrado_por=request.user)
        # Actualizar saldo
        prestamo.monto_pagado = (prestamo.monto_pagado or 0) + pago.monto_pagado
        if prestamo.monto_pagado >= prestamo.monto_total:
            prestamo.estado = 'LIQUIDADO'
        else:
            prestamo.estado = 'EN_CURSO'
        prestamo.save(update_fields=['monto_pagado', 'estado'])
        return Response(PagoPrestamoSerializer(pago).data, status=201)


# ─── CONTROL VACANTES ─────────────────────────────────────────────────────────
class ControlVacanteViewSet(viewsets.ModelViewSet):
    queryset = ControlVacante.objects.select_related('puesto', 'division').all()
    serializer_class = ControlVacanteSerializer
    permission_classes = [IsAuthenticated, AccesoRH]
    filter_backends = [filters.OrderingFilter]
    ordering = ['empresa', 'puesto__nombre']

    def get_queryset(self):
        qs = super().get_queryset()
        empresa = self.request.query_params.get('empresa')
        if empresa:
            qs = qs.filter(empresa=empresa)
        return qs


# ─── DASHBOARD RH ────────────────────────────────────────────────────────────
class DashboardRHView(APIView):
    permission_classes = [IsAuthenticated, AccesoRH]

    def get(self, request):
        from datetime import date
        hoy = date.today()
        total = Empleado.objects.filter(eliminado=False, activo=True).count()
        bajas_mes = BajaEmpleado.objects.filter(
            fecha_baja__year=hoy.year, fecha_baja__month=hoy.month
        ).count()
        vacaciones_pendientes = Vacacion.objects.filter(estado='PENDIENTE').count()
        prestamos_activos = Prestamo.objects.filter(estado__in=['APROBADO', 'EN_CURSO']).count()

        # Cumpleaños del mes
        cumples = Empleado.objects.filter(
            eliminado=False, activo=True,
            fecha_nacimiento__month=hoy.month
        ).order_by('fecha_nacimiento__day').values(
            'id', 'nombre', 'apellido', 'fecha_nacimiento'
        )[:10]

        return Response({
            'total_empleados_activos': total,
            'bajas_este_mes': bajas_mes,
            'vacaciones_pendientes': vacaciones_pendientes,
            'prestamos_activos': prestamos_activos,
            'cumpleanos_del_mes': list(cumples),
        })
