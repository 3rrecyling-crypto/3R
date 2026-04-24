# RH/admin.py
from .models import (
    Empleado, Departamento, Puesto, MotivoInactivacion,
    TipoDocumentoOperador, DocumentoOperador, HistorialLaboral,
    Salario, Contrato, DivisionOperativa,
    TipoCarga, TipoViaje)
from django.contrib import admin
from .models import (
    Empleado, 
    Departamento, 
    Puesto, 
    MotivoInactivacion, 
    DivisionOperativa,
    TipoDocumentoOperador,
    DocumentoOperador,
    HistorialLaboral,
    Salario,
    Contrato
)

@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'puesto', 'departamento', 'activo')
    list_filter = ('activo', 'departamento', 'puesto')
    search_fields = ('nombre', 'apellido', 'email')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Si el usuario no es un superadministrador, se aplica el filtro
        if not request.user.is_superuser:
            # Si el campo es 'departamento', filtra por el usuario logueado
            if db_field.name == "departamento":
                kwargs["queryset"] = Departamento.objects.filter(creado_por=request.user)
            # Si el campo es 'puesto', filtra por el usuario logueado
            if db_field.name == "puesto":
                kwargs["queryset"] = Puesto.objects.filter(creado_por=request.user)
        
        # Devuelve el campo del formulario (filtrado o no)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

# --- Registros existentes ---
admin.site.register(DivisionOperativa)
admin.site.register(Departamento)
admin.site.register(Puesto)
admin.site.register(MotivoInactivacion)
admin.site.register(TipoDocumentoOperador)
admin.site.register(DocumentoOperador)
admin.site.register(HistorialLaboral)
admin.site.register(Salario)
admin.site.register(Contrato)

# Registra los nuevos modelos para que aparezcan en el panel de administración
admin.site.register(TipoCarga)
admin.site.register(TipoViaje)