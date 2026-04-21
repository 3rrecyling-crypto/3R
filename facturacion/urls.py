# facturacion/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_facturacion, name='dashboard_facturacion'),
    path('nueva/', views.crear_factura_nueva, name='crear_factura_nueva'),
    path('prefacturar/', views.prefacturar_remisiones, name='prefacturar_remisiones'),
    path('generar/', views.generar_factura_accion, name='generar_factura_accion'),
    path('detalle/<int:pk>/', views.detalle_factura, name='detalle_factura_cliente'),
    path('pdf/<int:pk>/', views.generar_pdf, name='factura_pdf_cliente'),
    path('por-facturar/', views.remisiones_por_facturar, name='remisiones_por_facturar'),
    path('configurar-emisor/', views.configurar_emisor, name='configurar_emisor'),
    
    # Fíjate que esta línea termine con una coma:
    path('cliente/<int:cliente_id>/fiscal/', views.configurar_cliente_fiscal, name='configurar_cliente_fiscal'),

    # Nueva ruta para pagos (agregada correctamente):
    path('factura/<int:factura_id>/pago/', views.registrar_pago, name='registrar_pago'),
    path('pagos/nuevo/', views.nuevo_complemento_pago, name='nuevo_complemento_pago'),
    path('factura/<int:pk>/cancelar/', views.cancelar_factura_view, name='cancelar_factura'),
    path('pago/<int:pk>/cancelar/', views.cancelar_pago_view, name='cancelar_pago'),
    path('api/buscar-sat/', views.buscar_catalogo_sat, name='buscar_catalogo_sat'),
    path('pago/pdf/<int:pk>/', views.generar_pdf_pago, name='pago_pdf_cliente'),
    path('descargar-xml/<int:pk>/', views.descargar_xml_view, name='descargar_xml'),
    path('factura/<int:factura_id>/nota-credito/', views.generar_nota_credito, name='generar_nota_credito'),
    path('nota-credito/nueva-libre/', views.crear_nota_credito_libre, name='crear_nota_credito_libre'),
    path('api/serie/crear/', views.api_crear_serie, name='api_crear_serie'),
    path('api/serie/eliminar/<int:serie_id>/', views.api_eliminar_serie, name='api_eliminar_serie'),
    path('pago/descargar-xml/<int:pk>/', views.descargar_xml_pago, name='descargar_xml_pago'),
    path('api/buscar-cp/', views.buscar_cp_view, name='api_buscar_cp'),
    path('exportar-contabilidad/', views.exportar_reporte_contable, name='exportar_reporte_contable'),
    path('catalogo/', views.lista_productos, name='lista_productos'),
    path('catalogo/nuevo/', views.crear_producto, name='crear_producto'),
    path('catalogo/editar/<int:pk>/', views.editar_producto, name='editar_producto'),
    path('catalogo/eliminar/<int:pk>/', views.eliminar_producto, name='eliminar_producto'),
    
    # API JSON
    path('api/buscar-local/', views.api_buscar_productos_local, name='api_buscar_productos_local'),
    path('impuestos/', views.lista_impuestos, name='lista_impuestos'),
    path('impuestos/nuevo/', views.crear_impuesto, name='crear_impuesto'),
    path('impuestos/editar/<int:pk>/', views.editar_impuesto, name='editar_impuesto'),
    path('impuestos/eliminar/<int:pk>/', views.eliminar_impuesto, name='eliminar_impuesto'),
    path('api/validar-lugar/', views.api_validar_lugar, name='api_validar_lugar'),
]