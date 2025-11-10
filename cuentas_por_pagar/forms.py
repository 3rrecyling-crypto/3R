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
            'orden_compra', 'numero_factura', 'fecha_emision', 
            'fecha_vencimiento', 'monto', 'archivo_factura', 'notas'
        ]
        widgets = {
            'orden_compra': forms.Select(attrs={'class': 'form-select'}),
            'numero_factura': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_emision': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_vencimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'archivo_factura': forms.FileInput(attrs={'class': 'form-control'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Importación local para evitar circular imports
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