"""
api/views/ternium.py
ViewSets y vistas para todo el módulo operativo Ternium.
"""
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import DynamicPagePagination
from api.permissions import AccesoRemisiones, AccesoCatalogos, AccesoReportes
from api.serializers.ternium import (
    OrigenSerializer, EmpresaSerializer, LineaTransporteSerializer,
    OperadorSerializer, MaterialSerializer, UnidadSerializer,
    ContenedorSerializer, LugarSerializer, ClienteSerializer,
    RemisionListSerializer, RemisionDetailSerializer,
    DetalleRemisionSerializer, EvidenciaRemisionSerializer,
    HistorialRemisionSerializer, RegistroLogisticoSerializer,
    EntradaMaquilaSerializer, InventarioPatiSerializer,
    DescargaSerializer, PlasticoSerializer, ControlTarimaSerializer,
    ConfiguracionManifiestoSerializer, ControlManifiestoTraneSerializer,
    ManifiestoResiduosSerializer,
    PrecioMedlineSerializer, ConfiguracionAlertaMermaSerializer,
    DestinatarioAlertaMermaSerializer,
)
from ternium.models import (
    Origen, Empresa, LineaTransporte, Operador, Material, Unidad,
    Contenedor, Lugar, Cliente, Remision, DetalleRemision,
    EvidenciaRemision, HistorialRemision, RegistroLogistico,
    EntradaMaquila, InventarioPatio, Descarga, Plastico,
    ControlTarima, ConfiguracionManifiesto, ControlManifiestoTrane,
    ManifiestoResiduos,
    PrecioMedline, ConfiguracionAlertaMerma, DestinatarioAlertaMerma,
)


# ─── HELPER ──────────────────────────────────────────────────────────────────
def _empresas_autorizadas(user):
    """Retorna QS de empresas que el usuario puede ver."""
    if user.is_superuser:
        return Empresa.objects.all()
    try:
        return user.profile.empresas_autorizadas.all()
    except Exception:
        return Empresa.objects.none()


# ─── CATÁLOGOS ────────────────────────────────────────────────────────────────
class OrigenViewSet(viewsets.ModelViewSet):
    queryset = Origen.objects.all().order_by('nombre')
    serializer_class = OrigenSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre']
    ordering_fields = ['nombre']
    pagination_class = DynamicPagePagination


class EmpresaViewSet(viewsets.ModelViewSet):
    serializer_class = EmpresaSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre', 'prefijo']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        return _empresas_autorizadas(self.request.user).prefetch_related('origenes')


class LineaTransporteViewSet(viewsets.ModelViewSet):
    serializer_class = LineaTransporteSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        return LineaTransporte.objects.filter(empresas__in=empresas).distinct().order_by('nombre')


class OperadorViewSet(viewsets.ModelViewSet):
    serializer_class = OperadorSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'folio']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        return Operador.objects.filter(empresas__in=empresas).distinct().order_by('nombre')

    def perform_destroy(self, instance):
        """Da de baja en vez de borrar.

        La FK de Remision es SET_NULL: borrar el operador dejaría sin nombre a
        todas sus remisiones y ese dato no se puede recuperar.
        """
        instance.activo = False
        instance.save(update_fields=['activo'])


class MaterialViewSet(viewsets.ModelViewSet):
    serializer_class = MaterialSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'clave_sat']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        return Material.objects.filter(empresas__in=empresas).distinct().order_by('nombre')


class UnidadViewSet(viewsets.ModelViewSet):
    serializer_class = UnidadSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['internal_id', 'license_plate', 'vin']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        qs = Unidad.objects.filter(empresas__in=empresas).distinct().order_by('internal_id')
        # Filtros opcionales
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(operational_status=status_filter)
        tipo = self.request.query_params.get('tipo')
        if tipo:
            qs = qs.filter(asset_type=tipo)
        return qs


class ContenedorViewSet(viewsets.ModelViewSet):
    serializer_class = ContenedorSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'placas']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        return Contenedor.objects.filter(empresas__in=empresas).distinct().order_by('nombre')


