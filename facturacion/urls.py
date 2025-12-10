# facturacion/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_facturacion, name='dashboard_facturacion'),
    # Nueva ruta independiente
    path('nueva/', views.crear_factura_nueva, name='crear_factura_nueva'), 
    
    path('prefacturar/', views.prefacturar_remisiones, name='prefacturar_remisiones'),
    path('generar/', views.generar_factura_accion, name='generar_factura_accion'),
    path('detalle/<int:pk>/', views.detalle_factura, name='detalle_factura_cliente'),
    path('pdf/<int:pk>/', views.generar_pdf, name='factura_pdf_cliente'), # Sugiero cambiar este también
    path('por-facturar/', views.remisiones_por_facturar, name='remisiones_por_facturar'),
    path('configurar-emisor/', views.configurar_emisor, name='configurar_emisor'),
    path('cliente/<int:cliente_id>/fiscal/', views.configurar_cliente_fiscal, name='configurar_cliente_fiscal'),
    
]