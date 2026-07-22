from django.contrib import admin

from .models import SimulacionViaje


@admin.register(SimulacionViaje)
class SimulacionViajeAdmin(admin.ModelAdmin):
    list_display = ["nombre", "es_plantilla", "creado_por", "actualizado"]
    list_filter = ["es_plantilla"]
    search_fields = ["nombre"]