class LugarViewSet(viewsets.ModelViewSet):
    serializer_class = LugarSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre', 'rfc', 'razon_social']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        qs = Lugar.objects.filter(empresas__in=empresas).distinct().order_by('nombre')
        tipo = self.request.query_params.get('tipo')
        if tipo:
            qs = qs.filter(tipo=tipo)
        es_patio = self.request.query_params.get('es_patio')
        if es_patio is not None:
            qs = qs.filter(es_patio=es_patio.lower() == 'true')
        return qs


class ClienteViewSet(viewsets.ModelViewSet):
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        return Cliente.objects.filter(empresas__in=empresas).distinct().order_by('nombre')

    def perform_create(self, serializer):
        cliente = serializer.save()
        # Si se dio de alta sin especificar empresas, asociarlo a las autorizadas del
        # usuario para que sea visible (get_queryset filtra por empresas). Evita crear
        # "clientes fantasma" que no aparecerían en el catálogo tras guardarse.
        if not cliente.empresas.exists():
            cliente.empresas.set(_empresas_autorizadas(self.request.user))


class ManifiestoClienteViewSet(viewsets.ModelViewSet):
    """Catálogo de clientes para el COMBOBOX del manifiesto oficial (campo generador).

    A diferencia de ClienteViewSet (gestión de catálogos: exige `acceso_catalogos` y
    filtra por empresa), aquí basta con estar AUTENTICADO y se muestra el catálogo
    completo. Así los usuarios del portal de manifiestos pueden listar / dar de alta /
    editar clientes aunque NO tengan permiso de entrar a la sección de catálogos.
    Eliminar sí queda restringido a administradores de catálogos.
    """
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']
    pagination_class = DynamicPagePagination
    queryset = Cliente.objects.all().order_by('nombre')

    def perform_destroy(self, instance):
        user = self.request.user
        if not (user.is_superuser or user.has_perm('ternium.acceso_catalogos')):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo administradores de catálogos pueden eliminar clientes.")
        instance.delete()


# ─── REMISIONES ──────────────────────────────────────────────────────────────
class RemisionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccesoRemisiones]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['remision', 'folio', 'folio_medline', 'folio_ld', 'folio_dlv']
    ordering_fields = ['fecha', 'remision', 'status']
    ordering = ['-fecha']

    def get_serializer_class(self):
        if self.action == 'list':
            return RemisionListSerializer
        return RemisionDetailSerializer

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        qs = Remision.objects.filter(empresa__in=empresas).select_related(
            'empresa', 'operador', 'origen', 'destino', 'cliente',
            'linea_transporte', 'unidad', 'contenedor',
        ).order_by('-fecha')

        # ── Filtros ──────────────────────────────────────────────────────────
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)

        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        origen_id = self.request.query_params.get('origen')
        if origen_id:
            qs = qs.filter(origen_id=origen_id)

        destino_id = self.request.query_params.get('destino')
        if destino_id:
            qs = qs.filter(destino_id=destino_id)

        operador_id = self.request.query_params.get('operador')
        if operador_id:
            qs = qs.filter(operador_id=operador_id)

        material_id = self.request.query_params.get('material')
        if material_id:
            qs = qs.filter(detalles__material_id=material_id).distinct()

        medline = self.request.query_params.get('medline')
        if medline == 'true':
            qs = qs.filter(origen__nombre__icontains='MEDLINE')

        return qs

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        """POST /api/v1/remisiones/{id}/cancelar/ — Cancela la remisión."""
        remision = self.get_object()
        if remision.status == 'CANCELADO':
            return Response({'detail': 'Ya está cancelada.'}, status=400)
        try:
            from ternium.api_views import cancelar_remision as _cancelar
            # reutilizar lógica existente
            from django.test import RequestFactory
            # invocamos la lógica interna directamente
            from ternium import api_views as av
            folio_liberado = remision.folio_medline
            remision.status = 'CANCELADO'
            remision.folio_medline = None
            remision.save()
            # Folio Medline manual: al cancelar se LIBERA (queda pendiente), pero NO
            # se renumera — renumerar reescribiría folios que el usuario tecleó a mano.
            # if folio_liberado:
            #     av._renumerar_folios_medline(folio_liberado)
            return Response({'detail': 'Remisión cancelada.', 'id': remision.pk})
        except Exception as e:
            return Response({'detail': str(e)}, status=500)

    @action(detail=True, methods=['post'])
    def auditar(self, request, pk=None):
        """POST /api/v1/remisiones/{id}/auditar/"""
        remision = self.get_object()
        if not (request.user.is_superuser or request.user.has_perm('ternium.can_audit_remision')):
            return Response({'detail': 'Sin permisos para auditar.'}, status=403)
        if remision.status != 'TERMINADO':
            return Response({'detail': 'Solo se pueden auditar remisiones TERMINADAS.'}, status=400)
        remision.status = 'AUDITADO'
        remision.save(update_fields=['status'])
        return Response({'detail': 'Remisión auditada.', 'status': 'AUDITADO'})

    @action(detail=True, methods=['get'])
    def catalogos_disponibles(self, request, pk=None):
        """GET /api/v1/remisiones/{empresa_id}/catalogos/ — catálogos filtrados por empresa."""
        empresa_id = pk
        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            return Response({'detail': 'Empresa no encontrada.'}, status=404)
        return Response({
            'operadores': OperadorSerializer(
                Operador.objects.filter(empresas=empresa, activo=True), many=True
            ).data,
            'lineas': LineaTransporteSerializer(
                LineaTransporte.objects.filter(empresas=empresa), many=True
            ).data,
            'unidades': UnidadSerializer(
                Unidad.objects.filter(empresas=empresa), many=True
            ).data,
            'contenedores': ContenedorSerializer(
                Contenedor.objects.filter(empresas=empresa), many=True
            ).data,
            'materiales': MaterialSerializer(
                Material.objects.filter(empresas=empresa), many=True
            ).data,
            'lugares': LugarSerializer(
                Lugar.objects.filter(empresas=empresa), many=True
            ).data,
        })


