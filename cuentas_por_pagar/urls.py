from django.urls import path
from . import views

urlpatterns = [
    # Facturas
    path('facturas/', views.FacturaListView.as_view(), name='lista_facturas'),
    path('facturas/<int:pk>/', views.FacturaDetailView.as_view(), name='detalle_factura'),
    path('facturas/<int:pk>/editar/', views.FacturaUpdateView.as_view(), name='editar_factura'),
    path('facturas/<int:pk>/eliminar/', views.FacturaDeleteView.as_view(), name='eliminar_factura'),
    path('facturas/<int:pk>/plazos/', views.gestionar_plazos_factura, name='gestionar_plazos_factura'),
    
    # Pagos
    path('pagos/', views.PagoListView.as_view(), name='lista_pagos'),
    path('pagos/nuevo/', views.PagoCreateView.as_view(), name='crear_pago'),
    path('pagos/<int:pk>/', views.PagoDetailView.as_view(), name='detalle_pago'),
    path('pagos/<int:pk>/editar/', views.PagoUpdateView.as_view(), name='editar_pago'),
    path('pagos/<int:pk>/eliminar/', views.PagoDeleteView.as_view(), name='eliminar_pago'),
    
    # Redirección desde Compras
    path('orden-compra/<int:pk>/plazos/', views.gestionar_plazos_oc_redirect, name='gestionar_plazos_oc'),
    
    # Dashboard y APIs
    path('dashboard/', views.dashboard_cuentas_por_pagar, name='dashboard_cuentas_por_pagar'),
    path('api/estadisticas/', views.api_estadisticas_proveedor, name='api_estadisticas_proveedor'),
    path('api/deudas/', views.api_deudas_proveedor, name='api_deudas_proveedor'),
    path('exportar-excel/', views.exportar_facturas_excel, name='exportar_facturas_excel'),
]