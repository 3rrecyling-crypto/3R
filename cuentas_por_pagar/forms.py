from django import forms
from .models import Factura, Pago
from compras.models import OrdenCompra
from django.utils import timezone  # Añadido para cálculo de fecha
from django.db.models import Max

# cuentas_por_pagar/forms.py

class FacturaForm(forms.ModelForm):
    class Meta:
        model = Factura
        fields = [
            'orden_compra', 'proveedor', 'numero_factura', 
            'fecha_emision', 'fecha_vencimiento', 'monto', 
            'archivo_factura', 'notas', 'cantidad_plazos'
        ]
        widgets = {
            'orden_compra': forms.Select(attrs={'class': 'form-select'}),
            'proveedor': forms.Select(attrs={'class': 'form-select'}), # Nuevo
            'cantidad_plazos': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}), # Nuevo
            'numero_factura': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_emision': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_vencimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'archivo_factura': forms.FileInput(attrs={'class': 'form-control'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # La Orden de Compra ya no es obligatoria
        self.fields['orden_compra'].required = False
        self.fields['proveedor'].required = True # El proveedor SI es obligatorio
        
        # Lógica existente para filtrar OCs
        try:
            from compras.models import OrdenCompra
            self.fields['orden_compra'].queryset = OrdenCompra.objects.filter(
                estatus__in=['APROBADA', 'AUDITADA']
            ).exclude(factura_cxp__isnull=False)
        except ImportError:
            pass

class PagoForm(forms.ModelForm):
    class Meta:
        model = Pago
        fields = [
            'fecha_pago', 'monto_pagado', 'metodo_pago', 
            'referencia', 'archivo_comprobante', 'notas'
            # Quitamos numero_plazo del usuario, ya no es relevante para el cálculo, es solo informativo
        ]
        widgets = {
            'monto_pagado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'fecha_pago': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'metodo_pago': forms.Select(attrs={'class': 'form-select'}),
            'referencia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Transferencia 123'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'archivo_comprobante': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.factura = kwargs.pop('factura', None)
        super().__init__(*args, **kwargs)
        # Si estamos editando un pago existente, obtenemos la factura de la instancia
        if self.instance.pk and self.instance.factura:
            self.factura = self.instance.factura

    def clean_monto_pagado(self):
        monto_nuevo = self.cleaned_data.get('monto_pagado')
        
        if not monto_nuevo:
            return 0

        if not self.factura:
            return monto_nuevo

        # 1. Calcular cuánto se ha pagado en TOTAL en esta factura
        pagos_existentes = self.factura.pagos.all()
        
        # Si estamos EDITANDO, excluimos el pago actual de la suma para no contarlo doble
        if self.instance.pk:
            pagos_existentes = pagos_existentes.exclude(pk=self.instance.pk)
            
        total_pagado_previamente = pagos_existentes.aggregate(total=Sum('monto_pagado'))['total'] or 0
        total_pagado_previamente = float(total_pagado_previamente)
        
        monto_factura = float(self.factura.monto)
        monto_pendiente_real = monto_factura - total_pagado_previamente
        
        # 2. Validación: El nuevo monto no puede superar lo que falta por pagar
        # Agregamos una tolerancia de 0.10 por redondeos decimales
        if float(monto_nuevo) > (monto_pendiente_real + 0.10):
            raise forms.ValidationError(
                f"El monto (${monto_nuevo}) excede la deuda pendiente (${monto_pendiente_real:,.2f}). "
                "No se puede pagar de más."
            )
            
        if float(monto_nuevo) <= 0:
             raise forms.ValidationError("El pago debe ser mayor a 0.")

        return monto_nuevo
    
    
class CXPManualForm(forms.ModelForm):
    class Meta:
        model = Factura
        fields = [
            'proveedor', 'numero_factura', 
            'fecha_emision', 'monto', 
            'cantidad_plazos', 'archivo_factura', 'notas'
        ]
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select select2'}),
            'numero_factura': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: F-90210 (Folio del Proveedor)'}),
            'fecha_emision': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'cantidad_plazos': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'value': 1}),
            'archivo_factura': forms.FileInput(attrs={'class': 'form-control'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Fecha de vencimiento se calcula sola, no la pedimos en el form manual para no confundir
        # El proveedor es obligatorio
        self.fields['proveedor'].required = True