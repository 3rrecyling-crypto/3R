from django.contrib import admin
from .models import (
    Cuenta, 
    Movimiento, 
    Categoria, 
    SubCategoria, 
    Tercero, 
    UnidadNegocio, 
    Operacion,
    ComprobanteFiscal
)

# --- INLINES ---
# Esto permite subir/ver los XML y PDFs directamente dentro de la pantalla del Movimiento
class ComprobanteFiscalInline(admin.TabularInline):
    model = ComprobanteFiscal
    extra = 0
    readonly_fields = ('fecha_subida', 'monto_iva', 'uuid')
    fields = ('archivo_xml', 'archivo_pdf', 'uuid', 'monto_iva', 'fecha_subida')
    can_delete = True

# --- ADMIN PRINCIPAL ---

@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'concepto_corto', 'cuenta', 'cargo_fmt', 'abono_fmt', 'estatus', 'tiene_xml')
    list_filter = ('cuenta', 'estatus', 'fecha', 'categoria', 'auditado')
    search_fields = ('concepto', 'tercero__nombre', 'comprobantes__uuid')
    date_hierarchy = 'fecha'
    inlines = [ComprobanteFiscalInline]
    
    # Opciones de visualización
    list_per_page = 20

    def concepto_corto(self, obj):
        return (obj.concepto[:40] + '..') if len(obj.concepto) > 40 else obj.concepto
    concepto_corto.short_description = "Concepto"

    def cargo_fmt(self, obj):
        if obj.cargo and obj.cargo > 0:
            return f"${obj.cargo:,.2f}"
        return "-"
    cargo_fmt.short_description = "Cargo"

    def abono_fmt(self, obj):
        if obj.abono and obj.abono > 0:
            return f"${obj.abono:,.2f}"
        return "-"
    abono_fmt.short_description = "Abono"
    
    def tiene_xml(self, obj):
        count = obj.comprobantes.count()
        return f"✅ {count}" if count > 0 else "❌"
    tiene_xml.short_description = "XMLs"

@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'moneda', 'saldo_actual_display')
    
    def saldo_actual_display(self, obj):
        # Muestra el saldo calculado de la propiedad @property
        return f"${obj.saldo_actual:,.2f}"
    saldo_actual_display.short_description = "Saldo Actual"

@admin.register(Tercero)
class TerceroAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'celular')
    search_fields = ('nombre', 'celular')
    list_filter = ('tipo',)

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(SubCategoria)
class SubCategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria')
    list_filter = ('categoria',)
    search_fields = ('nombre',)

# Registros simples para catálogos menores
admin.site.register(UnidadNegocio)
admin.site.register(Operacion)

# Opcional: registrar ComprobanteFiscal por separado si quieres ver solo los archivos
@admin.register(ComprobanteFiscal)
class ComprobanteFiscalAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'movimiento', 'monto_iva', 'fecha_subida')
    search_fields = ('uuid', 'movimiento__concepto')
    list_filter = ('fecha_subida',)