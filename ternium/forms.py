# ternium/forms.py

import os
from django import forms
from django.utils import timezone
from django.contrib.auth.forms import AuthenticationForm
from .models import (
    Empresa, Lugar, Remision, EntradaMaquila, LineaTransporte,
    Operador, Material, Unidad, Contenedor, DetalleRemision, Descarga,
    RegistroLogistico
)


class OperadorForm(forms.ModelForm):
    class Meta:
        model = Operador
        fields = ['nombre']
        widgets = {'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Juan Pérez'})}
        labels = {'nombre': 'Nombre Completo del Operador'}


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        # AGREGAMOS 'clave_unidad_sat' AQUI ABAJO:
        fields = ['nombre', 'clave_sat', 'clave_unidad_sat', 'empresas'] 
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Chatarra de Acero #1'}),
            'clave_sat': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 01010101'}),
            # WIDGET NUEVO PARA LA UNIDAD
            'clave_unidad_sat': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. KGM'}), 
            'empresas': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nombre': 'Nombre del Material', 
            'clave_sat': 'Clave SAT (Prod/Serv)',
            'clave_unidad_sat': 'Clave Unidad (H87/KGM)', # Etiqueta opcional
            'empresas': 'Unidades de Negocio (Empresas)'
        }

class UnidadForm(forms.ModelForm):
    class Meta:
        model = Unidad
        # Incluimos solo los campos que queremos que el usuario edite
        fields = [
            'internal_id', 'license_plate', 'make_model', 'year', 'vin', 'asset_type',
            'color', 'ownership', 'acquisition_date', 'operational_status',
            'insurance_policy', 'insurance_due_date', 'circulation_license',
            'license_due_date', 'display_photo', 'unit_documents', 'empresas', 'notes'
        ]
        widgets = {
            # Widgets para campos de fecha para que muestren un calendario
            'acquisition_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'insurance_due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'license_due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            
            # Widgets para archivos
            'display_photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'unit_documents': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.doc,.docx,.xls,.xlsx,image/*'}),

            # Widget para selección múltiple de empresas
            'empresas': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
            
            # Widget para notas
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Bucle para añadir la clase 'form-control' o 'form-select' a todos los campos
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            elif not isinstance(field.widget, (forms.CheckboxSelectMultiple, forms.DateInput, forms.FileInput, forms.Textarea)):
                field.widget.attrs.update({'class': 'form-control'})
                
class ContenedorForm(forms.ModelForm):
    class Meta:
        model = Contenedor
        fields = ['nombre', 'placas', 'empresas']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: CS-04, CAJA-53FT'}),
            'placas': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. CONT-456-789'}),
            'empresas': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }
        labels = {'nombre': 'Nombre o ID del Contenedor', 'placas': 'Placas del Contenedor', 'empresas': 'Unidades de Negocio (Empresas)'}


class LineaTransporteForm(forms.ModelForm):
    class Meta:
        model = LineaTransporte
        fields = ['nombre', 'empresas']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Transportes Rápidos del Norte'}),
            'empresas': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }
        labels = {'nombre': 'Nombre de la Línea de Transporte', 'empresas': 'Unidades de Negocio (Empresas)'}


class LugarForm(forms.ModelForm):
    """
    Formulario para Lugares (Clientes/Proveedores).
    Aquí es donde SÍ van los datos fiscales.
    """
    class Meta:
        model = Lugar
        # Agregamos los campos fiscales que tienes en tu modelo Lugar
        fields = [
            'nombre', 'tipo', 'es_patio', 'empresas',
            'razon_social', 'rfc', 'regimen_fiscal', 'uso_cfdi',
            'calle', 'numero_exterior', 'numero_interior', 
            'colonia', 'codigo_postal', 'municipio', 'estado', 'pais'
        ]
        widgets = {
            # Datos Operativos
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre corto (Alias)'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'es_patio': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'empresas': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
            
            # Datos Fiscales
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control'}),
            'regimen_fiscal': forms.Select(attrs={'class': 'form-select'}),
            'uso_cfdi': forms.Select(attrs={'class': 'form-select'}),
            
            # Dirección
            'calle': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_exterior': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_interior': forms.TextInput(attrs={'class': 'form-control'}),
            'colonia': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_postal': forms.TextInput(attrs={'class': 'form-control'}),
            'municipio': forms.TextInput(attrs={'class': 'form-control'}),
            'estado': forms.TextInput(attrs={'class': 'form-control'}),
            'pais': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nombre': 'Nombre Operativo', 
            'es_patio': '¿Es Patio de Inventario?',
            'empresas': 'Unidades de Negocio Asociadas'
        }


