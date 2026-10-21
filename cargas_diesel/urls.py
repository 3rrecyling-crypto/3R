from django.urls import path
from . import views, views_captura

app_name = 'diesel'

urlpatterns = [
    # Dashboard
    path('api/dashboard/', views.DashboardAPIView.as_view(), name='api_dashboard'),

    # Patios
    path('api/patios/', views.PatiosListAPIView.as_view(), name='api_patios'),

    # Proveedores
    path('api/proveedores/', views.ProveedoresListAPIView.as_view(), name='api_proveedores'),

    # Unidades
    path('api/unidades/', views.UnidadesListAPIView.as_view(), name='api_unidades'),
    path('api/unidades/rendimiento/', views.UnidadesRendimientoListAPIView.as_view(), name='api_unidades_rendimiento'),

    # Cargas
    path('api/cargas/', views.CargaDieselListAPIView.as_view(), name='api_cargas_lista'),
    path('api/cargas/crear/', views.CargaDieselCreateAPIView.as_view(), name='api_carga_crear'),

    # Compras
    path('api/compras/', views.CompraListAPIView.as_view(), name='api_compras_lista'),
    path('api/compras/crear/', views.CompraCreateAPIView.as_view(), name='api_compra_crear'),

    # Ajustes
    path('api/ajustes/', views.AjusteListAPIView.as_view(), name='api_ajustes_lista'),
    path('api/ajustes/crear/', views.AjusteCreateAPIView.as_view(), name='api_ajuste_crear'),

    # Configuración Tótem
    path('api/totem/<int:patio_id>/', views.TotemConfigAPIView.as_view(), name='api_totem_config'),

    # Captura desde el celular (PWA de Next en /diesel/captura)
    path('api/captura/datos/', views_captura.CapturaDatosAPIView.as_view(), name='api_captura_datos'),
    path('api/captura/cargas/', views_captura.CapturaCargaAPIView.as_view(), name='api_captura_cargas'),

    # Catálogos de la captura: Permisionarios (con unidades de Catálogos), Thermos y Despachadores
    path('api/permisionarios/', views_captura.PermisionariosAPIView.as_view(), name='api_permisionarios'),
    path('api/permisionarios/unidades/', views_captura.PermisionarioUnidadesAPIView.as_view(), name='api_permisionarios_unidades'),
    path('api/permisionarios/<int:pk>/', views_captura.PermisionarioDetalleAPIView.as_view(), name='api_permisionario_detalle'),
    path('api/thermos/', views_captura.ThermosAPIView.as_view(), name='api_thermos'),
    path('api/thermos/<int:pk>/', views_captura.ThermoDetalleAPIView.as_view(), name='api_thermo_detalle'),
    path('api/despachadores/', views_captura.DespachadoresAPIView.as_view(), name='api_despachadores'),
    path('api/despachadores/opciones/', views_captura.DespachadorOpcionesAPIView.as_view(), name='api_despachadores_opciones'),
    path('api/despachadores/<int:pk>/', views_captura.DespachadorDetalleAPIView.as_view(), name='api_despachador_detalle'),
    path('carga/formulario/', views.formulario_carga_view, name='formulario_carga'),
    path('dashboard/', views.dashboard_view, name='dashboard_diesel'),
    path('api/login/', views.LoginAPIView.as_view(), name='api-login'),
    path('api/csrf/', views.CsrfView.as_view(), name='api-csrf'),
]
