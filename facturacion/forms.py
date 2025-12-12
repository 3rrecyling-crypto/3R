from django import forms
from .models import Factura, DatosFiscales, ComplementoPago
from ternium.models import Lugar
from django.db.models import Sum

USO_CFDI_CHOICES = [
    ('G03', 'G03 - Gastos en general'),
    ('G01', 'G01 - Adquisición de mercancías'),
    ('P01', 'P01 - Por definir'),
]

METODO_PAGO_CHOICES = [
    ('PUE', 'PUE - Pago en una sola exhibición'),
    ('PPD', 'PPD - Pago en parcialidades o diferido'),
]

FORMA_PAGO_CHOICES = [
    ('01', '01 - Efectivo'),
    ('03', '03 - Transferencia electrónica'),
    ('99', '99 - Por definir'),
]

class DatosFiscalesForm(forms.ModelForm):
    class Meta:
        model = DatosFiscales
        fields = '__all__'
        widgets = {
            'rfc': forms.TextInput(attrs={'class': 'form-control', 'style': 'text-transform:uppercase;'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_postal': forms.TextInput(attrs={'class': 'form-control'}),
            'regimen_fiscal': forms.Select(attrs={'class': 'form-select'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control'}),
            'empresa_interna': forms.HiddenInput(), # Se asigna automáticamente
            'cliente_interno': forms.HiddenInput()
        }

class GenerarFacturaForm(forms.ModelForm):
    # Campos que no están en el modelo Factura directamente o necesitan widgets especiales
    uso_cfdi = forms.ChoiceField(choices=USO_CFDI_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    metodo_pago = forms.ChoiceField(choices=METODO_PAGO_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    forma_pago = forms.ChoiceField(choices=FORMA_PAGO_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    
    aplicar_retencion = forms.BooleanField(
        required=False, 
        label="Aplicar Retención de IVA (6%)", 
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'onchange': 'calcularTotales()'})
    )

    class Meta:
        model = Factura
        fields = ['moneda', 'tipo_cambio'] # Solo los que guardamos directo
        widgets = {
            'moneda': forms.TextInput(attrs={'class': 'form-control', 'value': 'MXN'}),
            'tipo_cambio': forms.NumberInput(attrs={'class': 'form-control', 'value': '1.0', 'step': '0.0001'}),
        }
class PagoForm(forms.ModelForm):
    # --- CORRECCIÓN AQUÍ TAMBIÉN ---
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Forma de Pago"
    )

    class Meta:
        model = ComplementoPago
        fields = ['fecha_pago', 'forma_pago', 'monto_total', 'num_operacion']
        widgets = {
            'fecha_pago': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'monto_total': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'num_operacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Referencia bancaria'}),
        }
        
class NuevaFacturaLibreForm(forms.ModelForm):
    receptor = forms.ModelChoiceField(
        queryset=DatosFiscales.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Cliente / Receptor",
        empty_label="Seleccione un Cliente"
    )
    
    # Checkbox para activar retención de IVA (común en reciclaje)
    aplicar_retencion = forms.BooleanField(
        required=False, 
        label="Aplicar Retención de IVA (6% o cálculo manual)",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Factura
        fields = ['receptor', 'uso_cfdi', 'metodo_pago', 'forma_pago', 'moneda', 'tipo_cambio']
        widgets = {
            'uso_cfdi': forms.Select(attrs={'class': 'form-select'}),
            'metodo_pago': forms.Select(attrs={'class': 'form-select'}),
            'forma_pago': forms.Select(attrs={'class': 'form-select'}),
            'moneda': forms.TextInput(attrs={'class': 'form-control', 'value': 'MXN'}),
            'tipo_cambio': forms.NumberInput(attrs={'class': 'form-control', 'value': '1.0'}),
        }
        
class ConfigurarEmisorForm(forms.Form):
    lugar_origen = forms.ModelChoiceField(
        queryset=Lugar.objects.all(),
        label="Selecciona el Lugar que contiene TUS datos fiscales",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Se copiará el RFC, Razón Social y Dirección de este lugar para usarse como Emisor."
    )
    
    
class DatosFiscalesClienteForm(forms.ModelForm):
    """Formulario para capturar RFC del cliente al vuelo"""
    class Meta:
        model = DatosFiscales
        # --- CORRECCIÓN: Cambiamos 'uso_cfdi_preferido' por 'uso_cfdi' ---
        fields = ['razon_social', 'rfc', 'regimen_fiscal', 'codigo_postal', 'uso_cfdi']
        
        widgets = {
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control text-uppercase'}),
            'regimen_fiscal': forms.Select(attrs={'class': 'form-select'}),
            'codigo_postal': forms.TextInput(attrs={'class': 'form-control'}),
            # Si quieres agregar widget para uso_cfdi:
            'uso_cfdi': forms.Select(attrs={'class': 'form-select'}),
        
        }
        
    
class PagoForm(forms.ModelForm):
    class Meta:
        model = ComplementoPago
        # CAMBIO: Usamos 'monto_total' en lugar de 'monto'
        fields = ['fecha_pago', 'forma_pago', 'monto_total', 'num_operacion']
        widgets = {
            'fecha_pago': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'forma_pago': forms.Select(attrs={'class': 'form-select'}),
            'monto_total': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'num_operacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Referencia bancaria'}),
        }

    def __init__(self, *args, **kwargs):
        self.factura_obj = kwargs.pop('factura_obj', None)
        super().__init__(*args, **kwargs)

    # CAMBIO: Renombramos la validación a clean_monto_total
    def clean_monto_total(self):
        monto = self.cleaned_data.get('monto_total')
        if self.factura_obj and monto:
            # CAMBIO: Calculamos historial usando la nueva relación 'pagos_recibidos'
            pagos_anteriores = self.factura_obj.pagos_recibidos.aggregate(total=Sum('importe_pagado'))['total'] or 0
            saldo_pendiente = self.factura_obj.monto_total - pagos_anteriores
            
            saldo_pendiente = round(saldo_pendiente, 2)
            
            if monto > saldo_pendiente:
                raise forms.ValidationError(f"El monto excede el saldo pendiente (${saldo_pendiente:,.2f})")
            if monto <= 0:
                raise forms.ValidationError("El monto debe ser mayor a 0.")
        return monto

    def clean(self):
        cleaned_data = super().clean()
        fecha_pago = cleaned_data.get('fecha_pago')

        if self.factura_obj:
            if self.factura_obj.estado == 'cancelada':
                raise forms.ValidationError("No se pueden registrar pagos a una factura CANCELADA.")

            if fecha_pago and fecha_pago.date() < self.factura_obj.fecha_emision.date():
                self.add_error('fecha_pago', f"La fecha de pago no puede ser anterior a la fecha de la factura.")

        return cleaned_data
    
    
class ComplementoPagoCabeceraForm(forms.ModelForm):
    cliente = forms.ModelChoiceField(
        queryset=DatosFiscales.objects.filter(es_emisor=False),
        widget=forms.Select(attrs={'class': 'form-select select2', 'id': 'select-cliente'}),
        label="Cliente"
    )
    
    # --- CORRECCIÓN AQUÍ: Definimos explícitamente el campo con sus opciones ---
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Forma de Pago SAT"
    )

    class Meta:
        model = ComplementoPago
        fields = ['fecha_pago', 'forma_pago', 'monto_total', 'num_operacion']
        widgets = {
            'fecha_pago': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            # Ya no definimos forma_pago aquí porque lo hicimos arriba
            'monto_total': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'input-monto-total'}),
            'num_operacion': forms.TextInput(attrs={'class': 'form-control'}),
        }