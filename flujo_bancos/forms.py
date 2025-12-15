from django import forms
from .models import Movimiento, Cuenta, SubCategoria, Operacion, Tercero

# 1. FORMULARIO PARA ALTA RÁPIDA DE TERCEROS
class TerceroForm(forms.ModelForm):
    class Meta:
        model = Tercero
        fields = ['nombre', 'tipo', 'celular']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Walmart'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'celular': forms.TextInput(attrs={'class': 'form-select', 'placeholder': 'Opcional'}),
        }

# 2. FORMULARIO PRINCIPAL UNIFICADO
# 1. FORMULARIO PARA ALTA RÁPIDA DE TERCEROS
class TerceroForm(forms.ModelForm):
    class Meta:
        model = Tercero
        fields = ['nombre', 'tipo', 'celular']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Walmart'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'celular': forms.TextInput(attrs={'class': 'form-select', 'placeholder': 'Opcional'}),
        }

# 2. FORMULARIO PRINCIPAL UNIFICADO
class MovimientoForm(forms.ModelForm):
    # --- Campos EXTRAS para la interfaz (No existen en BD directo) ---
    TIPO_CHOICES = [
        ('ingreso', 'Ingreso (Abono)'),
        ('egreso', 'Egreso (Cargo)'),
    ]
    
    tipo_movimiento = forms.ChoiceField(
        choices=TIPO_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_movimiento'}),
        label="Tipo de Movimiento"
    )
    
    monto_total = forms.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_monto_total'}),
        label="Monto Base (Subtotal)"
    )

    # Campo auxiliar para el Tercero (Combo Box)
    tercero_obj = forms.ModelChoiceField(
        queryset=Tercero.objects.all().order_by('nombre'), 
        required=False,
        label="A QUIEN SE LE PAGÓ",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Movimiento
        fields = [
            'fecha', 'concepto', 
            'unidad_negocio', 'operacion', 
            'categoria', 'subcategoria', 'cuenta', 
            'iva', 'ret_iva', 'ret_isr', 'comentarios',
            'comprobante' 
        ]
        
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'concepto': forms.TextInput(attrs={'class': 'form-control', 'list': 'lista-conceptos'}),
            'unidad_negocio': forms.Select(attrs={'class': 'form-select'}),
            'operacion': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'subcategoria': forms.Select(attrs={'class': 'form-select'}),
            'cuenta': forms.Select(attrs={'class': 'form-select'}),
            'iva': forms.NumberInput(attrs={'class': 'form-control imp-field', 'step': '0.01'}),
            'ret_iva': forms.NumberInput(attrs={'class': 'form-control imp-field', 'step': '0.01'}),
            'ret_isr': forms.NumberInput(attrs={'class': 'form-control imp-field', 'step': '0.01'}),
            'comprobante': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'comentarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    # *** INICIALIZACIÓN ***
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # --- MODIFICACIÓN: HACER IVA OPCIONAL ---
        self.fields['iva'].required = False 
        # ----------------------------------------
        
        # Si estamos editando un registro existente (instance.pk existe)
        if self.instance and self.instance.pk:
            
            # 1. Precargar Monto y Tipo (Ingreso vs Egreso)
            initial_monto = 0
            initial_tipo = 'egreso' 
            
            if self.instance.cargo > 0:
                initial_monto = self.instance.cargo
                initial_tipo = 'egreso'
            elif self.instance.abono > 0:
                initial_monto = self.instance.abono
                initial_tipo = 'ingreso'
            
            self.fields['monto_total'].initial = initial_monto
            self.fields['tipo_movimiento'].initial = initial_tipo
            
            # 2. Precargar el Tercero en el Combo Box
            if self.instance.tercero:
                try:
                    tercero_encontrado = Tercero.objects.filter(nombre=self.instance.tercero).first()
                    if tercero_encontrado:
                        self.fields['tercero_obj'].initial = tercero_encontrado
                except:
                    pass 
            
            # 3. Filtrar Subcategorías 
            if self.instance.categoria:
                 self.fields['subcategoria'].queryset = SubCategoria.objects.filter(categoria=self.instance.categoria).order_by('nombre')
            else:
                 self.fields['subcategoria'].queryset = SubCategoria.objects.none()

            # Si hay datos POST (cuando hay error de validación)
            if 'categoria' in self.data:
                try:
                    categoria_id = int(self.data.get('categoria'))
                    self.fields['subcategoria'].queryset = SubCategoria.objects.filter(categoria_id=categoria_id).order_by('nombre')
                except (ValueError, TypeError):
                    pass

    # *** LÓGICA DE GUARDADO (SOLO UNA VEZ) ***
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # 1. Convertir Combobox Tercero -> Texto para BD
        tercero_seleccionado = self.cleaned_data.get('tercero_obj')
        if tercero_seleccionado:
            instance.tercero = tercero_seleccionado.nombre 
        
        # 2. Convertir Monto Base -> Cargo/Abono
        tipo = self.cleaned_data.get('tipo_movimiento')
        monto_base = self.cleaned_data.get('monto_total', 0)
        
        if tipo == 'egreso':
            instance.cargo = monto_base
            instance.abono = 0
            cambio_saldo = -monto_base
        else: 
            instance.abono = monto_base
            instance.cargo = 0
            cambio_saldo = monto_base 

        # 3. Recálculo simple de saldo (Solo referencia)
        if instance.cuenta:
             instance.saldo_banco = instance.cuenta.saldo_actual + cambio_saldo
            
        if commit:
            instance.save()

        return instance

class TransferenciaForm(forms.Form):
    cuenta_origen = forms.ModelChoiceField(queryset=Cuenta.objects.all(), label="Cuenta de Origen", widget=forms.Select(attrs={'class': 'form-control'}))
    cuenta_destino = forms.ModelChoiceField(queryset=Cuenta.objects.all(), label="Cuenta de Destino", widget=forms.Select(attrs={'class': 'form-control'}))
    monto = forms.DecimalField(max_digits=15, decimal_places=2, label="Monto a Transferir (Moneda Origen)", widget=forms.NumberInput(attrs={'class': 'form-control'}))
    tipo_cambio = forms.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        required=False, 
        initial=1.0, 
        label="Tipo de Cambio", 
        help_text="Requerido si las cuentas tienen monedas diferentes.",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    concepto = forms.CharField(max_length=200, initial="Transferencia entre cuentas", label="Concepto", widget=forms.TextInput(attrs={'class': 'form-control'}))

    def clean(self):
        cleaned_data = super().clean()
        origen = cleaned_data.get('cuenta_origen')
        destino = cleaned_data.get('cuenta_destino')
        tc = cleaned_data.get('tipo_cambio')

        if origen and destino:
            if origen == destino:
                self.add_error('cuenta_destino', "La cuenta destino no puede ser la misma que la de origen.")
            if origen.moneda != destino.moneda:
                if not tc or tc == 1.0:
                    self.add_error('tipo_cambio', f"Estás transfiriendo de {origen.moneda} a {destino.moneda}. Por favor ingresa un Tipo de Cambio válido.")
        return cleaned_data

class CuentaForm(forms.ModelForm):
    class Meta:
        model = Cuenta
        fields = ['nombre', 'saldo_inicial', 'moneda']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'saldo_inicial': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'moneda': forms.Select(attrs={'class': 'form-select'}),
        }