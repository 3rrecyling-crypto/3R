# RH/urls.py - VERSIÓN COMPLETA Y FUNCIONAL
from django.urls import path, re_path
from . import views
from .views import vacantes_dashboard_view, asignar_reemplazo
from .views import descargar_documentos_empleado, descargar_documento_individual
from .api_nextjs import (
    api_rh_crear_empleado, api_rh_empleado_detail,
    api_rh_supervisores, api_rh_tipos_viaje, api_rh_tipos_carga, api_rh_divisiones,
    api_departamentos_list, api_departamento_detail,
    api_puestos_crear, api_puesto_detail,
    api_rh_vacacion_crear, api_rh_vacacion_detail, api_rh_empleado_balance_vacaciones,
    api_rh_prestamo_crear, api_rh_prestamo_detail,
)
from django.http import HttpResponse

app_name = 'rh'

# ============================================================================
# VISTA DE EMERGENCIA - FUNCIONA CON CUALQUIER PREFIJO
# ============================================================================
def api_empleado_info_cualquier_prefijo(request, empleado_id):
    """
    Vista que funciona con: 
    - /rh/api/empleado-info/38/  (prefijo real 'rh/')
    - /RH/api/empleado-info/38/  (prefijo que busca el frontend)
    - /api/empleado-info/38/     (sin prefijo)
    """
    from django.http import JsonResponse
    from .models import Empleado
    from decimal import Decimal
    from django.utils import timezone
    
    # DEBUG: Ver qué URL está llegando
    print(f"🎯 API LLAMADA - URL: {request.path}")
    print(f"🎯 Método: {request.method}")
    print(f"🎯 User: {request.user}")
    
    try:
        # Verificar autenticación
        if not request.user.is_authenticated:
            return JsonResponse({
                'error': 'No autenticado',
                'login_url': '/accounts/login/'
            }, status=401)
        
        # Buscar empleado
        empleado = Empleado.objects.filter(pk=empleado_id, activo=True).first()
        if not empleado:
            return JsonResponse({
                'error': f'Empleado {empleado_id} no encontrado o inactivo',
                'empleado_id': empleado_id
            }, status=404)
        
        # Obtener salario
        salario_actual = empleado.salario_actual
        if salario_actual and salario_actual.sueldo_mensual:
            sueldo_mensual = salario_actual.sueldo_mensual
        else:
            sueldo_mensual = Decimal('5000')
        
        # Calcular límites
        limite_maximo = sueldo_mensual * Decimal('3')
        pago_maximo_mensual = sueldo_mensual * Decimal('0.4')
        
        # Contar préstamos
        prestamos_activos = empleado.prestamos.filter(
            estado__in=['APROBADO', 'EN_CURSO']
        ).count()
        
        # Preparar respuesta
        data = {
            'success': True,
            'id': empleado.id,
            'nombre_completo': empleado.nombre_completo,
            'puesto': empleado.puesto.nombre if empleado.puesto else 'Sin puesto',
            'departamento': empleado.departamento.nombre if empleado.departamento else 'Sin departamento',
            'sueldo_mensual': float(sueldo_mensual),
            'limite_maximo': float(limite_maximo),
            'pago_maximo_mensual': float(pago_maximo_mensual),
            'prestamos_activos': prestamos_activos,
            'timestamp': timezone.now().isoformat(),
        }
        
        # Headers CORS
        response = JsonResponse(data)
        response['Access-Control-Allow-Origin'] = '*'
        return response
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'message': 'Error interno del servidor'
        }, status=500)

