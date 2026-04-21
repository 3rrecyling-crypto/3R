from django.urls import path
from . import views, api_views

urlpatterns = [
    # ── API JSON (Next.js) ──────────────────────────────────────────────────
    path('api/cuentas/',                    api_views.api_lista_cuentas,        name='api_bancos_cuentas'),
    path('api/movimientos/',                api_views.api_lista_movimientos,     name='api_bancos_lista'),
    path('api/movimientos/crear/',          api_views.api_crear_movimiento,      name='api_bancos_crear'),
    path('api/movimientos/importar/',       api_views.api_importar_movimientos,  name='api_bancos_importar'),
    path('api/movimientos/<int:pk>/',       api_views.api_detalle_movimiento,    name='api_bancos_detalle'),
    path('api/movimientos/<int:pk>/editar/', api_views.api_editar_eliminar_movimiento, name='api_bancos_editar'),
    path('api/lookup/',                    api_views.api_lookup_data,           name='api_bancos_lookup'),
    path('api/resumen/',                   api_views.api_resumen_list_create,   name='api_bancos_resumen'),
    path('api/resumen/<str:periodo>/',     api_views.api_resumen_detail,        name='api_bancos_resumen_detail'),
    path('api/categorias/',                api_views.api_categorias,            name='api_bancos_categorias'),
    path('api/categorias/<int:pk>/',       api_views.api_categoria_detail,      name='api_bancos_categoria_detail'),
    path('api/subcategorias/',             api_views.api_subcategorias_crear,   name='api_bancos_subcategorias_crear'),
    path('api/subcategorias/<int:pk>/',    api_views.api_subcategoria_detail,   name='api_bancos_subcategoria_detail'),
    # ───────────────────────────────────────────────────────────────────────
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
    path('importar-movimientos/', views.importar_movimientos, name='importar_movimientos'),

    
    path('categorias/', views.gestion_categorias_view, name='bancos_categorias_lista'), # <--- NOMBRE ÚNICO
    
    path('categorias/crear/', views.crear_categoria, name='bancos_crear_categoria'),
    path('categorias/editar/<int:pk>/', views.editar_categoria, name='bancos_editar_categoria'),
    path('categorias/eliminar/<int:pk>/', views.eliminar_categoria, name='bancos_eliminar_categoria'),
    
    path('subcategorias/crear/', views.crear_subcategoria, name='bancos_crear_subcategoria'),
    path('subcategorias/editar/<int:pk>/', views.editar_subcategoria, name='bancos_editar_subcategoria'),
    path('subcategorias/eliminar/<int:pk>/', views.eliminar_subcategoria, name='bancos_eliminar_subcategoria'),
    path('movimientos/eliminar/<int:pk>/', views.eliminar_movimiento, name='eliminar_movimiento'),
    path('movimientos/subir-comprobante/<int:movimiento_id>/', views.subir_comprobante, name='subir_comprobante'),
    path('movimientos/borrar-comprobante/<int:comprobante_id>/', views.eliminar_comprobante, name='eliminar_comprobante'),
]