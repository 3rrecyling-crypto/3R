from django.contrib import admin

from .models import Diagrama, DiagramaCompartido


@admin.register(Diagrama)
class DiagramaAdmin(admin.ModelAdmin):
    list_display = ("id", "titulo", "creado_por", "publico", "actualizado")
    list_filter = ("publico",)
    search_fields = ("titulo", "descripcion")


@admin.register(DiagramaCompartido)
class DiagramaCompartidoAdmin(admin.ModelAdmin):
    list_display = ("id", "diagrama", "usuario", "permiso", "compartido_por", "creado")
    list_filter = ("permiso",)
    search_fields = ("diagrama__titulo", "usuario__username")
    autocomplete_fields = ("diagrama", "usuario", "compartido_por")
