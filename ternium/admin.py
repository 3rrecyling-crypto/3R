from django.contrib import admin
from .models import (
    Origen, Empresa, LineaTransporte, Operador, Material, 
    Unidad, Contenedor, Lugar, Remision, Cliente, 
    DetalleRemision, InventarioPatio, Descarga, 
    RegistroLogistico, EntradaMaquila, Profile,
    # --- Nuevos Modelos Importados ---
    EvidenciaRemision, HistorialRemision,
    Plastico, EvidenciaPlastico, HistorialPlastico,
    ControlTarima
)

# --- INLINES (Tablas dentro de otros formularios) ---

class DetalleRemisionInline(admin.TabularInline):
    model = DetalleRemision
    extra = 0
    autocomplete_fields = ['material', 'cliente']

class EvidenciaRemisionInline(admin.TabularInline):
    model = EvidenciaRemision
    extra = 0
    readonly_fields = ('creado_en',)

class HistorialRemisionInline(admin.TabularInline):
    model = HistorialRemision
    extra = 0
    readonly_fields = ('usuario', 'fecha', 'cambio')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

class EvidenciaPlasticoInline(admin.TabularInline):
    model = EvidenciaPlastico
    extra = 0
    readonly_fields = ('subido_en',)

class HistorialPlasticoInline(admin.TabularInline):
    model = HistorialPlastico
    extra = 0
    readonly_fields = ('usuario', 'fecha', 'cambio')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

# --- CONFIGURACIÓN DE MODELOS ---

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'area', 'telefono', 'get_empresas_autorizadas')
    search_fields = ('user__username', 'user__email', 'area')
    filter_horizontal = ('empresas_autorizadas',) 

    def get_empresas_autorizadas(self, obj):
        return ", ".join([e.nombre for e in obj.empresas_autorizadas.all()])
    get_empresas_autorizadas.short_description = 'Empresas Asignadas'

@admin.register(Origen)
class OrigenAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'prefijo', 'creado_en')
    search_fields = ('nombre', 'prefijo')
    filter_horizontal = ('origenes',)

@admin.register(LineaTransporte)
class LineaTransporteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'creado_en')
    search_fields = ('nombre',)
    filter_horizontal = ('empresas',)

@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'folio', 'creado_en')
    search_fields = ('nombre', 'folio')

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'clave_sat', 'clave_unidad_sat', 'creado_en')
    search_fields = ('nombre', 'clave_sat')
    filter_horizontal = ('empresas',)

@admin.register(Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display = ('internal_id', 'license_plate', 'asset_type', 'operational_status', 'ownership')
    list_filter = ('asset_type', 'operational_status', 'ownership', 'empresas')
    search_fields = ('internal_id', 'license_plate', 'vin')
    filter_horizontal = ('empresas',)
    list_per_page = 50

@admin.register(Contenedor)
class ContenedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'placas', 'creado_en')
    search_fields = ('nombre', 'placas')
    filter_horizontal = ('empresas',)

@admin.register(Lugar)
class LugarAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'es_patio', 'rfc')
    list_filter = ('tipo', 'es_patio', 'empresas')
    search_fields = ('nombre', 'rfc', 'razon_social')
    filter_horizontal = ('empresas',)

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'creado_en')
    search_fields = ('nombre',)
    filter_horizontal = ('empresas',)

@admin.register(Remision)
class RemisionAdmin(admin.ModelAdmin):
    list_display = ('remision', 'fecha', 'empresa', 'status', 'origen', 'destino', 'total_peso_ld', 'total_peso_dlv')
    list_filter = ('status', 'fecha', 'empresa', 'origen', 'destino')
    search_fields = ('remision', 'folio_ld', 'folio_dlv', 'operador__nombre')
    date_hierarchy = 'fecha'
    
    # Se agregaron los inlines de Evidencia e Historial
    inlines = [DetalleRemisionInline, EvidenciaRemisionInline, HistorialRemisionInline]
    
    autocomplete_fields = ['empresa', 'operador', 'linea_transporte', 'unidad', 'contenedor', 'origen', 'destino', 'cliente']
    list_per_page = 50

@admin.register(InventarioPatio)
class InventarioPatioAdmin(admin.ModelAdmin):
    list_display = ('patio', 'material', 'cantidad', 'ultima_actualizacion')
    list_filter = ('patio', 'material')
    search_fields = ('patio__nombre', 'material__nombre')
    readonly_fields = ('ultima_actualizacion',)

@admin.register(Descarga)
class DescargaAdmin(admin.ModelAdmin):
    list_display = ('origen', 'destino', 'material', 'cantidad', 'fecha_descarga', 'registrado_por')
    list_filter = ('fecha_descarga', 'origen', 'destino', 'material')
    date_hierarchy = 'fecha_descarga'
    list_per_page = 50

@admin.register(RegistroLogistico)
class RegistroLogisticoAdmin(admin.ModelAdmin):
    list_display = ('remision', 'fecha_carga', 'status', 'transportista', 'toneladas_remisionadas', 'toneladas_recibidas')
    list_filter = ('status', 'fecha_carga', 'transportista')
    search_fields = ('remision', 'boleta_bascula', 'chofer', 'tractor', 'tolva')
    date_hierarchy = 'fecha_carga'
    autocomplete_fields = ['transportista', 'material']
    list_per_page = 50

@admin.register(EntradaMaquila)
class EntradaMaquilaAdmin(admin.ModelAdmin):
    list_display = ('c_id_remito', 'fecha_ingreso', 'status', 'transporte', 'peso_neto', 'alerta')
    list_filter = ('status', 'fecha_ingreso', 'alerta')
    search_fields = ('c_id_remito', 'num_boleta_remision', 'transporte')
    date_hierarchy = 'fecha_ingreso'
    list_per_page = 50

# --- NUEVOS ADMINISTRADORES ---

@admin.register(Plastico)
class PlasticoAdmin(admin.ModelAdmin):
    list_display = ('remision', 'fecha', 'empresa', 'status', 'peso', 'venta', 'pagado')
    list_filter = ('status', 'empresa', 'fecha', 'pagado')
    search_fields = ('remision', 'operador', 'unidad', 'descripcion')
    date_hierarchy = 'fecha'
    autocomplete_fields = ['empresa', 'origen', 'destino']
    inlines = [EvidenciaPlasticoInline, HistorialPlasticoInline]
    list_per_page = 50

@admin.register(ControlTarima)
class ControlTarimaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'origen', 'destino', 'gran_total')
    list_filter = ('fecha', 'origen', 'destino')
    search_fields = ('origen__nombre', 'destino__nombre', 'comentarios')
    date_hierarchy = 'fecha'
    list_per_page = 50