class RemisionForm(forms.ModelForm):
    class Meta:
        model = Remision
        exclude = ['status', 'auditado_por', 'auditado_en']
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'remision': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'linea_transporte': forms.Select(attrs={'class': 'form-select'}),
            'operador': forms.Select(attrs={'class': 'form-select'}),
            'unidad': forms.Select(attrs={'class': 'form-select'}),
            'contenedor': forms.Select(attrs={'class': 'form-select'}),
            'origen': forms.Select(attrs={'class': 'form-select'}),
            'destino': forms.Select(attrs={'class': 'form-select'}),
            'inicia_ld': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'termina_ld': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'folio_ld': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'inicia_dlv': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'termina_dlv': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'folio_dlv': forms.TextInput(attrs={'class': 'form-control'}),
            'evidencia_carga': forms.FileInput(attrs={'class': 'form-control'}),
            'evidencia_descarga': forms.FileInput(attrs={'class': 'form-control'}),
            'comentario': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        # Extraemos 'empresa' de los argumentos, si se proporciona desde la vista
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        # Si se pasó una empresa, filtramos los QuerySets de los campos relacionados
        if empresa:
            self.fields['linea_transporte'].queryset = LineaTransporte.objects.filter(empresas=empresa)
            self.fields['unidad'].queryset = Unidad.objects.filter(empresas=empresa)
            self.fields['contenedor'].queryset = Contenedor.objects.filter(empresas=empresa)
            self.fields['origen'].queryset = Lugar.objects.filter(empresas=empresa, tipo__in=['ORIGEN', 'AMBOS'])
            self.fields['destino'].queryset = Lugar.objects.filter(empresas=empresa, tipo__in=['DESTINO', 'AMBOS'])
        # Si no hay empresa (al crear una remisión nueva), los campos aparecen vacíos
        else:
            self.fields['linea_transporte'].queryset = LineaTransporte.objects.none()
            self.fields['unidad'].queryset = Unidad.objects.none()
            self.fields['contenedor'].queryset = Contenedor.objects.none()
            self.fields['origen'].queryset = Lugar.objects.none()
            self.fields['destino'].queryset = Lugar.objects.none()

        # Nota: El campo 'operador' no está relacionado a 'Empresa' en el modelo,
        # por lo que muestra todos los operadores disponibles.
        self.fields['operador'].queryset = Operador.objects.all()

        if self.instance and self.instance.pk and self.instance.status == 'AUDITADO':
            for field in self.fields:
                self.fields[field].disabled = True
    
    def clean(self):
        cleaned_data = super().clean()
        origen = cleaned_data.get('origen')
        destino = cleaned_data.get('destino')
        
        patios_exentos = ["PATIO MONTERREY", "PATIO NUEVO LAREDO"]

        is_completing = all([
            cleaned_data.get('remision'), cleaned_data.get('fecha'), cleaned_data.get('linea_transporte'),
            cleaned_data.get('operador'), cleaned_data.get('unidad'), origen, destino,
            cleaned_data.get('folio_ld'), cleaned_data.get('folio_dlv')
        ])

        if is_completing:
            if origen and origen.nombre.upper() not in patios_exentos:
                if not cleaned_data.get('evidencia_carga') and not (self.instance and self.instance.evidencia_carga):
                    self.add_error('evidencia_carga', 'Se requiere la evidencia de carga para este origen.')

            if destino and destino.nombre.upper() not in patios_exentos:
                if not cleaned_data.get('evidencia_descarga') and not (self.instance and self.instance.evidencia_descarga):
                    self.add_error('evidencia_descarga', 'Se requiere la evidencia de descarga para este destino.')

        return cleaned_data


class DetalleRemisionForm(forms.ModelForm):
    class Meta:
        model = DetalleRemision
        fields = ['material', 'cliente', 'peso_ld', 'peso_dlv']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select material-select'}),
            'cliente': forms.Select(attrs={'class': 'form-select cliente-select'}),
            'peso_ld': forms.NumberInput(attrs={'class': 'form-control peso-carga text-end', 'step': '0.001', 'placeholder': '0.000'}),
            'peso_dlv': forms.NumberInput(attrs={'class': 'form-control peso-descarga text-end', 'step': '0.001', 'placeholder': '0.000'}),
        }
        labels = {
            'material': '', 'cliente': '', 'peso_ld': '', 'peso_dlv': ''
        }

    def __init__(self, *args, **kwargs):
        material_queryset = kwargs.pop('material_queryset', None)
        lugar_queryset = kwargs.pop('lugar_queryset', None)
        super().__init__(*args, **kwargs)
        
        if material_queryset is not None:
            self.fields['material'].queryset = material_queryset
        else:
            self.fields['material'].queryset = Material.objects.none()
            
        if lugar_queryset is not None:
            self.fields['cliente'].queryset = lugar_queryset
        else:
            self.fields['cliente'].queryset = Lugar.objects.none()


