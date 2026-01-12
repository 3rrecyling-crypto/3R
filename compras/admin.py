# compras/admin.py

from django.contrib import admin
from .models import (
    Proveedor, Categoria, UnidadMedida, Articulo, ArticuloProveedor,
    SolicitudCompra, DetalleSolicitud, OrdenCompra, DetalleOrdenCompra
)

# --- INLINES (Para ver detalles dentro del padre) ---

class ArticuloProveedorInline(admin.TabularInline):
    model = ArticuloProveedor
    extra = 1
    autocomplete_fields = ['proveedor']

class DetalleSolicitudInline(admin.TabularInline):
    model = DetalleSolicitud
    extra = 0
    autocomplete_fields = ['articulo']

class DetalleOrdenCompraInline(admin.TabularInline):
    model = DetalleOrdenCompra
    extra = 0
    autocomplete_fields = ['articulo']

# --- MODEL ADMINS ---

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'rfc', 'empresa', 'lugar', 'contacto_principal', 'activo')
    list_filter = ('activo', 'empresa', 'lugar')
    search_fields = ('razon_social', 'rfc', 'contacto_principal', 'email_contacto')
    ordering = ('razon_social',)

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'parent')
    search_fields = ('nombre',)
    ordering = ('nombre',)

@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'abreviatura')
    search_fields = ('nombre', 'abreviatura')

@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'sku', 'empresa', 'categoria', 'tipo', 'activo')
    list_filter = ('activo', 'tipo', 'empresa', 'categoria')
    search_fields = ('nombre', 'sku', 'descripcion')
    inlines = [ArticuloProveedorInline]
    # Autocomplete para que cargue rápido si tienes muchos artículos
    search_fields = ['nombre', 'sku'] 

@admin.register(SolicitudCompra)
class SolicitudCompraAdmin(admin.ModelAdmin):
    list_display = ('folio', 'empresa', 'solicitante', 'proveedor', 'estatus', 'prioridad', 'creado_en')
    list_filter = ('estatus', 'prioridad', 'empresa', 'creado_en')
    search_fields = ('folio', 'motivo', 'solicitante__username', 'solicitante__first_name')
    readonly_fields = ('folio', 'creado_en', 'fecha_aprobacion', 'aprobado_por')
    inlines = [DetalleSolicitudInline]
    
    # Organizar campos en secciones
    fieldsets = (
        ('Información General', {
            'fields': ('folio', 'empresa', 'lugar', 'solicitante', 'estatus', 'prioridad')
        }),
        ('Detalle', {
            'fields': ('motivo', 'proveedor', 'cotizacion')
        }),
        ('Aprobación', {
            'fields': ('aprobado_por', 'fecha_aprobacion')
        }),
    )

@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = ('folio', 'proveedor', 'empresa', 'estatus', 'fecha_entrega_esperada', 'total_display')
    list_filter = ('estatus', 'empresa', 'moneda', 'fecha_emision')
    search_fields = ('folio', 'proveedor__razon_social')
    readonly_fields = ('folio', 'creado_en', 'creado_por', 'lista_para_auditoria')
    inlines = [DetalleOrdenCompraInline]

    fieldsets = (
        ('Encabezado', {
            'fields': ('folio', 'solicitud_origen', 'empresa', 'proveedor', 'estatus')
        }),
        ('Finanzas y Plazos', {
            'fields': ('moneda', 'tipo_cambio', 'condiciones_pago', 'modalidad_pago', 'cantidad_plazos', 'fecha_entrega_esperada')
        }),
        ('Auditoría', {
            'fields': ('factura', 'factura_subida', 'comprobante_pago', 'comprobante_pago_subido', 'lista_para_auditoria')
        }),
        ('Control', {
            'fields': ('creado_por', 'creado_en')
        }),
    )

    def total_display(self, obj):
        return f"${obj.total_general:,.2f} {obj.moneda}"
    total_display.short_description = "Total General"

# Registro simple para modelos intermedios si necesitas verlos directo
@admin.register(ArticuloProveedor)
class ArticuloProveedorAdmin(admin.ModelAdmin):
    list_display = ('articulo', 'proveedor', 'precio_unitario', 'ultima_actualizacion')
    list_filter = ('proveedor', 'ultima_actualizacion')
    search_fields = ('articulo__nombre', 'proveedor__razon_social')