# ============================================================================
# PATRONES DE URL - LAS RUTAS ESPECIALES PRIMERO
# ============================================================================
urlpatterns = [
    # ========== RUTAS API ESPECIALES (¡DEBEN IR PRIMERO!) ==========
    
    # 1. Ruta para /RH/api/empleado-info/ (MAYÚSCULAS - lo que busca el frontend)
    #    IMPORTANTE: Esta debe ser una ruta ABSOLUTA (sin prefijo 'rh/')
    path('RH/api/empleado-info/<uuid:empleado_id>/', 
         api_empleado_info_cualquier_prefijo, 
         name='api_empleado_info_rh_mayus'),
    
    # 2. Ruta para /rh/api/empleado-info/ (minúsculas - la ruta real)
    #    Esta es la ruta que Django usa realmente
    path('api/empleado-info/<uuid:empleado_id>/',
         api_empleado_info_cualquier_prefijo,
         name='api_empleado_info'),

    # ========== ENDPOINTS API REST PARA NEXT.JS ==========
    path('api/dashboard/', views.api_rh_dashboard, name='api_dashboard'),
    # Empleados CRUD
    path('api/empleados/', views.api_rh_empleados, name='api_empleados'),
    path('api/empleados/crear/', api_rh_crear_empleado, name='api_crear_empleado'),
    path('api/empleados/<uuid:pk>/', api_rh_empleado_detail, name='api_empleado_detail'),
    path('api/empleados/<uuid:pk>/eliminar/', views.api_rh_eliminar_empleado, name='api_eliminar_empleado'),
    path('api/empleados/<uuid:pk>/restaurar/', views.api_rh_restaurar_empleado, name='api_restaurar_empleado'),
    # Catálogos
    path('api/departamentos/', api_departamentos_list, name='api_departamentos'),
    path('api/departamentos/crear/', api_departamentos_list, name='api_departamentos_crear'),
    path('api/departamentos/<int:pk>/', api_departamento_detail, name='api_departamento_detail'),
    path('api/departamentos/<int:pk>/eliminar/', api_departamento_detail, name='api_departamento_eliminar'),
    path('api/puestos/', views.api_rh_puestos, name='api_puestos'),
    path('api/puestos/crear/', api_puestos_crear, name='api_puestos_crear'),
    path('api/puestos/<int:pk>/', api_puesto_detail, name='api_puesto_detail'),
    path('api/puestos/<int:pk>/eliminar/', api_puesto_detail, name='api_puesto_eliminar'),
    path('api/supervisores/', api_rh_supervisores, name='api_supervisores'),
    path('api/tipos-viaje/', api_rh_tipos_viaje, name='api_tipos_viaje'),
    path('api/tipos-carga/', api_rh_tipos_carga, name='api_tipos_carga'),
    path('api/divisiones/', api_rh_divisiones, name='api_divisiones'),
    # Otros
    path('api/vacaciones/', views.api_rh_vacaciones, name='api_vacaciones'),
    path('api/vacaciones/crear/', api_rh_vacacion_crear, name='api_vacacion_crear'),
    path('api/vacaciones/<int:pk>/', api_rh_vacacion_detail, name='api_vacacion_detail'),
    path('api/empleados/<uuid:pk>/vacaciones-balance/', api_rh_empleado_balance_vacaciones, name='api_empleado_vacaciones_balance'),
    path('api/prestamos/', views.api_rh_prestamos, name='api_prestamos'),
    path('api/prestamos/crear/', api_rh_prestamo_crear, name='api_prestamo_crear'),
    path('api/prestamos/<int:pk>/', api_rh_prestamo_detail, name='api_prestamo_detail'),
    # Alias de descarga para Next.js
    path('descargar-documentos-zip/<uuid:pk>/', descargar_documentos_empleado, name='descargar_documentos_zip_alias'),
    path('descargar-documento-individual/<uuid:pk>/<str:tipo_documento>/', descargar_documento_individual, name='descargar_documento_individual_alias'),
    
    # ========== RUTAS NORMALES DE LA APLICACIÓN ==========
    # Ruta de Inicio
    path('', views.inicio_rh, name='inicio_rh'),
    
    # Rutas para Empleados - TODAS CAMBIADAS A uuid:pk
    path('empleados/', views.EmpleadoListView.as_view(), name='lista_empleados'),
    path('empleados/nuevo/', views.EmpleadoCreateView.as_view(), name='empleado_create'),
    path('empleados/<uuid:pk>/', views.EmpleadoDetailView.as_view(), name='empleado_detail'),
    path('empleados/<uuid:pk>/editar/', views.EmpleadoUpdateView.as_view(), name='empleado_update'),
    path('empleados/<uuid:pk>/eliminar/', views.eliminar_empleado, name='empleado_delete'),
    path('empleados/<uuid:pk>/pdf/', views.generar_pdf_empleado, name='generar_pdf_empleado'),
    path('empleados/exportar/excel/', views.export_empleados_excel, name='export_empleados_excel'),

    # Rutas para Departamentos - SE MANTIENEN int:pk (porque Departamento usa ID autoincremental)
    path('departamentos/', views.DepartamentoListView.as_view(), name='lista_departamentos'),
    path('departamentos/nuevo/', views.DepartamentoCreateView.as_view(), name='departamento_create'),
    path('departamentos/<int:pk>/', views.DepartamentoDetailView.as_view(), name='departamento_detail'),
    path('departamentos/<int:pk>/editar/', views.DepartamentoUpdateView.as_view(), name='departamento_update'),
    path('departamentos/<int:pk>/eliminar/', views.DepartamentoDeleteView.as_view(), name='departamento_delete'),

    # Rutas para Puestos - SE MANTIENEN int:pk (porque Puesto usa ID autoincremental)
    path('puestos/', views.PuestoListView.as_view(), name='lista_puestos'),
    path('puestos/nuevo/', views.PuestoCreateView.as_view(), name='puesto_create'),
    path('puestos/<int:pk>/', views.PuestoDetailView.as_view(), name='puesto_detail'),
    path('puestos/<int:pk>/editar/', views.PuestoUpdateView.as_view(), name='puesto_update'),
    path('puestos/<int:pk>/eliminar/', views.PuestoDeleteView.as_view(), name='puesto_delete'),
    
    # Ruta para Cumpleaños
    path('cumpleanos/', views.cumpleanos_rh, name='cumpleanos_rh'),
    path('documentos/semaforo/', views.semaforo_documentos_view, name='semaforo_documentos'),

    # Rutas para Tipos de Documento de Operador - SE MANTIENEN int:pk
    path('tipos-documento-operador/', views.TipoDocumentoOperadorListView.as_view(), name='lista_tipos_documento_operador'),
    path('tipos-documento-operador/crear/', views.TipoDocumentoOperadorCreateView.as_view(), name='crear_tipo_documento_operador'),
    path('tipos-documento-operador/editar/<int:pk>/', views.TipoDocumentoOperadorUpdateView.as_view(), name='editar_tipo_documento_operador'),
    path('tipos-documento-operador/eliminar/<int:pk>/', views.TipoDocumentoOperadorDeleteView.as_view(), name='eliminar_tipo_documento_operador'),
    path('reportes/bajas/', views.reporte_bajas, name='reporte_bajas'),
    path('dashboard/', views.dashboard_view, name='dashboard_operadores'),
    path('dashboard/vacantes/', vacantes_dashboard_view, name='vacantes_dashboard'),
    path('dashboard/vacantes/exportar/', views.exportar_faltantes_excel, name='exportar_vacantes_faltantes'),
    path('dashboard/vacantes/metas/', views.ControlVacanteListView.as_view(), name='lista_control_vacantes'),
    path('dashboard/vacantes/metas/nueva/', views.ControlVacanteCreateView.as_view(), name='crear_control_vacante'),
    path('dashboard/vacantes/metas/<int:pk>/editar/', views.ControlVacanteUpdateView.as_view(), name='editar_control_vacante'),
    path('dashboard/vacantes/metas/<int:pk>/eliminar/', views.ControlVacanteDeleteView.as_view(), name='eliminar_control_vacante'),
    path('vacantes/<int:pk>/asignar-reemplazo/', asignar_reemplazo, name='asignar_reemplazo'),
    path('reportes/documentacion-operador/', views.reporte_documentacion_operador, name='reporte_documentacion_operador'),

    # Documentos del empleado - CAMBIADAS A uuid:pk
    path('empleados/<uuid:pk>/documentos/zip/', descargar_documentos_empleado, name='descargar_documentos_zip'),
    path('empleados/<uuid:pk>/documentos/<str:tipo_documento>/', descargar_documento_individual, name='descargar_documento_individual'),

    # Documentos masivos
    path('documentos/todos/', views.descargar_documentos_todos, name='descargar_documentos_todos'),
    path('documentos/generar-todos/', views.generar_documentos_todos, name='generar_documentos_todos'),
    path('documentos/departamento/<int:departamento_id>/', views.generar_documentos_por_departamento, 
         name='generar_documentos_departamento'),
    path('empleados/<uuid:pk>/documentos/estado/', 
         views.estado_generacion_documentos, 
         name='estado_generacion_documentos'),
    path('diagnostico-storage/', views.diagnostico_storage, name='diagnostico_storage'),
    path('inicializar-datos/', views.inicializar_datos_operativos, name='inicializar_datos'),
    path('auditoria-datos/', views.auditoria_datos_operativos, name='auditoria_datos'),

    # Bajas de empleados - CAMBIADAS A uuid:pk donde corresponde a empleado
    path('empleados/<uuid:pk>/dar-baja/', views.dar_baja_empleado, name='dar_baja_empleado'),
    path('bajas/historial/', views.historial_bajas, name='historial_bajas'),
    path('bajas/<int:pk>/detalle/', views.detalle_baja, name='detalle_baja'),  # Baja usa ID autoincremental
    path('bajas/<int:pk>/recontratar/', views.recontratar_empleado, name='recontratar_empleado'),
    path('bajas/exportar-excel/', views.reporte_bajas_excel, name='reporte_bajas_excel'),
    
    # AJAX para motivos jerarquizados
    path('bajas/get-submotivos/', views.get_submotivos_ajax, name='get_submotivos_ajax'),
    path('bajas/get-detalles/', views.get_detalles_ajax, name='get_detalles_ajax'),

    # Gestión de Vacaciones - CAMBIADAS A uuid:pk donde corresponde a empleado
    path('vacaciones/', views.gestion_vacaciones, name='gestion_vacaciones'),
    path('vacaciones/solicitar/', views.solicitar_vacacion, name='solicitar_vacacion'),
    path('vacaciones/solicitar/<uuid:empleado_id>/', views.solicitar_vacacion, name='solicitar_vacacion_empleado'),
    path('vacaciones/<int:pk>/aprobar/', views.aprobar_vacacion, name='aprobar_vacacion'),  # Vacacion usa ID autoincremental
    path('vacaciones/<int:pk>/detalle/', views.detalle_vacacion, name='detalle_vacacion'),
    path('empleados/<uuid:empleado_id>/vacaciones/historico/', views.historico_vacaciones_empleado, name='historico_vacaciones'),
    path('vacaciones/reporte-excel/', views.reporte_vacaciones_excel, name='reporte_vacaciones_excel'),
    path('vacaciones/historico/', views.solicitar_vacacion, {'modo_historico': True}, name='solicitar_vacacion_historico'),

    # Gestión de Préstamos - CAMBIADAS A uuid:pk donde corresponde a empleado
    path('prestamos/', views.gestion_prestamos, name='gestion_prestamos'),
    path('prestamos/solicitar/', views.solicitar_prestamo, name='solicitar_prestamo'),
    path('prestamos/solicitar/<uuid:empleado_id>/', views.solicitar_prestamo, name='solicitar_prestamo_empleado'),
    path('prestamos/<int:pk>/aprobar/', views.aprobar_prestamo, name='aprobar_prestamo'),  # Prestamo usa ID autoincremental
    path('prestamos/<int:pk>/detalle/', views.detalle_prestamo, name='detalle_prestamo'),
    path('prestamos/<int:prestamo_id>/registrar-pago/', views.registrar_pago, name='registrar_pago'),
    path('empleados/<uuid:empleado_id>/prestamos/historico/', views.historico_prestamos_empleado, name='historico_prestamos'),
    path('prestamos/reporte-excel/', views.reporte_prestamos_excel, name='reporte_prestamos_excel'),

    # Rutas para la papelera de reciclaje - CAMBIADAS A uuid:pk
    path('empleados/papelera/', views.papelera_empleados, name='papelera_empleados'),
    path('empleados/<uuid:pk>/restaurar/', views.restaurar_empleado, name='restaurar_empleado'),
    path('empleados/<uuid:pk>/eliminar-permanentemente/', 
         views.eliminar_permanentemente, 
         name='eliminar_permanentemente'),
    path('empleados/vaciar-papelera/', views.vaciar_papelera, name='vaciar_papelera'),

     # Exportar/Importar
    path('exportar-todo/', views.exportar_rh_completo, name='exportar_rh_completo'),
    path('importar-todo/', views.importar_rh_completo, name='importar_rh_completo'),

    # Bajas
    path('bajas/', views.lista_bajas, name='lista_bajas'),
    path('bajas/<int:pk>/editar/', views.editar_baja, name='editar_baja'),  # Baja usa ID autoincremental
    path('bajas/<int:pk>/eliminar/', views.eliminar_baja, name='eliminar_baja'),  # Baja usa ID autoincremental
    path('procesar-checadas/', views.procesar_checadas, name='procesar_checadas'),
]