# ─── REGISTRO LOGÍSTICO ──────────────────────────────────────────────────────
class RegistroLogisticoViewSet(viewsets.ModelViewSet):
    serializer_class = RegistroLogisticoSerializer
    permission_classes = [IsAuthenticated, AccesoRemisiones]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['remision__remision', 'boleta_bascula']
    ordering = ['-fecha_carga']

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        return RegistroLogistico.objects.filter(
            remision__empresa__in=empresas
        ).select_related('remision').order_by('-fecha_carga')


# ─── ENTRADA MAQUILA ─────────────────────────────────────────────────────────
class EntradaMaquilaViewSet(viewsets.ModelViewSet):
    serializer_class = EntradaMaquilaSerializer
    permission_classes = [IsAuthenticated, AccesoRemisiones]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['c_id_remito', 'num_boleta_remision']
    ordering = ['-fecha_ingreso']

    def get_queryset(self):
        qs = EntradaMaquila.objects.all().order_by('-fecha_ingreso')
        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha_ingreso__gte=fecha_desde)
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha_ingreso__lte=fecha_hasta)
        return qs


# ─── INVENTARIO PATIO ────────────────────────────────────────────────────────
class InventarioPatioViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InventarioPatiSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        qs = InventarioPatio.objects.select_related('patio', 'material').order_by('patio__nombre')
        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        material_id = self.request.query_params.get('material')
        if material_id:
            qs = qs.filter(material_id=material_id)
        return qs

    @action(detail=False, methods=['get'])
    def resumen(self, request):
        """GET /api/v1/inventario-patio/resumen/ — total KG y TON por patio."""
        qs = self.get_queryset()
        from collections import defaultdict
        resumen = defaultdict(lambda: {'patio': '', 'total_kg': 0, 'materiales': []})
        for inv in qs:
            patio_id = inv.patio_id
            resumen[patio_id]['patio'] = inv.patio.nombre
            resumen[patio_id]['total_kg'] += float(inv.cantidad)
            resumen[patio_id]['materiales'].append({
                'material': inv.material.nombre,
                'cantidad_kg': float(inv.cantidad),
                'cantidad_ton': round(float(inv.cantidad) / 1000, 3),
            })
        data = []
        for patio_id, info in resumen.items():
            info['total_ton'] = round(info['total_kg'] / 1000, 3)
            data.append(info)
        return Response(data)


