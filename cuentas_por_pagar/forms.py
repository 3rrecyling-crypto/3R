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
    numero_plazo = forms.IntegerField(
        required=False,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
            'placeholder': 'Número del plazo'
        }),
        help_text="Número del plazo (1 para primer plazo, 2 para segundo, etc.)"
    )
    
    fecha_plazo_programado = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Fecha programada para este plazo (opcional)"
    )
    
    class Meta:
        model = Pago
        fields = [
            'factura', 'fecha_pago', 'monto_pagado', 'metodo_pago', 
            'referencia', 'archivo_comprobante', 'numero_plazo',
            'fecha_plazo_programado', 'notas'
        ]
        # AQUÍ ES DONDE OCURRE LA MAGIA:
        widgets = {
            'numero_plazo': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': '1'  # <--- NECESARIO para Floating Label
            }),
            'monto_pagado': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': '0.00', # <--- NECESARIO
                'step': '0.01'
            }),
            'fecha_pago': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date',
                'placeholder': 'yyyy-mm-dd' # <--- NECESARIO (aunque sea date)
            }),
            'metodo_pago': forms.Select(attrs={
                'class': 'form-select', # <--- OJO: Para selects usa 'form-select' no 'form-control'
                'placeholder': 'Seleccione'
            }),
            'referencia': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Transferencia 12345' # <--- NECESARIO
            }),
            'notas': forms.Textarea(attrs={
                'class': 'form-control', 
                'placeholder': 'Comentarios adicionales',
                'rows': 3
            }),
            'archivo_comprobante': forms.FileInput(attrs={
                'class': 'form-control' # Los archivos no usan placeholder, eso está bien
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer el campo factura no requerido si se pasa en el initial
        if 'factura' in self.initial:
            self.fields['factura'].required = False
    
    def clean_monto_pagado(self):
        """Validación flexible del monto pagado (±10% del monto sugerido)"""
        monto_pagado = self.cleaned_data.get('monto_pagado')
        factura = self.cleaned_data.get('factura')
        
        # Si no hay factura o monto, no validar
        if not factura or not monto_pagado:
            return monto_pagado
        
        # Solo validar para facturas a plazos
        if not factura.es_pago_plazos:
            return monto_pagado
        
        # Calcular márgenes
        monto_minimo = float(factura.monto_minimo_permitido)
        monto_maximo = float(factura.monto_maximo_permitido)
        
        # Validar que esté dentro del rango permitido
        if monto_pagado < monto_minimo:
            raise forms.ValidationError(
                f"El monto pagado (${monto_pagado:.2f}) es menor al mínimo permitido (${monto_minimo:.2f}). "
            )
        
        if monto_pagado > monto_maximo:
            raise forms.ValidationError(
                f"El monto pagado (${monto_pagado:.2f}) excede el máximo permitido (${monto_maximo:.2f}). "
            )
        
        return monto_pagado
    
    def clean(self):
        """Validación adicional para el número de plazo"""
        cleaned_data = super().clean()
        factura = cleaned_data.get('factura')
        numero_plazo = cleaned_data.get('numero_plazo')
        
        if factura and numero_plazo:
            # Validar que el número de plazo no esté ya pagado
            if factura.pagos.filter(numero_plazo=numero_plazo).exists():
                raise forms.ValidationError(
                    f"El plazo #{numero_plazo} ya fue registrado para esta factura."
                )
            
            # Validar que el número de plazo no exceda la cantidad programada
            if factura.es_pago_plazos and numero_plazo > factura.cantidad_plazos:
                raise forms.ValidationError(
                    f"El plazo #{numero_plazo} excede el número total de plazos programados ({factura.cantidad_plazos})."
                )
        
        return cleaned_data
    
    
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