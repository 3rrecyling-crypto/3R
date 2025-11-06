from django import forms
from .models import Factura, Pago
from compras.models import OrdenCompra
from django.utils import timezone  # Añadido para cálculo de fecha

class FacturaForm(forms.ModelForm):
    class Meta:
        model = Factura
        fields = ['orden_compra', 'numero_factura', 'fecha_emision', 'fecha_vencimiento', 'monto', 'notas']
        widgets = {
            'orden_compra': forms.Select(attrs={'class': 'form-select'}),
            'numero_factura': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_emision': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_vencimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from compras.models import OrdenCompra
            # Filtra OCs auditadas o aprobadas que no tengan factura
            self.fields['orden_compra'].queryset = OrdenCompra.objects.filter(
                estatus__in=['APROBADA', 'AUDITADA']
            ).exclude(factura_cxp__isnull=False)
            
            if self.instance and self.instance.pk:
                # Si es edición, calcula fecha de vencimiento basado en OC
                dias_credito = getattr(self.instance.orden_compra.proveedor, 'dias_credito', 30)
                self.fields['fecha_vencimiento'].initial = self.instance.orden_compra.fecha_emision + timezone.timedelta(days=dias_credito)
        except ImportError:
            # Si no se puede importar OrdenCompra, deshabilitar el campo
            self.fields['orden_compra'].queryset = Factura.objects.none()
            self.fields['orden_compra'].help_text = "No se pudo cargar las órdenes de compra"

class PagoForm(forms.ModelForm):
    class Meta:
        model = Pago
        fields = ['factura', 'fecha_pago', 'monto_pagado', 'metodo_pago', 'referencia', 'notas']
        widgets = {
            'factura': forms.Select(attrs={'class': 'form-select'}),
            'fecha_pago': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'monto_pagado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'metodo_pago': forms.Select(attrs={'class': 'form-select'}),
            'referencia': forms.TextInput(attrs={'class': 'form-control'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtra facturas pendientes
        self.fields['factura'].queryset = Factura.objects.filter(pagada=False)