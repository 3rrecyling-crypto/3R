from django import forms
from .models import Factura, DatosFiscales, ComplementoPago
from ternium.models import Lugar

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
    class Meta:
        model = ComplementoPago
        fields = ['fecha_pago', 'monto', 'forma_pago', 'num_operacion']
        widgets = {
            'fecha_pago': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'forma_pago': forms.Select(attrs={'class': 'form-select'}),
            'num_operacion': forms.TextInput(attrs={'class': 'form-control'}),
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