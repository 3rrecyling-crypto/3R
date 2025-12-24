# compras/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Dashboard de Compras
    path('', views.dashboard_compras, name='dashboard_compras'),
    
    # Proveedores
    path('proveedores/', views.ProveedorListView.as_view(), name='lista_proveedores'),
    path('proveedores/nuevo/', views.ProveedorCreateView.as_view(), name='crear_proveedor'),
    path('proveedores/<int:pk>/', views.ProveedorDetailView.as_view(), name='detalle_proveedor'),
    path('proveedores/<int:pk>/editar/', views.ProveedorUpdateView.as_view(), name='editar_proveedor'),
    path('proveedores/<int:pk>/eliminar/', views.ProveedorDeleteView.as_view(), name='eliminar_proveedor'),
    
    # Artículos
    path('articulos/', views.ArticuloListView.as_view(), name='lista_articulos'),
    # --- MODIFICADO --- (Apunta a la vista de función)
    path('articulos/nuevo/', views.crear_articulo, name='crear_articulo'),
    path('articulos/<int:pk>/editar/', views.editar_articulo, name='editar_articulo'),
    
    # Solicitudes de Compra
    path('solicitudes/', views.SolicitudCompraListView.as_view(), name='lista_solicitudes'),
    path('solicitudes/nueva/', views.crear_solicitud, name='crear_solicitud'),
    path('solicitudes/editar/<int:pk>/', views.editar_solicitud, name='editar_solicitud'),
    path('solicitudes/detalle/<int:pk>/', views.SolicitudCompraDetailView.as_view(), name='detalle_solicitud'),
    path('solicitudes/<int:pk>/aprobar/', views.aprobar_solicitud, name='aprobar_solicitud'),
    path('solicitudes/<int:pk>/rechazar/', views.rechazar_solicitud, name='rechazar_solicitud'),
    path('solicitudes/<int:pk>/generar-oc/', views.generar_orden_de_compra, name='generar_orden_de_compra'),

    # Órdenes de Compra
    path('ordenes/', views.OrdenCompraListView.as_view(), name='lista_ordenes_compra'),
    path('ordenes/detalle/<int:pk>/', views.OrdenCompraDetailView.as_view(), name='detalle_orden_compra'),
    
    # --- LÍNEA AÑADIDA PARA SOLUCIONAR EL ERROR ---
    path('ordenes/<int:pk>/terminar/', views.redirigir_a_generar_oc, name='terminar_orden_compra'),
    # -----------------------------------------------
    
    path('ordenes/<int:pk>/archivos/', views.OrdenCompraArchivosUpdateView.as_view(), name='editar_archivos_oc'),
    path('ordenes/<int:pk>/pdf/', views.orden_compra_pdf_view, name='orden_compra_pdf'),
    path('ordenes/<int:pk>/auditar/', views.iniciar_auditoria_oc, name='iniciar_auditoria_oc'),
    path('ordenes/<int:pk>/cancelar/', views.cancelar_orden_compra, name='cancelar_orden_compra'),
    path('api/update_articulo_precio/', views.update_articulo_proveedor_precio, name='update_articulo_proveedor_precio'),

    # URLs para gestión de documentos de OC
    path('ordenes/<int:pk>/subir-factura/', views.subir_factura_oc, name='subir_factura_oc'),
    path('ordenes/<int:pk>/subir-comprobante/', views.subir_comprobante_oc, name='subir_comprobante_oc'),
    path('ordenes/<int:pk>/eliminar-documento/<str:tipo>/', views.eliminar_documento_oc, name='eliminar_documento_oc'),


    # Categorías
    path('categorias/', views.CategoriaListView.as_view(), name='lista_categorias'),
    path('categorias/nueva/', views.CategoriaCreateView.as_view(), name='crear_categoria'),
    path('categorias/<int:pk>/editar/', views.CategoriaUpdateView.as_view(), name='editar_categoria'),
    path('categorias/<int:pk>/eliminar/', views.CategoriaDeleteView.as_view(), name='eliminar_categoria'),

    # API para filtrar artículos dinámicamente
    # --- RUTA NUEVA AÑADIDA ---
    path('api/origenes_por_empresa/<int:empresa_id>/', views.get_origenes_por_empresa, name='api_origenes_por_empresa'),
    path('api/articulos_por_empresa/<int:empresa_id>/', views.get_articulos_por_empresa, name='api_articulos_por_empresa'),
    path('api/proveedores_por_empresa/<int:empresa_id>/', views.get_proveedores_por_empresa, name='api_proveedores_por_empresa'),
    path('api/articulos_por_proveedor/<int:proveedor_id>/', views.get_articulos_por_proveedor, name='api_articulos_por_proveedor'),
    path('api/update-articulo-precio/', views.update_articulo_proveedor_precio, name='api_update_articulo_precio'),
    path('api/empresas-por-operacion/<int:operacion_id>/', views.get_empresas_por_operacion, name='api_empresas_por_operacion'),
    path('reportes/excel-compras/', views.reporte_compras_excel, name='reporte_compras_excel'),
    path('webhooks/whatsapp/', views.twilio_webhook, name='twilio_webhook'),
]