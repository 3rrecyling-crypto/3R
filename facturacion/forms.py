from django import forms
from django.db.models import Sum
from ternium.models import Lugar
from .models import Factura, DatosFiscales, ComplementoPago, SatUsoCFDI, SatRegimenFiscal
from .models import SeriePersonalizada # <--- Importar el nuevo modelo
# ==========================================
# 1. CATÁLOGOS COMPLETOS
# ==========================================

USO_CFDI_CHOICES = [
    ('G01', 'G01 - Adquisición de mercancías'),
    ('G02', 'G02 - Devoluciones, descuentos o bonificaciones'),
    ('G03', 'G03 - Gastos en general'),
    ('I01', 'I01 - Construcciones'),
    ('I02', 'I02 - Mobiliario y equipo de oficina por inversiones'),
    ('I03', 'I03 - Equipo de transporte'),
    ('I04', 'I04 - Equipo de computo y accesorios'),
    ('I05', 'I05 - Dados, troqueles, moldes, matrices y herramental'),
    ('I06', 'I06 - Comunicaciones telefónicas'),
    ('I07', 'I07 - Comunicaciones satelitales'),
    ('I08', 'I08 - Otra maquinaria y equipo'),
    ('D01', 'D01 - Honorarios médicos, dentales y gastos hospitalarios'),
    ('D02', 'D02 - Gastos médicos por incapacidad o discapacidad'),
    ('D03', 'D03 - Gastos funerales'),
    ('D04', 'D04 - Donativos'),
    ('D05', 'D05 - Intereses reales efectivamente pagados por créditos hipotecarios'),
    ('D06', 'D06 - Aportaciones voluntarias al SAR'),
    ('D07', 'D07 - Primas por seguros de gastos médicos'),
    ('D08', 'D08 - Gastos de transportación escolar obligatoria'),
    ('D09', 'D09 - Depósitos en cuentas para el ahorro'),
    ('D10', 'D10 - Pagos por servicios educativos (colegiaturas)'),
    ('S01', 'S01 - Sin efectos fiscales'),
    ('CP01', 'CP01 - Pagos'),
    ('CN01', 'CN01 - Nómina'),
]

REGIMEN_FISCAL_CHOICES = [
    ('601', '601 - General de Ley Personas Morales'),
    ('603', '603 - Personas Morales con Fines no Lucrativos'),
    ('605', '605 - Sueldos y Salarios e Ingresos Asimilados a Salarios'),
    ('606', '606 - Arrendamiento'),
    ('607', '607 - Régimen de Enajenación o Adquisición de Bienes'),
    ('608', '608 - Demás ingresos'),
    ('610', '610 - Residentes en el Extranjero sin Establecimiento Permanente'),
    ('611', '611 - Ingresos por Dividendos'),
    ('612', '612 - Personas Físicas con Actividades Empresariales y Profesionales'),
    ('614', '614 - Ingresos por intereses'),
    ('616', '616 - Sin obligaciones fiscales'),
    ('620', '620 - Sociedades Cooperativas de Producción'),
    ('621', '621 - Incorporación Fiscal'),
    ('622', '622 - Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras'),
    ('623', '623 - Opcional para Grupos de Sociedades'),
    ('624', '624 - Coordinados'),
    ('625', '625 - Actividades Empresariales con ingresos a través de Plataformas'),
    ('626', '626 - Régimen Simplificado de Confianza (RESICO)'),
]

FORMA_PAGO_CHOICES = [
    ('01', '01 - Efectivo'),
    ('02', '02 - Cheque nominativo'),
    ('03', '03 - Transferencia electrónica de fondos'),
    ('04', '04 - Tarjeta de crédito'),
    ('05', '05 - Monedero electrónico'),
    ('06', '06 - Dinero electrónico'),
    ('08', '08 - Vales de despensa'),
    ('12', '12 - Dación en pago'),
    ('13', '13 - Pago por subrogación'),
    ('14', '14 - Pago por consignación'),
    ('15', '15 - Condonación'),
    ('17', '17 - Compensación'),
    ('23', '23 - Novación'),
    ('24', '24 - Confusión'),
    ('25', '25 - Remisión de deuda'),
    ('26', '26 - Prescripción o caducidad'),
    ('27', '27 - A satisfacción del acreedor'),
    ('28', '28 - Tarjeta de débito'),
    ('29', '29 - Tarjeta de servicios'),
    ('30', '30 - Aplicación de anticipos'),
    ('31', '31 - Intermediario pagos'),
    ('99', '99 - Por definir'),
]