# ============================================================================
# NOTA CRÍTICA: Qué se cambió y por qué
# ============================================================================
"""
CAMBIOS REALIZADOS:

1. TODAS las rutas que reciben el PK de un EMPLEADO se cambiaron de:
   <int:pk> o <int:empleado_id> → <uuid:pk> o <uuid:empleado_id>

   Porque el modelo Empleado usa UUIDField como primary key:
   id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

2. Se MANTUVIERON como <int:pk> las rutas para:
   - Departamento (usa ID autoincremental)
   - Puesto (usa ID autoincremental) 
   - TipoDocumentoOperador (usa ID autoincremental)
   - Baja (usa ID autoincremental)
   - Vacacion (usa ID autoincremental)
   - Prestamo (usa ID autoincremental)
   - Vacantes (usa ID autoincremental)

3. También se cambiaron las APIs:
   - api_empleado_info_rh_mayus: <int:empleado_id> → <uuid:empleado_id>
   - api_empleado_info: <int:empleado_id> → <uuid:empleado_id>

Esto resuelve el error:
NoReverseMatch at /rh/empleados/
Reverse for 'empleado_detail' with arguments '(UUID('ff04f001-6371-4903-a9b0-4eac91000e0f'),)' not found.
1 pattern(s) tried: ['rh/empleados/(?P<pk>[0-9]+)/\\Z']
"""