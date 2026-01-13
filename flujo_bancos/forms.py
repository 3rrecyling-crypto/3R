from django import forms
from .models import Movimiento, Cuenta, SubCategoria, Operacion, Tercero
from .models import Cuenta, Movimiento, ComprobanteFiscal

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
    # --- CAMPOS EXTRAS (INTERFAZ) ---
    TIPO_CHOICES = [('ingreso', 'Ingreso (Abono)'), ('egreso', 'Egreso (Cargo)')]
    
    # Agregamos required=False aquí
    tipo_movimiento = forms.ChoiceField(
        choices=TIPO_CHOICES, 
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_movimiento'}),
        label="Tipo"
    )
    
    # Agregamos required=False aquí
    monto_total = forms.DecimalField(
        max_digits=12, decimal_places=2, 
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_monto_total'}),
        label="Monto"
    )

    tercero_obj = forms.ModelChoiceField(
        queryset=Tercero.objects.all().order_by('nombre'), 
        required=False, 
        label="Tercero",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # Si en tu HTML usas 'cuenta_destino_transfer', defínela aquí opcionalmente
    cuenta_destino_transfer = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Movimiento
        fields = [
            'fecha', 'concepto', 'unidad_negocio', 'operacion', 
            'categoria', 'subcategoria', 'cuenta', 
            'iva', 'ret_iva', 'ret_isr', 'comentarios', 'comprobante'
            # Agrega aquí cualquier otro campo del modelo que falte
        ]
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'concepto': forms.TextInput(attrs={'class': 'form-control', 'list': 'lista-conceptos'}),
            'unidad_negocio': forms.Select(attrs={'class': 'form-select'}),
            'operacion': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'subcategoria': forms.Select(attrs={'class': 'form-select'}),
            'cuenta': forms.Select(attrs={'class': 'form-select'}),
            'iva': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ret_iva': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ret_isr': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'comprobante': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'comentarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # --- CAMBIO PRINCIPAL: HACER TODO OPCIONAL ---
        # Recorremos todos los campos (fecha, cuenta, subcategoria, etc.)
        # y les decimos a Django que NO son obligatorios.
        for field_name, field in self.fields.items():
            field.required = False

        # --- LÓGICA DE PRECARGA (EDICIÓN) ---
        if self.instance and self.instance.pk:
            # Precargar Monto y Tipo
            if self.instance.cargo > 0:
                self.fields['monto_total'].initial = self.instance.cargo
                self.fields['tipo_movimiento'].initial = 'egreso'
            elif self.instance.abono > 0:
                self.fields['monto_total'].initial = self.instance.abono
                self.fields['tipo_movimiento'].initial = 'ingreso'
            
            # Precargar Tercero
            if self.instance.tercero:
                tercero = Tercero.objects.filter(nombre=self.instance.tercero).first()
                if tercero: 
                    self.fields['tercero_obj'].initial = tercero

            # Filtrar Subcategorías según la Categoría guardada
            if self.instance.categoria:
                 self.fields['subcategoria'].queryset = SubCategoria.objects.filter(categoria=self.instance.categoria)
            else:
                 self.fields['subcategoria'].queryset = SubCategoria.objects.none()

        # --- LÓGICA DINÁMICA (POST) ---
        # Si el usuario envió el formulario (POST), filtramos subcategorías
        # basándonos en lo que seleccionó en 'categoria'
        if 'categoria' in self.data:
            try:
                categoria_id = int(self.data.get('categoria'))
                self.fields['subcategoria'].queryset = SubCategoria.objects.filter(categoria_id=categoria_id)
            except (ValueError, TypeError):
                pass
        elif not self.instance.pk:
            # Si es nuevo y no hay datos, lista vacía
            self.fields['subcategoria'].queryset = SubCategoria.objects.none()

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Guardar nombre del Tercero (solo si se seleccionó uno)
        tercero = self.cleaned_data.get('tercero_obj')
        if tercero: 
            instance.tercero = tercero.nombre
        
        # Mapear Monto (si está vacío usa 0)
        monto = self.cleaned_data.get('monto_total') or 0 
        tipo = self.cleaned_data.get('tipo_movimiento')
        
        if tipo == 'egreso':
            instance.cargo = monto
            instance.abono = 0
        elif tipo == 'ingreso':
            instance.abono = monto
            instance.cargo = 0
        else:
            # Si no seleccionó tipo, dejamos ambos en 0 o respetamos lo que tuviera la instancia
            if not instance.pk: # Solo si es nuevo forzamos 0
                instance.abono = 0
                instance.cargo = 0
            
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
        
class ImportarTxtForm(forms.Form):
    cuenta_destino = forms.ModelChoiceField(
        queryset=Cuenta.objects.all(),
        label="Cuenta Bancaria",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    archivo_txt = forms.FileField(
        label="Archivo .txt",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.txt'})
    )
    
from django import forms
from .models import Categoria, SubCategoria

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Gastos Operativos'})
        }

class SubCategoriaForm(forms.ModelForm):
    class Meta:
        model = SubCategoria
        fields = ['categoria', 'nombre']
        widgets = {
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Renta de Oficina'})
        }
        
class ActualizarSaldoForm(forms.ModelForm):
    class Meta:
        model = Cuenta
        fields = ['saldo_inicial']
        widgets = {
            'saldo_inicial': forms.NumberInput(attrs={'class': 'form-control'})
        }
        
class ImportarExcelForm(forms.Form):
    cuenta_destino = forms.ModelChoiceField(
        queryset=Cuenta.objects.all(),
        label="Cuenta Bancaria",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    archivo_excel = forms.FileField(
        label="Archivo Excel (.xlsx)",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx, .xls'})
    )

class ComprobanteForm(forms.ModelForm):
    class Meta:
        model = ComprobanteFiscal
        fields = ['archivo_xml', 'archivo_pdf']
        widgets = {
            'archivo_xml': forms.FileInput(attrs={'class': 'form-control', 'accept': '.xml'}),
            'archivo_pdf': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        }