METODO_PAGO_CHOICES = [
    ('PUE', 'PUE - Pago en una sola exhibición'),
    ('PPD', 'PPD - Pago en parcialidades o diferido'),
]

MONEDA_CHOICES = [
    ('MXN', 'MXN - Peso Mexicano'),
    ('USD', 'USD - Dólar Americano'),
]

# ==========================================
# 2. FORMULARIOS ACTUALIZADOS
# ==========================================

class NuevaFacturaLibreForm(forms.ModelForm):
    serie_personalizada = forms.ModelChoiceField(
        queryset=SeriePersonalizada.objects.filter(activa=True),
        required=False,
        label="Serie / Folio Personalizado",
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        empty_label="-- Folio Automático (F) --" 
    )

    # --- CAMBIO AQUÍ: Usamos un campo auxiliar para seleccionar el Lugar ---
    lugar_receptor = forms.ModelChoiceField(
        # Filtramos solo Lugares que tengan RFC (no vacíos ni nulos)
        queryset=Lugar.objects.exclude(rfc__isnull=True).exclude(rfc__exact='').order_by('nombre'),
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Cliente / Receptor (Desde Lugares)",
        empty_label="Seleccione un Cliente"
    )
    # -----------------------------------------------------------------------
    
    uso_cfdi = forms.ChoiceField(
        choices=USO_CFDI_CHOICES,
        initial='G03',
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Uso de CFDI"
    )

    metodo_pago = forms.ChoiceField(
        choices=METODO_PAGO_CHOICES, 
        initial='PPD',
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Método de Pago"
    )

    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES, 
        initial='99',
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Forma de Pago"
    )
    
    moneda = forms.ChoiceField(
        choices=MONEDA_CHOICES,
        initial='MXN',
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Moneda"
    )

    tipo_cambio = forms.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        initial=1.0000,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Tipo de Cambio"
    )
    
    aplicar_retencion = forms.BooleanField(
        required=False, 
        label="Retención 6%",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    tipo_relacion = forms.ChoiceField(
        choices=[('', '--- Sin Relación ---'), ('04', '04 - Sustitución de CFDI previos')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select border-warning'}),
        label="Tipo Relación"
    )
    
    uuid_relacionado = forms.CharField(
        required=False,
        label="UUID Relacionado",
        widget=forms.TextInput(attrs={'class': 'form-control border-warning'})
    )

    class Meta:
        model = Factura
        # QUITAMOS 'receptor' de aquí porque lo manejaremos manualmente en la vista
        fields = ['moneda', 'tipo_cambio', 'uso_cfdi', 'metodo_pago', 'forma_pago', 'tipo_relacion', 'uuid_relacionado']

    # Personalizamos cómo se ve el lugar en la lista
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lugar_receptor'].label_from_instance = lambda obj: f"{obj.nombre} - {obj.rfc}"


class GenerarFacturaForm(forms.ModelForm):
    # --- ESTE ES EL FORMULARIO DE PREFACTURA ---
    # FALTABA ESTE CAMPO PARA QUE APARECIERA EN EL HTML
    serie_personalizada = forms.ModelChoiceField(
        queryset=SeriePersonalizada.objects.filter(activa=True),
        required=False,
        label="Serie / Folio Personalizado",
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        empty_label="-- Folio Automático (F) --"
    )

    uso_cfdi = forms.ChoiceField(
        choices=USO_CFDI_CHOICES,  # Asegúrate de importar USO_CFDI_CHOICES
        initial='G03',
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    metodo_pago = forms.ChoiceField(
        choices=METODO_PAGO_CHOICES, # Asegúrate de importar METODO_PAGO_CHOICES
        initial='PPD',
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES, # Asegúrate de importar FORMA_PAGO_CHOICES
        initial='99',
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    moneda = forms.ChoiceField(
        choices=MONEDA_CHOICES, # Asegúrate de importar MONEDA_CHOICES
        initial='MXN',
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    
    tipo_cambio = forms.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        initial=1.0000,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    aplicar_retencion = forms.BooleanField(
        required=False, 
        label="Aplicar Retención de IVA (6%)", 
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'onchange': 'calcularTotales()'})
    )

    class Meta:
        model = Factura
        fields = ['moneda', 'tipo_cambio']


class DatosFiscalesForm(forms.ModelForm):
    regimen_fiscal = forms.ChoiceField(
        choices=REGIMEN_FISCAL_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )

    class Meta:
        model = DatosFiscales
        fields = '__all__'
        widgets = {
            'rfc': forms.TextInput(attrs={'class': 'form-control', 'style': 'text-transform:uppercase;'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_postal': forms.TextInput(attrs={'class': 'form-control'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control'}),
            'empresa_interna': forms.HiddenInput(),
            'cliente_interno': forms.HiddenInput()
        }


class DatosFiscalesClienteForm(forms.ModelForm):
    regimen_fiscal = forms.ChoiceField(
        choices=REGIMEN_FISCAL_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    uso_cfdi = forms.ChoiceField(
        choices=USO_CFDI_CHOICES, 
        required=False,
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    
    # --- NUEVOS CAMPOS DE DIRECCIÓN PARA EL MODAL ---
    calle = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Calle'}))
    numero_exterior = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'No. Ext'}))
    numero_interior = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'No. Int'}))
    colonia = forms.CharField(required=False, widget=forms.Select(attrs={'class': 'form-select'})) # Se llenará con JS
    municipio = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}))
    estado = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}))

    class Meta:
        model = DatosFiscales
        fields = ['razon_social', 'rfc', 'regimen_fiscal', 'codigo_postal', 'uso_cfdi']
        widgets = {
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control text-uppercase'}),
            'codigo_postal': forms.TextInput(attrs={'class': 'form-control', 'id': 'input_cp_fiscal'}), # ID para JS
        }

