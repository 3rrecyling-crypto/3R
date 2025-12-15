from django.urls import path
from . import views

urlpatterns = [
    # CAMBIO CLAVE: name='dashboard_bancos' para no chocar con el inicio
    path('', views.dashboard, name='dashboard_bancos'),
    
    # CORRECCIÓN: Usamos los nombres en español que tienes en views.py
    path('movimientos/', views.lista_movimientos, name='lista_movimientos'),
    path('movimientos/nuevo/', views.crear_movimiento, name='crear_movimiento'),
    path('nuevo/', views.crear_movimiento, name='transaction_create'),
    path('transferencia/', views.crear_transferencia, name='transfer_create'),
    path('ajax/subcategories/', views.cargar_subcategorias, name='ajax_load_subcategories'),
    path('ajax/saldo-cuenta/', views.obtener_saldo_cuenta, name='ajax_saldo_cuenta'),
    path('cuenta/editar/<int:cuenta_id>/', views.editar_cuenta, name='editar_cuenta'),
    path('tercero/nuevo/', views.crear_tercero, name='crear_tercero'),
    path('movimientos/exportar/', views.exportar_movimientos_excel, name='exportar_movimientos_excel'),
    path('movimientos/<int:pk>/', views.detalle_movimiento, name='detalle_movimiento'),
    path('movimientos/editar/<int:pk>/', views.editar_movimiento, name='editar_movimiento'),
    path('movimientos/auditar/<int:pk>/', views.auditar_movimiento, name='auditar_movimiento'),
    path('transferencia/reporte/', views.exportar_transferencias_excel, name='exportar_transferencias_excel'),
    path('transferencias/lista/', views.lista_transferencias, name='lista_transferencias'),
    path('transferencias/cancelar/<int:pk>/', views.cancelar_transferencia, name='cancelar_transferencia'),
    path('transferencia/', views.crear_transferencia, name='crear_transferencia'),
    path('ajax/obtener-tc/', views.ajax_obtener_tc, name='ajax_obtener_tc'),
]