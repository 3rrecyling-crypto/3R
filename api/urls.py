"""
api/urls.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Router DRF completo para todo el sistema 3R.
Prefijo base: /api/v1/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# ── Auth ──────────────────────────────────────────────
from api.views.auth import (
    LoginView, LogoutView, MeView,
    ChangePasswordView, UsuariosAdminView, UsuarioPermisosView,
)

# ── Configuración ─────────────────────────────────────
from api.views.config import (
    ConfiguracionView, ConfiguracionModulosView, ConfiguracionUIView,
)

# ── Ternium / Operaciones ─────────────────────────────
from api.views.ternium import (
    OrigenViewSet, EmpresaViewSet, LineaTransporteViewSet,
    OperadorViewSet, MaterialViewSet, UnidadViewSet,
    ContenedorViewSet, LugarViewSet, ClienteViewSet, ManifiestoClienteViewSet,
    RemisionViewSet, RegistroLogisticoViewSet, EntradaMaquilaViewSet,
    InventarioPatioViewSet, DescargaViewSet, PlasticoViewSet,
    ControlTarimaViewSet, ConfiguracionManifiestoViewSet,
    ControlManifiestoTraneViewSet, ManifiestoResiduosViewSet, PrecioMedlineViewSet,
    ConfiguracionAlertaMermaViewSet, DestinatarioAlertaMermaViewSet,
    ReporteKPIView, CatalogosEmpresaView, CodigoPostalView,
)

# ── RH ────────────────────────────────────────────────
from api.views.rh import (
    DepartamentoViewSet, PuestoViewSet, MotivoInactivacionViewSet,
    DivisionOperativaViewSet, TipoCargaViewSet, TipoViajeViewSet,
    TipoDocumentoOperadorViewSet, EmpleadoViewSet,
    MotivoBajaViewSet, BajaEmpleadoViewSet,
    VacacionViewSet, HistoricoVacacionesViewSet,
    PrestamoViewSet, ControlVacanteViewSet, DashboardRHView,
    PlantillaContratoViewSet, ContratoGeneradoViewSet,
)

# ── Bancos ────────────────────────────────────────────
from api.views.bancos import (
    CuentaViewSet, UnidadNegocioViewSet, OperacionViewSet,
    CategoriaViewSet, SubCategoriaViewSet, TerceroViewSet,
    MovimientoViewSet, ResumenMensualViewSet, ResumenBancosView,
)

# ── Compras ───────────────────────────────────────────
from api.views.compras import (
    ProveedorViewSet, CategoriaComprasViewSet, UnidadMedidaViewSet,
    ArticuloViewSet, SolicitudCompraViewSet, OrdenCompraViewSet,
)

# ── CxP ───────────────────────────────────────────────
from api.views.cxp import FacturaCxPViewSet, AlertasCxPView

# ── Diesel ────────────────────────────────────────────
from api.views.diesel import (
    PatioViewSet, ProveedorDieselViewSet, UnidadDieselViewSet,
    TotemViewSet, CompraCombustibleViewSet, AjusteInventarioViewSet,
    CargaDieselViewSet, ResumenDieselView,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
router = DefaultRouter()

# ── Catálogos base ───────────────────────────────────
router.register(r'origenes',        OrigenViewSet,          basename='origen')
router.register(r'empresas',        EmpresaViewSet,         basename='empresa')
router.register(r'lineas-transporte', LineaTransporteViewSet, basename='linea-transporte')
router.register(r'operadores',      OperadorViewSet,        basename='operador')
router.register(r'materiales',      MaterialViewSet,        basename='material')
router.register(r'unidades',        UnidadViewSet,          basename='unidad')
router.register(r'contenedores',    ContenedorViewSet,      basename='contenedor')
router.register(r'lugares',         LugarViewSet,           basename='lugar')
router.register(r'clientes',        ClienteViewSet,         basename='cliente')
router.register(r'manifiesto-clientes', ManifiestoClienteViewSet, basename='manifiesto-cliente')

# ── Operaciones ──────────────────────────────────────
router.register(r'remisiones',          RemisionViewSet,            basename='remision')
router.register(r'registro-logistico',  RegistroLogisticoViewSet,   basename='registro-logistico')
router.register(r'entradas-maquila',    EntradaMaquilaViewSet,      basename='entrada-maquila')
router.register(r'inventario-patio',    InventarioPatioViewSet,     basename='inventario-patio')
router.register(r'descargas',           DescargaViewSet,            basename='descarga')
router.register(r'plastico',            PlasticoViewSet,            basename='plastico')
router.register(r'control-tarimas',     ControlTarimaViewSet,       basename='control-tarima')

# ── Manifiestos / TRANE ──────────────────────────────
router.register(r'configuracion-manifiesto',  ConfiguracionManifiestoViewSet,  basename='config-manifiesto')
router.register(r'manifiestos-trane',         ControlManifiestoTraneViewSet,   basename='manifiesto-trane')
router.register(r'manifiestos-residuos',      ManifiestoResiduosViewSet,       basename='manifiesto-residuos')

# ── Medline ──────────────────────────────────────────
router.register(r'precios-medline',           PrecioMedlineViewSet,            basename='precio-medline')

# ── Alertas merma ─────────────────────────────────────
router.register(r'alertas-merma',             ConfiguracionAlertaMermaViewSet, basename='alerta-merma')
router.register(r'destinatarios-alerta',      DestinatarioAlertaMermaViewSet,  basename='destinatario-alerta')

# ── RH ───────────────────────────────────────────────
router.register(r'rh/departamentos',          DepartamentoViewSet,             basename='rh-departamento')
router.register(r'rh/puestos',                PuestoViewSet,                   basename='rh-puesto')
router.register(r'rh/motivos-inactivacion',   MotivoInactivacionViewSet,       basename='rh-motivo-inactivacion')
router.register(r'rh/divisiones-operativas',  DivisionOperativaViewSet,        basename='rh-division')
router.register(r'rh/tipos-carga',            TipoCargaViewSet,                basename='rh-tipo-carga')
router.register(r'rh/tipos-viaje',            TipoViajeViewSet,                basename='rh-tipo-viaje')
router.register(r'rh/tipos-documento',        TipoDocumentoOperadorViewSet,    basename='rh-tipo-documento')
router.register(r'rh/empleados',              EmpleadoViewSet,                 basename='rh-empleado')
router.register(r'rh/motivos-baja',           MotivoBajaViewSet,               basename='rh-motivo-baja')
router.register(r'rh/bajas',                  BajaEmpleadoViewSet,             basename='rh-baja')
router.register(r'rh/vacaciones',             VacacionViewSet,                 basename='rh-vacacion')
router.register(r'rh/historico-vacaciones',   HistoricoVacacionesViewSet,      basename='rh-historico-vac')
router.register(r'rh/prestamos',              PrestamoViewSet,                 basename='rh-prestamo')
router.register(r'rh/control-vacantes',       ControlVacanteViewSet,           basename='rh-vacante')
router.register(r'rh/plantillas-contrato',    PlantillaContratoViewSet,        basename='rh-plantilla-contrato')
router.register(r'rh/contratos-generados',    ContratoGeneradoViewSet,         basename='rh-contrato-generado')

# ── Bancos ───────────────────────────────────────────
router.register(r'bancos/cuentas',            CuentaViewSet,                   basename='banco-cuenta')
router.register(r'bancos/unidades-negocio',   UnidadNegocioViewSet,            basename='banco-unidad-negocio')
router.register(r'bancos/operaciones',        OperacionViewSet,                basename='banco-operacion')
router.register(r'bancos/categorias',         CategoriaViewSet,                basename='banco-categoria')
router.register(r'bancos/subcategorias',      SubCategoriaViewSet,             basename='banco-subcategoria')
router.register(r'bancos/terceros',           TerceroViewSet,                  basename='banco-tercero')
router.register(r'bancos/movimientos',        MovimientoViewSet,               basename='banco-movimiento')
router.register(r'bancos/resumenes-mensuales', ResumenMensualViewSet,          basename='banco-resumen')

# ── Compras ──────────────────────────────────────────
router.register(r'compras/proveedores',       ProveedorViewSet,                basename='compra-proveedor')
router.register(r'compras/categorias',        CategoriaComprasViewSet,         basename='compra-categoria')
router.register(r'compras/unidades-medida',   UnidadMedidaViewSet,             basename='compra-unidad-medida')
router.register(r'compras/articulos',         ArticuloViewSet,                 basename='compra-articulo')
router.register(r'compras/solicitudes',       SolicitudCompraViewSet,          basename='compra-solicitud')
router.register(r'compras/ordenes',           OrdenCompraViewSet,              basename='compra-orden')

# ── CxP ──────────────────────────────────────────────
router.register(r'cxp/facturas',              FacturaCxPViewSet,               basename='cxp-factura')

# ── Diesel ───────────────────────────────────────────
router.register(r'diesel/patios',             PatioViewSet,                    basename='diesel-patio')
router.register(r'diesel/proveedores',        ProveedorDieselViewSet,          basename='diesel-proveedor')
router.register(r'diesel/unidades',           UnidadDieselViewSet,             basename='diesel-unidad')
router.register(r'diesel/totems',             TotemViewSet,                    basename='diesel-totem')
router.register(r'diesel/compras-combustible', CompraCombustibleViewSet,       basename='diesel-compra')
router.register(r'diesel/ajustes',            AjusteInventarioViewSet,         basename='diesel-ajuste')
router.register(r'diesel/cargas',             CargaDieselViewSet,              basename='diesel-carga')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
urlpatterns = [
    # ── Router DRF ────────────────────────────────────
    path('', include(router.urls)),

    # ── Auth ──────────────────────────────────────────
    path('auth/login/',           LoginView.as_view(),          name='api-login'),
    path('auth/logout/',          LogoutView.as_view(),         name='api-logout'),
    path('auth/me/',              MeView.as_view(),             name='api-me'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='api-change-password'),
    path('auth/usuarios/',        UsuariosAdminView.as_view(),  name='api-usuarios-admin'),
    path('auth/usuarios/<int:pk>/permisos/', UsuarioPermisosView.as_view(), name='api-usuario-permisos'),

    # ── Configuración del sistema ─────────────────────
    path('codigo-postal/',  CodigoPostalView.as_view(),        name='api-codigo-postal'),
    path('config/',         ConfiguracionView.as_view(),       name='api-config'),
    path('config/modulos/', ConfiguracionModulosView.as_view(), name='api-config-modulos'),
    path('config/ui/',      ConfiguracionUIView.as_view(),     name='api-config-ui'),

    # ── Catálogos por empresa ─────────────────────────
    path('catalogos/empresa/<int:empresa_id>/', CatalogosEmpresaView.as_view(), name='api-catalogos-empresa'),

    # ── KPIs / Reportes ───────────────────────────────
    path('reportes/kpi/',   ReporteKPIView.as_view(),         name='api-kpi'),

    # ── Bancos: resumen ───────────────────────────────
    path('bancos/resumen/', ResumenBancosView.as_view(),       name='api-bancos-resumen'),

    # ── CxP: alertas ──────────────────────────────────
    path('cxp/alertas/',    AlertasCxPView.as_view(),          name='api-cxp-alertas'),

    # ── Diesel: resumen ───────────────────────────────
    path('diesel/resumen/', ResumenDieselView.as_view(),       name='api-diesel-resumen'),

    # ── RH: dashboard ─────────────────────────────────
    path('rh/dashboard/',   DashboardRHView.as_view(),        name='api-rh-dashboard'),

    # ── Token auth DRF (opcional: útil para browsable API) ──
    path('auth/token/', include('rest_framework.urls', namespace='rest_framework')),
]
