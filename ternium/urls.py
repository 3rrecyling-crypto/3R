# ternium/urls.py

from django.urls import path
from . import views
from .views import (
    UnidadDetailView, UnidadUpdateView, LugarDetailView, LugarUpdateView, 
    EmpresaDetailView, EmpresaUpdateView, ContenedorDetailView, ContenedorUpdateView,
    MaterialDetailView, MaterialUpdateView,
    RegistroLogisticoListView, RegistroLogisticoCreateView, RegistroLogisticoUpdateView,
    RegistroLogisticoDetailView, DescargarPaqueteZipView,RemisionDeleteView, detalles_genericos
)
from django.contrib.auth import views as auth_views

urlpatterns = [
    # URL Principal
    path('', views.home, name='home'),

    # --- URLs para Entradas de Maquila ---
    path('entradas/', views.EntradaMaquilaListView.as_view(), name='lista_entradas'), 
    path('entradas/nueva/', views.crear_entrada, name='crear_entrada'),
    path('entradas/<int:pk>/', views.detalle_entrada, name='detalle_entrada'), 
    path('perfil/', views.vista_perfil, name='perfil'),
    path('entradas/<int:pk>/editar/', views.editar_entrada, name='editar_entrada'),
    path('entradas/<int:pk>/eliminar/', views.eliminar_entrada, name='eliminar_entrada'),

    # --- URLs para Remisiones ---
    path('remisiones/', views.RemisionListView.as_view(), name='remision_lista'),
    path('remisiones/crear/', views.crear_remision, name='crear_remision'),
    path('remisiones/<int:pk>/', views.detalle_remision, name='detalle_remision'),
    path('remisiones/<int:pk>/editar/', views.editar_remision, name='editar_remision'),
    path('remision/<int:pk>/eliminar/', RemisionDeleteView.as_view(), name='eliminar_remision'),
    path('remision/<int:pk>/auditar/', views.auditar_remision, name='auditar_remision'),
    path('remisiones/exportar-excel/', views.export_remisiones_to_excel, name='export_remisiones_to_excel'),
    path('api/catalogos/<int:empresa_id>/', views.get_catalogos_por_empresa, name='api_get_catalogos_por_empresa'),

    # --- URLs para Descargas e Inventario ---
    path('descargas/', views.DescargaListView.as_view(), name='descarga_lista'),
    path('descargas/registrar/', views.DescargaCreateView.as_view(), name='crear_descarga'),

    # --- URLs para Catálogos ---
    path('lugares/', views.LugarListView.as_view(), name='lista_lugares'),
    path('lugares/nuevo/', views.LugarCreateView.as_view(), name='crear_lugar'),
    path('lugares/<int:pk>/', LugarDetailView.as_view(), name='detalle_lugar'),
    path('lugares/editar/<int:pk>/', LugarUpdateView.as_view(), name='editar_lugar'),
    
    path('empresas/', views.EmpresaListView.as_view(), name='lista_empresas'),
    path('empresas/nueva/', views.EmpresaCreateView.as_view(), name='crear_empresa'),
    path('empresas/<int:pk>/', EmpresaDetailView.as_view(), name='detalle_empresa'),
    path('empresas/editar/<int:pk>/', EmpresaUpdateView.as_view(), name='editar_empresa'),

    path('lineas-transporte/', views.LineaTransporteListView.as_view(), name='lista_lineas_transporte'),
path('lineas-transporte/nueva/', views.LineaTransporteCreateView.as_view(), name='crear_lineatransporte'),
path('lineas-transporte/<int:pk>/', views.LineaTransporteDetailView.as_view(), name='detalle_lineatransporte'), # <-- AÑADIDO
path('lineas-transporte/<int:pk>/editar/', views.LineaTransporteUpdateView.as_view(), name='editar_lineatransporte'), # <-- AÑADIDO

    path('operadores/', views.OperadorListView.as_view(), name='lista_operadores'),
    path('operadores/nuevo/', views.OperadorCreateView.as_view(), name='crear_operador'),
    path('operadores/<int:pk>/', views.OperadorDetailView.as_view(), name='detalle_operador'), # <-- AÑADIDO
    path('operadores/<int:pk>/editar/', views.OperadorUpdateView.as_view(), name='editar_operador'), # <-- AÑADIDO

    path('materiales/', views.MaterialListView.as_view(), name='lista_materiales'),
    path('materiales/nuevo/', views.MaterialCreateView.as_view(), name='crear_material'),
    path('materiales/<int:pk>/', MaterialDetailView.as_view(), name='detalle_material'),
    path('materiales/editar/<int:pk>/', MaterialUpdateView.as_view(), name='editar_material'),

    path('unidades/', views.UnidadListView.as_view(), name='lista_unidades'),
    path('unidades/nueva/', views.UnidadCreateView.as_view(), name='crear_unidad'),
    path('unidades/<int:pk>/', UnidadDetailView.as_view(), name='detalle_unidad'),
    path('unidades/editar/<int:pk>/', UnidadUpdateView.as_view(), name='editar_unidad'),

    path('contenedores/', views.ContenedorListView.as_view(), name='lista_contenedores'),
    path('contenedores/nuevo/', views.ContenedorCreateView.as_view(), name='crear_contenedor'),
    path('contenedores/<int:pk>/', ContenedorDetailView.as_view(), name='detalle_contenedor'),
    path('contenedores/editar/<int:pk>/', ContenedorUpdateView.as_view(), name='editar_contenedor'),

    # --- URLs para Logística Ternium (CORREGIDO) ---
    path('registros-logistica/', RegistroLogisticoListView.as_view(), name='lista_registros_logistica'),
    path('registros-logistica/nuevo/', RegistroLogisticoCreateView.as_view(), name='crear_registro_logistica'),
    path('registros-logistica/<int:pk>/', RegistroLogisticoDetailView.as_view(), name='detalle_registro_logistica'),
    path('registros-logistica/<int:pk>/editar/', RegistroLogisticoUpdateView.as_view(), name='editar_registro_logistica'),
    path('registros-logistica/<int:pk>/descargar-zip/', DescargarPaqueteZipView.as_view(), name='descargar_paquete_zip'),

    # --- API y Autenticación ---
    path('api/get-catalogos/<int:empresa_id>/', views.get_catalogos_por_empresa, name='get_catalogos_por_empresa'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('logistica/export/excel/', views.export_logistica_to_excel, name='export_logistica_excel'),
    path('logistica/<int:pk>/auditar/', views.auditar_registro_logistico, name='auditar_registro_logistica'),
    path('ternium/', views.home_portal_view, name='ternium_portal'),
    path('portal/', views.home_portal_view, name='home_portal'), # <-- ADD THIS LINE
    
    # --- ADD THESE NEW URLS TO FIX THE ERROR AND ENABLE NEW FEATURES ---
    path('entradas/export/excel/', views.export_entradas_to_excel, name='export_entradas_excel'),
    path('entradas/<int:pk>/descargar-zip/', views.DescargarZipMaquilaView.as_view(), name='descargar_zip_maquila'),
    path('entradas/<int:pk>/auditar/', views.auditar_entrada, name='auditar_entrada'),
    path('operadores/<int:pk>/editar/', views.OperadorUpdateView.as_view(), name='editar_operador'), # <-- AÑADE ESTA LÍNEA
    
    path('catalogo/<str:model_name>/<int:pk>/detalles/', views.detalles_genericos, name='detalles_genericos'),
    
    # URL para búsqueda avanzada
    path('catalogo/busqueda-avanzada/', views.busqueda_avanzada, name='busqueda_avanzada'),
    path('catalogo/busqueda-avanzada/', views.busqueda_avanzada, name='busqueda_avanzada'),
    
    # === AÑADE ESTA LÍNEA PARA EL ASISTENTE DE IA ===
    path('asistente-ia/', views.asistente_ia, name='asistente_ia'),
    path('api/get-next-remision/<int:empresa_id>/', views.get_next_remision_number, name='get_next_remision_number'),
    path('empresas/<int:pk>/vincular-origenes/', 
         views.EmpresaVincularOrigenesView.as_view(), 
         name='vincular_origenes_empresa'),
    path('analisis/dashboard/', views.dashboard_analisis_view, name='dashboard_analisis'),
    path('remisiones/importar/', views.importar_remisiones_excel, name='importar_remisiones_excel'),
    path('analisis/remisiones/', views.dashboard_remisiones_view, name='dashboard_remisiones'),
]
    

