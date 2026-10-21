from django.contrib import admin
from .models import (
    Patio, PerfilUsuarioDiesel, ProveedorDiesel, Unidad,
    Totem, CompraCombustible, AjusteInventario, CargaDiesel,
    Permisionario, PermisionarioUnidad, Thermo,
)


@admin.register(Patio)
class PatioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'codigo', 'activo', 'created_at']
    list_filter = ['activo']
    search_fields = ['nombre', 'codigo']


@admin.register(PerfilUsuarioDiesel)
class PerfilUsuarioDieselAdmin(admin.ModelAdmin):
    list_display = ['user', 'es_global']
    list_filter = ['es_global']
    filter_horizontal = ['patios']


@admin.register(ProveedorDiesel)
class ProveedorDieselAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'rfc', 'contacto', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre', 'rfc']


class PermisionarioUnidadInline(admin.TabularInline):
    model = PermisionarioUnidad
    extra = 0
    autocomplete_fields = ['unidad']


@admin.register(Permisionario)
class PermisionarioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'rfc', 'telefono', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre', 'rfc']
    inlines = [PermisionarioUnidadInline]


@admin.register(Thermo)
class ThermoAdmin(admin.ModelAdmin):
    list_display = ['identificador', 'descripcion', 'numero_serie', 'permisionario', 'activo']
    list_filter = ['activo', 'permisionario']
    search_fields = ['identificador', 'descripcion', 'numero_serie']


@admin.register(Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display = ['numero_economico', 'descripcion', 'tipo', 'patio', 'activo']
    list_filter = ['activo', 'patio']
    search_fields = ['numero_economico', 'descripcion']


@admin.register(Totem)
class TotemAdmin(admin.ModelAdmin):
    list_display = [
        'nombre', 'patio', 'cantidad_diesel', 'capacidad_diesel',
        'cantidad_urea', 'capacidad_urea', 'updated_at'
    ]
    list_filter = ['patio']
    readonly_fields = ['updated_at']


@admin.register(CompraCombustible)
class CompraCombustibleAdmin(admin.ModelAdmin):
    list_display = [
        'fecha', 'patio', 'tipo', 'proveedor', 'litros',
        'precio_unitario', 'total', 'numero_factura', 'usuario'
    ]
    list_filter = ['tipo', 'patio', 'proveedor']
    search_fields = ['numero_factura', 'proveedor_nombre']
    date_hierarchy = 'fecha'
    readonly_fields = ['total', 'proveedor_nombre']


@admin.register(AjusteInventario)
class AjusteInventarioAdmin(admin.ModelAdmin):
    list_display = [
        'fecha', 'patio', 'tipo_combustible', 'tipo_movimiento',
        'litros', 'cantidad_anterior', 'cantidad_posterior', 'motivo', 'usuario'
    ]
    list_filter = ['tipo_combustible', 'tipo_movimiento', 'patio']
    date_hierarchy = 'fecha'
    readonly_fields = ['cantidad_anterior', 'cantidad_posterior']


@admin.register(CargaDiesel)
class CargaDieselAdmin(admin.ModelAdmin):
    list_display = [
        'fecha_carga', 'patio', 'unidad', 'thermo', 'tipo_carga', 'odometro',
        'litros_diesel', 'litros_thermo', 'litros_urea',
        'costo_total', 'rendimiento', 'permisionario_nombre', 'usuario'
    ]
    list_filter = ['patio', 'tipo_carga', 'unidad']
    search_fields = ['unidad__numero_economico']
    date_hierarchy = 'fecha_carga'
    readonly_fields = ['rendimiento', 'costo_total', 'precio_litro']
