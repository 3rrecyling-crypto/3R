from django.contrib import admin

from .models import Ticket, TicketArchivo, TicketComentario


class TicketComentarioInline(admin.TabularInline):
    model = TicketComentario
    extra = 0
    readonly_fields = ('autor', 'tipo', 'mensaje', 'creado_en')


class TicketArchivoInline(admin.TabularInline):
    model = TicketArchivo
    extra = 0
    readonly_fields = ('nombre', 'tamano', 'subido_por', 'subido_en')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('folio', 'titulo', 'tipo', 'prioridad', 'estado', 'solicitante', 'asignado_a',
                    'fecha_recepcion', 'fecha_seguimiento')
    list_filter = ('estado', 'tipo', 'prioridad', 'modulo')
    search_fields = ('folio', 'titulo', 'descripcion')
    readonly_fields = ('folio', 'fecha_recepcion', 'fecha_resolucion', 'fecha_cierre', 'actualizado_en')
    inlines = [TicketArchivoInline, TicketComentarioInline]
