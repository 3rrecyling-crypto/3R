from django.contrib import admin

from .models import ArchivoTransferencia, Transferencia


class ArchivoInline(admin.TabularInline):
    model = ArchivoTransferencia
    extra = 0
    readonly_fields = ["nombre", "tamano"]


@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
    list_display = ["token", "titulo", "creado_por", "creado_en", "expira_en", "descargas"]
    search_fields = ["token", "titulo", "creado_por__username"]
    readonly_fields = ["token", "creado_en"]
    inlines = [ArchivoInline]