# ─── DESCARGAS ───────────────────────────────────────────────────────────────
class DescargaViewSet(viewsets.ModelViewSet):
    serializer_class = DescargaSerializer
    permission_classes = [IsAuthenticated, AccesoRemisiones]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha_descarga']

    def get_queryset(self):
        qs = Descarga.objects.order_by('-fecha_descarga')
        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha_descarga__gte=fecha_desde)
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha_descarga__lte=fecha_hasta)
        return qs


# ─── PLÁSTICO ────────────────────────────────────────────────────────────────
class PlasticoViewSet(viewsets.ModelViewSet):
    serializer_class = PlasticoSerializer
    permission_classes = [IsAuthenticated, AccesoRemisiones]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['remision', 'folio']
    ordering = ['-fecha']

    def get_queryset(self):
        empresas = _empresas_autorizadas(self.request.user)
        qs = Plastico.objects.filter(empresa__in=empresas).order_by('-fecha')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        return qs


# ─── CONTROL TARIMAS ─────────────────────────────────────────────────────────
class ControlTarimaViewSet(viewsets.ModelViewSet):
    serializer_class = ControlTarimaSerializer
    permission_classes = [IsAuthenticated, AccesoRemisiones]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha']

    def get_queryset(self):
        qs = ControlTarima.objects.order_by('-fecha')
        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        return qs


# ─── MANIFIESTOS TRANE ───────────────────────────────────────────────────────
class ConfiguracionManifiestoViewSet(viewsets.ModelViewSet):
    queryset = ConfiguracionManifiesto.objects.select_related('origen', 'material').all()
    serializer_class = ConfiguracionManifiestoSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]


class ControlManifiestoTraneViewSet(viewsets.ModelViewSet):
    serializer_class = ControlManifiestoTraneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha_captura']

    def get_queryset(self):
        qs = ControlManifiestoTrane.objects.order_by('-fecha_captura')
        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha_captura__gte=fecha_desde)
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha_captura__lte=fecha_hasta)
        return qs


class ManifiestoResiduosViewSet(viewsets.ModelViewSet):
    """CRUD del manifiesto oficial de residuos de manejo especial (formato SMA)."""
    serializer_class = ManifiestoResiduosSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DynamicPagePagination

    def get_queryset(self):
        qs = ManifiestoResiduos.objects.all().order_by('-creado_en', '-id')
        buscar = self.request.query_params.get('buscar')
        if buscar:
            qs = qs.filter(no_manifiesto__icontains=buscar)
        return qs

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)