class ConfigurarEmisorForm(forms.Form):
    lugar_origen = forms.ModelChoiceField(
        # Filtramos solo lugares que tengan RFC llenado para evitar errores
        queryset=Lugar.objects.exclude(rfc__isnull=True).exclude(rfc__exact=''),
        label="Selecciona tu Sucursal/Lugar",
        empty_label="-- Selecciona un Lugar con Datos Fiscales --",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Personalizamos la etiqueta para ver el RFC en la lista
        self.fields['lugar_origen'].label_from_instance = lambda obj: f"{obj.nombre} - RFC: {obj.rfc}"

class PagoForm(forms.ModelForm):
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select select2'}),
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

    def __init__(self, *args, **kwargs):
        self.factura_obj = kwargs.pop('factura_obj', None)
        super().__init__(*args, **kwargs)

    def clean_monto_total(self):
        monto = self.cleaned_data.get('monto_total')
        if self.factura_obj and monto:
            pagos_anteriores = self.factura_obj.pagos_recibidos.aggregate(total=Sum('importe_pagado'))['total'] or 0
            saldo_pendiente = self.factura_obj.monto_total - pagos_anteriores
            saldo_pendiente = round(saldo_pendiente, 2)
            
            if monto > saldo_pendiente:
                raise forms.ValidationError(f"El monto excede el saldo pendiente (${saldo_pendiente:,.2f})")
            if monto <= 0:
                raise forms.ValidationError("El monto debe ser mayor a 0.")
        return monto


class ComplementoPagoCabeceraForm(forms.ModelForm):
    cliente = forms.ModelChoiceField(
        queryset=DatosFiscales.objects.filter(es_emisor=False),
        widget=forms.Select(attrs={'class': 'form-select select2', 'id': 'select-cliente'}),
        label="Cliente"
    )
    
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Forma de Pago SAT"
    )

    class Meta:
        model = ComplementoPago
        fields = ['fecha_pago', 'forma_pago', 'monto_total', 'num_operacion']
        widgets = {
            'fecha_pago': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'monto_total': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'input-monto-total'}),
            'num_operacion': forms.TextInput(attrs={'class': 'form-control'}),
        }


