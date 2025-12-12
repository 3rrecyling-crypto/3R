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
]