from django.urls import path
from . import auditoria_ia, excel_cargas, ia_tablero, views, views_captura, views_config, views_tablero

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
    path('api/cargas/excel/', excel_cargas.CargasExcelAPIView.as_view(), name='api_cargas_excel'),
    path('api/cargas/permisionarios/', views.CargasPermisionariosAPIView.as_view(), name='api_cargas_permisionarios'),
    path('api/cargas/auditoria/', auditoria_ia.AuditoriaCargasAPIView.as_view(), name='api_cargas_auditoria'),

    # Compras
    path('api/compras/', views.CompraListAPIView.as_view(), name='api_compras_lista'),
    path('api/compras/crear/', views.CompraCreateAPIView.as_view(), name='api_compra_crear'),

    # Ajustes
    path('api/ajustes/', views.AjusteListAPIView.as_view(), name='api_ajustes_lista'),
    path('api/ajustes/crear/', views.AjusteCreateAPIView.as_view(), name='api_ajuste_crear'),

    # Configuración Tótem
    path('api/totem/<int:patio_id>/', views.TotemConfigAPIView.as_view(), name='api_totem_config'),
    # Configuración de tótems (solo staff): alta, nombres, capacidad, alerta y nivel
    path('api/config/totems/', views_config.TotemsConfigAPIView.as_view(), name='api_config_totems'),
    path('api/config/totems/<int:patio_id>/', views_config.TotemConfigDetalleAPIView.as_view(), name='api_config_totem'),

    # Tablero BI: 3R RECYCLING (unidades y thermos) y permisionarios con sus cargas
    path('api/tablero/', views_tablero.TableroDieselAPIView.as_view(), name='api_tablero'),
    path('api/tablero/ia/', ia_tablero.TableroIAAPIView.as_view(), name='api_tablero_ia'),
    path('api/tablero/ia/excel/', ia_tablero.TableroIAExcelAPIView.as_view(), name='api_tablero_ia_excel'),

    # Captura desde el celular (PWA de Next en /diesel/captura)
    path('api/captura/datos/', views_captura.CapturaDatosAPIView.as_view(), name='api_captura_datos'),
    path('api/captura/cargas/', views_captura.CapturaCargaAPIView.as_view(), name='api_captura_cargas'),
    path('api/captura/cargas/<int:pk>/fotos/<str:clave>/', views_captura.CargaFotoAPIView.as_view(), name='api_captura_carga_foto'),
    path('api/captura/cargas/<int:pk>/resumen/', views_captura.CargaResumenAPIView.as_view(), name='api_captura_carga_resumen'),

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