class NotaCreditoLibreForm(forms.ModelForm):
    receptor = forms.ModelChoiceField(
        queryset=DatosFiscales.objects.filter(es_emisor=False),
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Cliente / Receptor",
        empty_label="Seleccione un Cliente"
    )
    
    uso_cfdi = forms.ChoiceField(
        choices=USO_CFDI_CHOICES,
        initial='G02',  # G02 - Devoluciones, descuentos o bonificaciones
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Uso de CFDI"
    )

    # --- NUEVO CAMPO AGREGADO ---
    metodo_pago = forms.ChoiceField(
        choices=METODO_PAGO_CHOICES, 
        initial='PUE', # PUE es el valor correcto para Notas de Crédito
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Método de Pago",
        help_text="Para Notas de Crédito debe ser PUE."
    )
    # ----------------------------

    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        label="Forma de Pago"
    )
    
    tipo_relacion = forms.ChoiceField(
        choices=[('01', '01 - Nota de crédito de los documentos relacionados'), ('03', '03 - Devolución de mercancía')],
        initial='01',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Tipo Relación"
    )
    
    uuid_relacionado = forms.CharField(
        label="UUID de la Factura a afectar",
        widget=forms.TextInput(attrs={'class': 'form-control border-warning', 'placeholder': 'Ej. 550e8400-e29b-41d4-a716-446655440000'}),
        help_text="Copia y pega el Folio Fiscal de la factura original."
    )

    concepto_descripcion = forms.CharField(
        label="Descripción",
        initial="Bonificación",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    monto_sin_iva = forms.DecimalField(
        label="Monto de la Nota (Sin IVA)",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )

    class Meta:
        model = Factura
        # Se agregó 'metodo_pago' a la lista de campos
        fields = ['receptor', 'uso_cfdi', 'metodo_pago', 'forma_pago', 'tipo_relacion', 'uuid_relacionado']
        
from .models import ProductoServicio

class ProductoServicioForm(forms.ModelForm):
    class Meta:
        model = ProductoServicio
        fields = [
            'codigo_interno', 'tipo', 'nombre', 
            'clave_prod_serv', 'clave_unidad', 'descripcion_sat', 
            'precio_unitario', 'objeto_impuesto', 
            # CAMBIO: Usamos los nuevos campos vinculados
            'impuesto_traslado', 
            'impuesto_retencion'
        ]
        widgets = {
            'codigo_interno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SKU-001'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre corto'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'clave_prod_serv': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 84111506'}),
            'clave_unidad': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. E48'}),
            'descripcion_sat': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'objeto_impuesto': forms.Select(attrs={'class': 'form-select'}),
            
            # WIDGETS PARA LOS NUEVOS COMBOS
            'impuesto_traslado': forms.Select(attrs={'class': 'form-select'}),
            'impuesto_retencion': forms.Select(attrs={'class': 'form-select'}),
        }
    
    # Opcional: Para mostrar una etiqueta vacía por defecto
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['impuesto_traslado'].empty_label = "Sin Impuesto Trasladado (Exento/0%)"
        self.fields['impuesto_retencion'].empty_label = "Sin Retención"
        
        
from .models import CatalogoImpuesto

class CatalogoImpuestoForm(forms.ModelForm):
    class Meta:
        model = CatalogoImpuesto
        fields = ['nombre', 'categoria', 'impuesto', 'tipo_factor', 'tasa_o_cuota', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. IVA 16%'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'impuesto': forms.Select(attrs={'class': 'form-select'}),
            'tipo_factor': forms.Select(attrs={'class': 'form-select'}),
            'tasa_o_cuota': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
