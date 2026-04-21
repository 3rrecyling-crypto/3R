from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Factura, Pago

@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ['numero_factura', 'orden_compra', 'monto', 'estatus']

@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ['factura', 'fecha_pago', 'monto_pagado', 'metodo_pago']