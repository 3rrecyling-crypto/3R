# ternium/urls.py

from django.urls import path
from . import views
from django.urls import path, include
from .forms import CustomLoginForm  # <--- Nombre correcto
from . import api_views
from .views import (
    UnidadDetailView, UnidadUpdateView, LugarDetailView, LugarUpdateView, 
    EmpresaDetailView, EmpresaUpdateView, ContenedorDetailView, ContenedorUpdateView,
    MaterialDetailView, MaterialUpdateView,
    RegistroLogisticoListView, RegistroLogisticoCreateView, RegistroLogisticoUpdateView,
    RegistroLogisticoDetailView, DescargarPaqueteZipView, RemisionDeleteView, detalles_genericos
)
from django.contrib.auth import views as auth_views

urlpatterns = [
    # ======================================================
    # 1. PÁGINA DE INICIO (BIENVENIDA)
    # ======================================================
    # Esta es la nueva puerta de entrada general. No requiere permisos especiales.
    path('', views.home_bienvenida, name='home'),

    # ======================================================
    # 2. DASHBOARD DE OPERACIONES (ANTES HOME)
    # ======================================================
    # Aquí está la lógica de Patios e Inventarios. Protegido por permiso 'acceso_dashboard_patio'.
    path('operaciones/dashboard/', views.dashboard_operaciones_view, name='dashboard_operaciones'),

    # ======================================================
    # 3. MÓDULO DE ENTRADAS DE MAQUILA
    # ======================================================
    path('entradas/', views.EntradaMaquilaListView.as_view(), name='lista_entradas'), 
    path('entradas/nueva/', views.crear_entrada, name='crear_entrada'),
    path('entradas/<int:pk>/', views.detalle_entrada, name='detalle_entrada'), 
    path('entradas/<int:pk>/editar/', views.editar_entrada, name='editar_entrada'),
    path('entradas/<int:pk>/eliminar/', views.eliminar_entrada, name='eliminar_entrada'),
    path('entradas/export/excel/', views.export_entradas_to_excel, name='export_entradas_excel'),
    path('entradas/<int:pk>/descargar-zip/', views.DescargarZipMaquilaView.as_view(), name='descargar_zip_maquila'),
    path('entradas/<int:pk>/auditar/', views.auditar_entrada, name='auditar_entrada'),

    # ======================================================
    # 4. MÓDULO DE REMISIONES
    # ======================================================
    path('remisiones/', views.RemisionListView.as_view(), name='remision_lista'),
    path('remisiones/crear/', views.crear_remision, name='crear_remision'),
    path('remisiones/importar/', views.importar_remisiones_excel, name='importar_remisiones_excel'),
    path('remisiones/<int:pk>/', views.detalle_remision, name='detalle_remision'),
    path('remisiones/<int:pk>/editar/', views.editar_remision, name='editar_remision'),
    path('remision/<int:pk>/eliminar/', RemisionDeleteView.as_view(), name='eliminar_remision'),
    path('remision/<int:pk>/auditar/', api_views.auditar_remision, name='auditar_remision'),
    path('remisiones/exportar-excel/', api_views.export_remisiones_to_excel, name='export_remisiones_to_excel'),
    
    # API interna para obtener folio
    path('api/get-next-remision/<int:empresa_id>/', views.get_next_remision_number, name='get_next_remision_number'),
    path('api/dashboard-operacion/', views.api_dashboard_operacion, name='api_dashboard_operacion'),

    # ======================================================
    # 5. MÓDULO DE LOGÍSTICA TERNIUM
    # ======================================================
    path('registros-logistica/', RegistroLogisticoListView.as_view(), name='lista_registros_logistica'),
    path('registros-logistica/nuevo/', RegistroLogisticoCreateView.as_view(), name='crear_registro_logistica'),
    path('registros-logistica/<int:pk>/', RegistroLogisticoDetailView.as_view(), name='detalle_registro_logistica'),
    path('registros-logistica/<int:pk>/editar/', RegistroLogisticoUpdateView.as_view(), name='editar_registro_logistica'),
    path('registros-logistica/<int:pk>/descargar-zip/', DescargarPaqueteZipView.as_view(), name='descargar_paquete_zip'),
    path('logistica/export/excel/', views.export_logistica_to_excel, name='export_logistica_excel'),
    path('logistica/<int:pk>/auditar/', views.auditar_registro_logistico, name='auditar_registro_logistica'),

    # ======================================================
    # 6. ANÁLISIS, REPORTES E INTELIGENCIA
    # ======================================================
    path('analisis/dashboard/', views.dashboard_analisis_view, name='dashboard_analisis'),
    path('analisis/remisiones/', views.dashboard_remisiones_view, name='dashboard_remisiones'),
    path('asistente-ia/', views.asistente_ia, name='asistente_ia'),

    # ======================================================
    # 7. CATÁLOGOS Y CONFIGURACIÓN
    # ======================================================
    
    # Perfil de Usuario
    path('perfil/', views.vista_perfil, name='perfil'),

    # API Catálogos Dinámicos
    path('api/get-catalogos/<int:empresa_id>/', views.get_catalogos_por_empresa, name='get_catalogos_por_empresa'),
    path('api/catalogos/<int:empresa_id>/', views.get_catalogos_por_empresa, name='api_get_catalogos_por_empresa'), # Alias
    path('catalogo/<str:model_name>/<int:pk>/detalles/', views.detalles_genericos, name='detalles_genericos'),
    path('catalogo/busqueda-avanzada/', views.busqueda_avanzada, name='busqueda_avanzada'),

    # Descargas e Inventario (Manual)
    path('descargas/', views.DescargaListView.as_view(), name='descarga_lista'),
    path('descargas/registrar/', views.DescargaCreateView.as_view(), name='crear_descarga'),

    # Lugares
    path('lugares/', views.LugarListView.as_view(), name='lista_lugares'),
    path('lugares/nuevo/', views.LugarCreateView.as_view(), name='crear_lugar'),
    path('lugares/<int:pk>/', LugarDetailView.as_view(), name='detalle_lugar'),
    path('lugares/editar/<int:pk>/', LugarUpdateView.as_view(), name='editar_lugar'),
    
    # Empresas
    path('empresas/', views.EmpresaListView.as_view(), name='lista_empresas'),
    path('empresas/nueva/', views.EmpresaCreateView.as_view(), name='crear_empresa'),
    path('empresas/<int:pk>/', EmpresaDetailView.as_view(), name='detalle_empresa'),
    path('empresas/editar/<int:pk>/', EmpresaUpdateView.as_view(), name='editar_empresa'),
    path('empresas/<int:pk>/vincular-origenes/', views.EmpresaVincularOrigenesView.as_view(), name='vincular_origenes_empresa'),

    # Líneas de Transporte
    path('lineas-transporte/', views.LineaTransporteListView.as_view(), name='lista_lineas_transporte'),
    path('lineas-transporte/nueva/', views.LineaTransporteCreateView.as_view(), name='crear_lineatransporte'),
    path('lineas-transporte/<int:pk>/', views.LineaTransporteDetailView.as_view(), name='detalle_lineatransporte'),
    path('lineas-transporte/<int:pk>/editar/', views.LineaTransporteUpdateView.as_view(), name='editar_lineatransporte'),

    # Operadores
    path('operadores/', views.OperadorListView.as_view(), name='lista_operadores'),
    path('operadores/nuevo/', views.OperadorCreateView.as_view(), name='crear_operador'),
    path('operadores/<int:pk>/', views.OperadorDetailView.as_view(), name='detalle_operador'),
    path('operadores/<int:pk>/editar/', views.OperadorUpdateView.as_view(), name='editar_operador'),

    # Materiales
    path('materiales/', views.MaterialListView.as_view(), name='lista_materiales'),
    path('materiales/nuevo/', views.MaterialCreateView.as_view(), name='crear_material'),
    path('materiales/<int:pk>/', MaterialDetailView.as_view(), name='detalle_material'),
    path('materiales/editar/<int:pk>/', MaterialUpdateView.as_view(), name='editar_material'),

    # Unidades
    path('unidades/', views.UnidadListView.as_view(), name='lista_unidades'),
    path('unidades/nueva/', views.UnidadCreateView.as_view(), name='crear_unidad'),
    path('unidades/<int:pk>/', UnidadDetailView.as_view(), name='detalle_unidad'),
    path('unidades/editar/<int:pk>/', UnidadUpdateView.as_view(), name='editar_unidad'),

    # Contenedores
    path('contenedores/', views.ContenedorListView.as_view(), name='lista_contenedores'),
    path('contenedores/nuevo/', views.ContenedorCreateView.as_view(), name='crear_contenedor'),
    path('contenedores/<int:pk>/', ContenedorDetailView.as_view(), name='detalle_contenedor'),
    path('contenedores/editar/<int:pk>/', ContenedorUpdateView.as_view(), name='editar_contenedor'),

    # ======================================================
    # 8. AUTENTICACIÓN Y PORTALES
    # ======================================================
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('entradas/<int:pk>/cancelar/', views.cancelar_entrada, name='cancelar_entrada'),
    # Portal específico para clientes/ternium
    path('ternium/', views.home_portal_view, name='ternium_portal'),
    path('portal/', views.home_portal_view, name='home_portal'),
    path('login/', auth_views.LoginView.as_view(
    template_name='registration/login.html',
    authentication_form=CustomLoginForm
), name='login'),
    path('remision/<int:pk>/cancelar/', api_views.cancelar_remision, name='cancelar_remision'),
    path('facturacion/', include('facturacion.urls')),
    path('exportar-catalogo/<str:model_name>/', views.export_catalogo_excel, name='export_catalogo_excel'),
    path('remisiones/importar-evidencias/', views.importar_evidencias_masivas, name='importar_evidencias_masivas'),
    path('logistica/<int:pk>/cancelar/', views.cancelar_registro_logistica, name='cancelar_registro_logistica'),
    path('remision/evidencia/<int:pk>/eliminar/', api_views.eliminar_evidencia_individual, name='eliminar_evidencia_individual'),
    path('plastico/', views.lista_plastico, name='lista_plastico'),
    path('plastico/nuevo/', views.crear_plastico, name='crear_plastico'),
    path('plastico/<int:pk>/', views.detalle_plastico, name='detalle_plastico'),
    path('plastico/editar/<int:pk>/', views.editar_plastico, name='editar_plastico'),
    path('plastico/cancelar/<int:pk>/', views.cancelar_plastico, name='cancelar_plastico'),
    path('plastico/auditar/<int:pk>/', views.auditar_plastico, name='auditar_plastico'),
    path('plastico/exportar/', views.exportar_plastico_excel, name='exportar_plastico_excel'),
    path('remision/<int:pk>/pdf/', views.export_remision_pdf, name='export_remision_pdf'),
    path('api/crear-transporte-ajax/', views.crear_linea_transporte_ajax, name='crear_transporte_ajax'),
    path('api/listar-transportes-ajax/', views.listar_lineas_transporte_ajax, name='listar_transportes_ajax'),
    path('portal/trane/', views.dashboard_trane_view, name='dashboard_trane'),
    path('portal/trane/api/data/', views.dashboard_trane_data, name='dashboard_trane_data'),
    path('api/verificar-remito/', views.verificar_remito_existente, name='verificar_remito_existente'),
    path('tarimas/', views.ControlTarimaListView.as_view(), name='lista_tarimas'),
    path('tarimas/nuevo/', views.crear_tarima, name='crear_tarima'),
    path('tarimas/editar/<int:pk>/', views.editar_tarima, name='editar_tarima'),
    path('tarimas/eliminar/<int:pk>/', views.eliminar_tarima, name='eliminar_tarima'),# Para gráficas
    path('tarimas/exportar/', views.export_tarimas_excel, name='exportar_tarimas_excel'),
    path('logistica/export/excel/', views.export_logistica_to_excel, name='export_logistica_excel'),
    
    # Opción 1: Totales Mensuales (Se mantiene igual)
    path('logistica/export/reporte-mensual/', views.export_logistica_reporte_mensual, name='export_logistica_mensual'),

    # NUEVO: Opción 2A - Reporte Solo Proveedor
    path('logistica/export/reporte-proveedor/', views.export_logistica_reporte_proveedor, name='export_logistica_proveedor'),
    
    # NUEVO: Opción 2B - Reporte Solo Material
    path('logistica/export/reporte-material/', views.export_logistica_reporte_material, name='export_logistica_material'),
    path('logistica/export/balanza-pesos/', views.export_balanza_pesos, name='export_balanza_pesos'),
    path('logistica/<int:pk>/rechazar/', views.rechazar_registro_logistica, name='rechazar_registro_logistica'),     # <--- NUEVO
    path('logistica/<int:pk>/restablecer/', views.restablecer_registro_logistica, name='restablecer_registro_logistica'), # <--- NUEVO
    path('remisiones/<int:remision_id>/reporte-destruccion/', api_views.descargar_reporte_destruccion, name='descargar_reporte_destruccion'),
    path('configuracion/asignar-manifiesto/', views.asignar_manifiesto, name='asignar_manifiesto'),
    # MÓDULO CONTROL TRANE (Manifiestos y dashboard_operacionesDocumentos)
    path('control-trane/', views.lista_control_trane, name='lista_control_trane'),
    path('control-trane/nuevo/', views.crear_control_trane, name='crear_control_trane'),
    path('control-trane/editar/<int:pk>/', views.editar_control_trane, name='editar_control_trane'),
    path('control-trane/eliminar/<int:pk>/', views.eliminar_control_trane, name='eliminar_control_trane'),
    path('control-trane/importar-remision/<int:remision_id>/', views.generar_trane_desde_remision, name='generar_trane_desde_remision'),
    path('remisiones/importar-trane/', views.importar_trane_a_remision, name='importar_trane_a_remision'),
    path('api/precio-medline/', views.obtener_precio_medline, name='obtener_precio_medline'),
    path('remisiones/exportar-especificos/', api_views.export_reportes_especificos, name='export_reportes_especificos'),
    path('remisiones/exportar-medline/', api_views.exportar_zip_medline, name='exportar_zip_medline'),
    path('api/dashboard-trane/', views.api_dashboard_trane, name='api_dashboard_trane'),
    path('api/remisiones-lista/', api_views.api_remisiones_lista, name='api_remisiones_lista'),
    path('api/exportar/remisiones', api_views.export_remisiones_to_excel, name='api_exportar_remisiones'),
    # 1. Ruta para obtener los catálogos dinámicos
    path('api/catalogos/<int:empresa_id>/', api_views.api_obtener_catalogos, name='api_obtener_catalogos'),
    path('api/remisiones/crear/', api_views.api_crear_remision, name='api_crear_remision'),
    path('api/remisiones/<int:pk>/editar/', api_views.api_editar_remision, name='api_editar_remision'),
    path('api/empresas/', api_views.api_obtener_empresas, name='api_obtener_empresas'),
    path('api/remisiones/<int:pk>/detalle/', api_views.api_remision_detalle),

    # ── CRUD Catalogos ───────────────────────────────────────────────
    path('api/cat/empresas/', api_views.api_cat_empresas, name='api_cat_empresas'),
    path('api/cat/empresas/<int:pk>/', api_views.api_cat_empresa_detail, name='api_cat_empresa_detail'),
    path('api/cat/lugares/', api_views.api_cat_lugares, name='api_cat_lugares'),
    path('api/cat/lugares/<int:pk>/', api_views.api_cat_lugar_detail, name='api_cat_lugar_detail'),
    path('api/cat/lineas/', api_views.api_cat_lineas, name='api_cat_lineas'),
    path('api/cat/lineas/<int:pk>/', api_views.api_cat_linea_detail, name='api_cat_linea_detail'),
    path('api/cat/operadores/', api_views.api_cat_operadores, name='api_cat_operadores'),
    path('api/cat/operadores/<int:pk>/', api_views.api_cat_operador_detail, name='api_cat_operador_detail'),
    path('api/cat/materiales/', api_views.api_cat_materiales, name='api_cat_materiales'),
    path('api/cat/materiales/<int:pk>/', api_views.api_cat_material_detail, name='api_cat_material_detail'),
    path('api/cat/unidades/', api_views.api_cat_unidades, name='api_cat_unidades'),
    path('api/cat/unidades/<int:pk>/', api_views.api_cat_unidad_detail, name='api_cat_unidad_detail'),
    path('api/cat/contenedores/', api_views.api_cat_contenedores, name='api_cat_contenedores'),
    path('api/cat/contenedores/<int:pk>/', api_views.api_cat_contenedor_detail, name='api_cat_contenedor_detail'),

    # ── Control Trane (Manifiestos) ──────────────────────────────────
    path('api/trane/manifiestos/', api_views.api_trane_manifiestos, name='api_trane_manifiestos'),
    path('api/trane/manifiestos/<int:pk>/', api_views.api_trane_manifiesto_detail, name='api_trane_manifiesto_detail'),

    # ── Perfil & Admin ───────────────────────────────────────────────
    path('api/perfil/', api_views.api_perfil, name='api_perfil'),
    path('api/admin/usuarios/', api_views.api_admin_usuarios, name='api_admin_usuarios'),
    path('api/admin/usuarios/<int:pk>/permisos/', api_views.api_admin_usuario_permisos, name='api_admin_usuario_permisos'),

]