class DescargaForm(forms.ModelForm):
    class Meta:
        model = Descarga
        fields = ['origen', 'destino', 'material', 'cantidad', 'fecha_descarga']
        widgets = {
            'origen': forms.Select(attrs={'class': 'form-select'}),
            'destino': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 1500.50'}),
            'fecha_descarga': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['origen'].queryset = Lugar.objects.order_by('nombre')
        self.fields['destino'].queryset = Lugar.objects.order_by('nombre')
        self.fields['material'].queryset = Material.objects.order_by('nombre')
        for field_name in self.fields:
            if isinstance(self.fields[field_name].widget, forms.Select):
                self.fields[field_name].widget.attrs.update({'data-control': 'select2'})


# --- FORMULARIO MODIFICADO ---
class EntradaMaquilaForm(forms.ModelForm):
    class Meta:
        model = EntradaMaquila
        fields = [
            'c_id_remito', 'num_boleta_remision', 'fecha_ingreso', 'transporte',
            'peso_remision', 'peso_bruto', 'peso_tara', 'calidad',
            'fecha_entrega_ternium',
            'foto_frontal', 'foto_superior_cargada', 'foto_trasera',
            'foto_superior_vacia', 'documento_remision_clientes'
        ]
        widgets = {
            'c_id_remito': forms.TextInput(attrs={'class': 'form-control'}),
            'num_boleta_remision': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'transporte': forms.Select(attrs={'class': 'form-select'}),
            'peso_remision': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'peso_bruto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'peso_tara': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'calidad': forms.Select(attrs={'class': 'form-select'}),
            'fecha_entrega_ternium': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            
            'foto_frontal': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'foto_superior_cargada': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'foto_trasera': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'foto_superior_vacia': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'documento_remision_clientes': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,application/pdf'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # --- LÓGICA ACTUALIZADA Y MEJORADA ---
        
        # Definir listas de opciones vacías por defecto
        transporte_choices = [('', 'No se encontró la empresa Ternium')]
        material_choices = [('', 'No se encontró la empresa Ternium')]

        try:
            # 1. Buscar la empresa "Ternium" (ignora mayúsculas/minúsculas)
            ternium_empresa = Empresa.objects.get(nombre__iexact="TERNIUM")
            
            # 2. Si se encuentra, filtrar los catálogos por esa empresa
            transporte_choices = [('', 'Seleccione una línea de transporte...')] + [
                (lt.nombre, lt.nombre) for lt in LineaTransporte.objects.filter(empresas=ternium_empresa).order_by('nombre')
            ]
            material_choices = [('', 'Seleccione una calidad de material...')] + [
                (m.nombre, m.nombre) for m in Material.objects.filter(empresas=ternium_empresa).order_by('nombre')
            ]
        except Empresa.DoesNotExist:
            # Si no se encuentra la empresa "Ternium", las listas desplegables mostrarán el mensaje de error.
            pass

        # 3. Asignar las opciones (filtradas o de error) a los campos
        self.fields['transporte'].widget.choices = transporte_choices
        self.fields['calidad'].widget.choices = material_choices
        
        # --- FIN DE LA LÓGICA ACTUALIZADA ---

        # Lógica existente para deshabilitar campos si está auditado
        if self.instance and self.instance.pk and self.instance.status == 'AUDITADO':
            for field in self.fields:
                self.fields[field].disabled = True

    def clean(self):
        # ... (el resto del formulario no necesita cambios)
        cleaned_data = super().clean()
        remito_id = cleaned_data.get('c_id_remito')
        if not remito_id:
            return cleaned_data

        file_map = {
            'foto_frontal': f"{remito_id}-1",
            'foto_superior_cargada': f"{remito_id}-2",
            'foto_trasera': f"{remito_id}-3",
            'foto_superior_vacia': f"{remito_id}-4",
            'documento_remision_clientes': f"{remito_id}-5",
        }

        for field_name, base_name in file_map.items():
            uploaded_file = self.files.get(field_name)
            if uploaded_file:
                extension = os.path.splitext(uploaded_file.name)[1]
                uploaded_file.name = f"{base_name}{extension}"
        
        return cleaned_data

class EmpresaForm(forms.ModelForm):
    """
    Formulario para Unidades de Negocio (Solo nombre y prefijo).
    """
    class Meta:
        model = Empresa
        # Solo pedimos los campos que realmente existen en el modelo Empresa
        fields = ['nombre', 'prefijo', 'origenes'] 
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. R3 Recycling Solutions'}),
            'prefijo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. MTY'}),
            'origenes': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nombre': 'Nombre de la Unidad de Negocio',
            'prefijo': 'Prefijo para Folios',
            'origenes': 'Orígenes Permitidos'
        }


class CustomLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control form-control-lg', 'placeholder': 'Tu nombre de usuario'})
        self.fields['password'].widget.attrs.update({'class': 'form-control form-control-lg', 'placeholder': 'Tu contraseña'})


# --- FORMULARIO MODIFICADO ---
class RegistroLogisticoForm(forms.ModelForm):
    class Meta:
        model = RegistroLogistico
        fields = [
            'remision', 'fecha_carga', 'boleta_bascula', 'fecha_envio',
            'transportista', 'chofer', 'tractor', 'tolva', 'material',
            'toneladas_remisionadas', 'toneladas_recibidas',
            'pdf_registro_camion_remision', 'pdf_remision_permiso',
            'foto_superior_vacia', 'foto_frontal',
            'foto_superior_llena', 'foto_trasera'
        ]
        widgets = {
            'fecha_carga': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_envio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'toneladas_remisionadas': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'toneladas_recibidas': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'remision': forms.TextInput(attrs={'class': 'form-control'}),
            'boleta_bascula': forms.TextInput(attrs={'class': 'form-control'}),
            'transportista': forms.Select(attrs={'class': 'form-select'}),
            'chofer': forms.Select(attrs={'class': 'form-select'}),
            'tractor': forms.Select(attrs={'class': 'form-select'}),
            'tolva': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select'}),

            'pdf_registro_camion_remision': forms.FileInput(attrs={'class': 'form-control', 'accept': 'application/pdf'}),
            'pdf_remision_permiso': forms.FileInput(attrs={'class': 'form-control', 'accept': 'application/pdf'}),
            'foto_superior_vacia': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'foto_frontal': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'foto_superior_llena': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'foto_trasera': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            ternium_empresa = Empresa.objects.get(nombre__iexact="TERNIUM")
            self.fields['transportista'].queryset = LineaTransporte.objects.filter(empresas=ternium_empresa).order_by('nombre')
            self.fields['tractor'].queryset = Unidad.objects.filter(empresas=ternium_empresa).order_by('internal_id')
            self.fields['tolva'].queryset = Contenedor.objects.filter(empresas=ternium_empresa).order_by('nombre')
            self.fields['material'].queryset = Material.objects.filter(empresas=ternium_empresa).order_by('nombre')
        except Empresa.DoesNotExist:
            self.fields['transportista'].queryset = LineaTransporte.objects.none()
            self.fields['tractor'].queryset = Unidad.objects.none()
            self.fields['tolva'].queryset = Contenedor.objects.none()
            self.fields['material'].queryset = Material.objects.none()

        self.fields['chofer'].queryset = Operador.objects.all().order_by('nombre')
        
        for field_name in ['transportista', 'chofer', 'tractor', 'tolva', 'material']:
            self.fields[field_name].empty_label = "Seleccione una opción"
            
        if self.instance and self.instance.pk and self.instance.status == 'AUDITADO':
            for field in self.fields:
                self.fields[field].disabled = True
    
    def clean(self):
        cleaned_data = super().clean()
        remision_id = cleaned_data.get('remision')
        if not remision_id:
            return cleaned_data

        file_map = {
            'pdf_registro_camion_remision': f"{remision_id}-4.pdf",
            'pdf_remision_permiso': f"{remision_id}-5.pdf",
            'foto_superior_vacia': f"{remision_id}-0",
            'foto_frontal': f"{remision_id}-1",
            'foto_superior_llena': f"{remision_id}-2",
            'foto_trasera': f"{remision_id}-3",
        }

        for field_name, new_name in file_map.items():
            uploaded_file = self.files.get(field_name)
            if uploaded_file:
                if '.' not in new_name:
                    extension = os.path.splitext(uploaded_file.name)[1]
                    uploaded_file.name = f"{new_name}{extension}"
                else:
                    uploaded_file.name = new_name
        
        return cleaned_data
    
from django.contrib.auth.forms import AuthenticationForm

class CustomLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control', 
            'placeholder': 'Usuario'
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control', 
            'placeholder': 'Contraseña'
        })
        
class EmpresaOrigenesForm(forms.ModelForm):
    """
    Formulario específico para vincular orígenes a una empresa.
    """
    class Meta:
        model = Empresa
        fields = ['origenes']
        widgets = {
            'origenes': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'origenes': 'Seleccione los orígenes permitidos para esta unidad de negocio:'
        }
        
class ImportarRemisionesForm(forms.Form):
    """
    Formulario simple para subir archivos Excel de remisiones.
    No está vinculado a un modelo directamente.
    """
    archivo_excel = forms.FileField(
        label="Seleccionar Archivo Excel (.xlsx)",
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx, .xls'
        })
    )