class CodigoPostalView(APIView):
    """Búsqueda por código postal usando el catálogo SEPOMEX/SAT ya cargado en la
    app facturacion. GET ?cp=64000 → { cp, estado, municipio, colonias: [...] }.
    Autocompleta el domicilio en el manifiesto (municipio) y sugiere colonias."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from facturacion.models import Colonia, CodigoPostalFiscal
        cp = "".join(ch for ch in (request.query_params.get("cp") or "") if ch.isdigit())[:5]
        if len(cp) < 5:
            return Response({"cp": cp, "estado": "", "municipio": "", "colonias": []})
        cpf = (CodigoPostalFiscal.objects
               .select_related("estado", "municipio")
               .filter(codigo=cp).first())
        colonias = list(
            Colonia.objects.filter(codigo_postal=cp)
            .values_list("nombre", flat=True).distinct().order_by("nombre")
        )
        return Response({
            "cp": cp,
            "estado": cpf.estado.nombre if cpf else "",
            "municipio": cpf.municipio.nombre if cpf else "",
            "colonias": colonias,
        })


# ─── MEDLINE ─────────────────────────────────────────────────────────────────
class PrecioMedlineViewSet(viewsets.ModelViewSet):
    queryset = PrecioMedline.objects.all().order_by('-mes')
    serializer_class = PrecioMedlineSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]


# ─── ALERTAS MERMA ───────────────────────────────────────────────────────────
class ConfiguracionAlertaMermaViewSet(viewsets.ModelViewSet):
    queryset = ConfiguracionAlertaMerma.objects.select_related('material').all()
    serializer_class = ConfiguracionAlertaMermaSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]


class DestinatarioAlertaMermaViewSet(viewsets.ModelViewSet):
    queryset = DestinatarioAlertaMerma.objects.all().order_by('email')
    serializer_class = DestinatarioAlertaMermaSerializer
    permission_classes = [IsAuthenticated, AccesoCatalogos]


# ─── REPORTES / KPIs ─────────────────────────────────────────────────────────
from rest_framework.views import APIView


class ReporteKPIView(APIView):
    """
    GET /api/v1/reportes/kpi/
    Parámetros: empresa, fecha_desde, fecha_hasta
    Retorna KPIs clave para el dashboard.
    """
    permission_classes = [IsAuthenticated, AccesoReportes]

    def get(self, request):
        empresas = _empresas_autorizadas(request.user)
        qs = Remision.objects.filter(empresa__in=empresas)

        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')
        empresa_id = request.query_params.get('empresa')

        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        total = qs.count()
        por_status = {}
        for s in ['PENDIENTE', 'TERMINADO', 'AUDITADO', 'CANCELADO']:
            por_status[s] = qs.filter(status=s).count()

        # Peso total (suma de DetalleRemision)
        from ternium.models import DetalleRemision
        detalles_qs = DetalleRemision.objects.filter(remision__in=qs)
        peso_carga = detalles_qs.aggregate(total=Sum('peso_ld'))['total'] or 0
        peso_descarga = detalles_qs.aggregate(total=Sum('peso_dlv'))['total'] or 0
        merma_abs = float(peso_carga) - float(peso_descarga)
        merma_pct = (merma_abs / float(peso_carga) * 100) if peso_carga else 0

        return Response({
            'total_remisiones': total,
            'por_status': por_status,
            'peso_carga_ton': round(float(peso_carga) / 1000, 3),
            'peso_descarga_ton': round(float(peso_descarga) / 1000, 3),
            'merma_absoluta_ton': round(merma_abs / 1000, 3),
            'merma_porcentaje': round(merma_pct, 2),
        })


class CatalogosEmpresaView(APIView):
    """
    GET /api/v1/catalogos/empresa/{empresa_id}/
    Devuelve todos los catálogos filtrados por empresa para poblar formularios.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, empresa_id):
        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            return Response({'detail': 'Empresa no encontrada.'}, status=404)

        return Response({
            'operadores': OperadorSerializer(
                Operador.objects.filter(empresas=empresa, activo=True).order_by('nombre'), many=True
            ).data,
            'lineas_transporte': LineaTransporteSerializer(
                LineaTransporte.objects.filter(empresas=empresa).order_by('nombre'), many=True
            ).data,
            'unidades': UnidadSerializer(
                Unidad.objects.filter(empresas=empresa).order_by('internal_id'), many=True
            ).data,
            'contenedores': ContenedorSerializer(
                Contenedor.objects.filter(empresas=empresa).order_by('nombre'), many=True
            ).data,
            'materiales': MaterialSerializer(
                Material.objects.filter(empresas=empresa).order_by('nombre'), many=True
            ).data,
            'lugares_origen': LugarSerializer(
                Lugar.objects.filter(empresas=empresa, tipo__in=['ORIGEN', 'AMBOS']).order_by('nombre'), many=True
            ).data,
            'lugares_destino': LugarSerializer(
                Lugar.objects.filter(empresas=empresa, tipo__in=['DESTINO', 'AMBOS']).order_by('nombre'), many=True
            ).data,
            'clientes': ClienteSerializer(
                Cliente.objects.filter(empresas=empresa).order_by('nombre'), many=True
            ).data,
        })
