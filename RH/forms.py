# RH/forms.py
from django import forms
from django.db.models import Q
from .models import (
    Empleado, Departamento, Puesto, MotivoInactivacion,
    TipoDocumentoOperador, DocumentoOperador, HistorialLaboral,
    Salario, Contrato, DivisionOperativa, TipoCarga, TipoViaje,
    Hijo, BajaEmpleado, MotivoBaja, ControlVacante
)
from datetime import date, timedelta, datetime
from .models import Vacacion, Prestamo, PagoPrestamo, HistoricoVacaciones
from datetime import date
import math
from decimal import Decimal
from django.db.models import Sum, Count, Avg



class EmpleadoForm(forms.ModelForm):
    # Hacer los campos no requeridos por defecto.
    tipo_carga = forms.ModelMultipleChoiceField(
        queryset=TipoCarga.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2'}),
        required=False, 
        label="Tipo de Carga"
    )
    tipo_viaje = forms.ModelMultipleChoiceField(
        queryset=TipoViaje.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2'}),
        required=False,
        label="Tipo de Viaje"
    )
    division_operativa = forms.ModelMultipleChoiceField(
        queryset=DivisionOperativa.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2'}),
        required=False,
        label="División Operativa"
    )

    class Meta:
        model = Empleado
        fields = '__all__'
        widgets = {
            # ... (los otros widgets permanecen sin cambios) ...
            'numero_empleado': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'puesto': forms.Select(attrs={'class': 'form-select'}),
            'departamento': forms.Select(attrs={'class': 'form-select'}),
            'fecha_contratacion': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}, 
                format='%Y-%m-%d'
            ),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_activo_toggle'}),
            'motivo_inactivacion': forms.Select(attrs={'class': 'form-select', 'id': 'id_motivo_inactivacion'}),
            'fecha_inactivacion': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control', 'id': 'id_fecha_inactivacion'}, 
                format='%Y-%m-%d'
            ),
            'fecha_nacimiento': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}, 
                format='%Y-%m-%d'
            ),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Calle y Número Ext/Int'}),
            'colonia': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_postal': forms.TextInput(attrs={'class': 'form-control'}),
            'ciudad': forms.TextInput(attrs={'class': 'form-control'}),
            'estado': forms.TextInput(attrs={'class': 'form-control'}),
            'pais': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor': forms.Select(attrs={'class': 'form-select'}),
            'nombre_conyuge': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono_conyuge': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+521234567890'}),
            'telefono_personal': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+521234567890'}),
            'estado_civil': forms.Select(attrs={'class': 'form-select'}),
            'nacionalidad': forms.TextInput(attrs={'class': 'form-control'}),
            'curp': forms.TextInput(attrs={'class': 'form-control'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control'}),
            'nss': forms.TextInput(attrs={'class': 'form-control'}),
            'foto_perfil': forms.FileInput(attrs={'class': 'form-control'}),
            'banco': forms.TextInput(attrs={'class': 'form-control'}),
            'clabe_interbancaria': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_tarjeta': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre_referencia_1': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono_referencia_1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+521234567890'}),
            'relacion_referencia_1': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre_referencia_2': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono_referencia_2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+521234567890'}),
            'relacion_referencia_2': forms.TextInput(attrs={'class': 'form-control'}),
            'ine_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'comprobante_domicilio': forms.FileInput(attrs={'class': 'form-control'}),
            'curriculum_vitae': forms.FileInput(attrs={'class': 'form-control'}),
            'acta_nacimiento_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'comprobante_estudios_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'carta_recomendacion_1_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'carta_recomendacion_2_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'constancia_fiscal_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'aviso_retencion_infonavit_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'semanas_cotizadas_imss_documento': forms.FileInput(attrs={'class': 'form-control'}),
            'empresa': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'numero_empleado': 'Número de Empleado Interno',
            'nombre_conyuge': 'Nombre del Cónyuge o Pareja',
            'numero_tarjeta': 'Número de Tarjeta (16 dígitos)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        supervisor_query = Q(puesto__nombre__icontains='Supervisor') | Q(puesto__nombre__icontains='Gerente')
        potential_supervisors = Empleado.objects.filter(supervisor_query).order_by('apellido', 'nombre')

        if self.instance and self.instance.pk:
            self.fields['supervisor'].queryset = potential_supervisors.exclude(pk=self.instance.pk)
        else:
            self.fields['supervisor'].queryset = potential_supervisors

        # --- MODIFICACIÓN ---
        # Iterar sobre todos los campos y establecerlos como no obligatorios
        for field_name, field in self.fields.items():
            field.required = False
            
            # Opcional: También puedes quitar la clase 'is-required' si la estabas usando
            widget_attrs = field.widget.attrs
            if 'class' in widget_attrs:
                widget_attrs['class'] = widget_attrs['class'].replace('is-required', '')
        
        # FORZAR campos mínimos obligatorios para evitar IntegrityError (NOT NULL)
        self.fields['nombre'].required = True
        self.fields['apellido'].required = True

        # 👇👇👇 NUEVO BLOQUE: FIX PARA QUE NO SE RESETEEN LAS FECHAS AL EDITAR 👇👇👇
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass # Si ya es string, lo deja pasar
        # 👆👆👆 FIN DEL NUEVO BLOQUE 👆👆👆

    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # Si el usuario ingresó un correo (no está vacío)
        if email:
            # 1. Verificar si ya existe ese correo en otro empleado
            # Excluimos al empleado actual (self.instance) para permitir guardar 
            # el mismo correo si no se ha modificado.
            qs = Empleado.objects.filter(email=email)
            
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            
            if qs.exists():
                raise forms.ValidationError("Este correo electrónico ya está asignado a otro empleado. Por favor utiliza uno diferente.")
        
        # Si está vacío, devolver None para evitar errores de unicidad con cadena vacía
        return email or None

    def clean_numero_empleado(self):
        val = self.cleaned_data.get('numero_empleado')
        return val or None

    def clean_curp(self):
        val = self.cleaned_data.get('curp')
        return val or None

    def clean_rfc(self):
        val = self.cleaned_data.get('rfc')
        return val or None

    def clean_nss(self):
        val = self.cleaned_data.get('nss')
        return val or None
    
    def clean_puesto_anterior(self):
        val = self.cleaned_data.get('puesto_anterior')
        return val if val else ''
    
    def clean_fecha_contratacion(self):
        fecha = self.cleaned_data.get('fecha_contratacion')
        if fecha == '':
            return None
        return fecha
    
    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data.get('fecha_nacimiento')
        if fecha == '':
            return None
        return fecha
    
    def clean_fecha_inactivacion(self):
        fecha = self.cleaned_data.get('fecha_inactivacion')
        if fecha == '':
            return None
        return fecha

    def clean_fecha_ingreso(self):
        fecha = self.cleaned_data.get('fecha_ingreso')
        if fecha == '':
            return None
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        
    # ---------------------------------------------------------
    # LIMPIEZA DE DATOS DEL SAT (Corta todo después del guion)
    # ---------------------------------------------------------
    def clean_colonia(self):
        val = self.cleaned_data.get('colonia', '')
        if val and '-' in str(val):
            return str(val).split('-')[0].strip()
        return val.strip() if val else val

    def clean_ciudad(self):
        val = self.cleaned_data.get('ciudad', '')
        if val and '-' in str(val):
            return str(val).split('-')[0].strip()
        return val.strip() if val else val

    def clean_estado(self):
        val = self.cleaned_data.get('estado', '')
        if val and '-' in str(val):
            return str(val).split('-')[0].strip()
        return val.strip() if val else val
    
    def clean_pais(self):
        val = self.cleaned_data.get('pais', '')
        # Si viene "MEX - MEXICO", se queda solo con "MEX"
        if val and '-' in str(val):
            return str(val).split('-')[0].strip()
        return val.strip() if val else val
        
        # --- MODIFICACIÓN ---
        # Se elimina (o comenta) la lógica de validación condicional para
        # que ningún campo sea obligatorio, ni siquiera para Operadores.
        
        # puesto = cleaned_data.get('puesto')
        # if puesto and 'operador' in puesto.nombre.lower():
        #     if not cleaned_data.get('tipo_viaje'):
        #         self.add_error('tipo_viaje', 'Este campo es obligatorio para el puesto de Operador.')
        #     
        #     if not cleaned_data.get('tipo_carga'):
        #         self.add_error('tipo_carga', 'Este campo es obligatorio para el puesto de Operador.')
        #
        #     if not cleaned_data.get('division_operativa'):
        #         self.add_error('division_operativa', 'Este campo es obligatorio para el puesto de Operador.')
        
        return cleaned_data



class HijoForm(forms.ModelForm):
    class Meta:
        model = Hijo
        fields = ['nombre', 'fecha_nacimiento']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- NUEVO: Hacer todos los campos no obligatorios ---
        for field_name, field in self.fields.items():
            field.required = False

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data.get('fecha_nacimiento')
        if fecha == '':
            return None
        return fecha


class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = '__all__'
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'nombre': 'Nombre del Departamento',
            'descripcion': 'Descripción',
        }

class PuestoForm(forms.ModelForm):
    class Meta:
        model = Puesto
        fields = '__all__'
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'salario_base': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nombre': 'Nombre del Puesto',
            'descripcion': 'Descripción',
            'salario_base': 'Salario Base',
        }

class MotivoInactivacionForm(forms.ModelForm):
    class Meta:
        model = MotivoInactivacion
        fields = '__all__'
        widgets = {
            'motivo': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'motivo': 'Motivo de Inactivación',
            'descripcion': 'Descripción del Motivo',
        }

class TipoDocumentoOperadorForm(forms.ModelForm):
    class Meta:
        model = TipoDocumentoOperador
        fields = '__all__'
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'requiere_fecha_vencimiento': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nombre': 'Nombre del Tipo de Documento',
            'descripcion': 'Descripción',
            'requiere_fecha_vencimiento': '¿Requiere Fecha de Vencimiento?',
        }

class DocumentoOperadorForm(forms.ModelForm):
    class Meta:
        model = DocumentoOperador
        fields = ['tipo_documento', 'archivo', 'numero_documento', 'fecha_expedicion', 'fecha_vencimiento', 'observaciones']
        widgets = {
            'tipo_documento': forms.Select(attrs={'class': 'form-select document-type-select'}),
            'archivo': forms.FileInput(attrs={'class': 'form-control'}),
            'numero_documento': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_expedicion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_vencimiento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control expiry-date-field'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- NUEVO: Hacer todos los campos no obligatorios ---
        for field_name, field in self.fields.items():
            field.required = False

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass
            
    def clean(self):
        cleaned_data = super().clean()
        
        tipo = cleaned_data.get('tipo_documento')
        archivo = cleaned_data.get('archivo')
        numero = cleaned_data.get('numero_documento')
        expedicion = cleaned_data.get('fecha_expedicion')
        vencimiento = cleaned_data.get('fecha_vencimiento')
        obs = cleaned_data.get('observaciones')

        # Verificamos si escribió ALGO en CUALQUIER campo de la fila
        has_data = any([tipo, archivo, numero, expedicion, vencimiento, obs])

        if has_data:
            if not tipo:
                self.add_error('tipo_documento', 'El tipo de documento es obligatorio.')

        return cleaned_data
    
    def clean_fecha_expedicion(self):
        fecha = self.cleaned_data.get('fecha_expedicion')
        if fecha == '':
            return None
        return fecha
    
    def clean_fecha_vencimiento(self):
        fecha = self.cleaned_data.get('fecha_vencimiento')
        if fecha == '':
            return None
        return fecha

class SalarioForm(forms.ModelForm):
    class Meta:
        model = Salario
        fields = ['sueldo_diario', 'fecha_efectiva', 'observaciones']
        widgets = {
            'sueldo_diario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'fecha_efectiva': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mantienes tu lógica de hacerlos opcionales visualmente
        for field_name, field in self.fields.items():
            field.required = False

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass

    # --- AGREGAR ESTA VALIDACIÓN ---
    def clean(self):
        cleaned_data = super().clean()
        sueldo = cleaned_data.get('sueldo_diario')
        fecha = cleaned_data.get('fecha_efectiva')
        observaciones = cleaned_data.get('observaciones')

        # Lógica: Si se llenó ALGUN campo, los obligatorios deben estar presentes.
        # Si todos están vacíos, se asume que no se quiere guardar nada en esta fila.
        has_data = sueldo or fecha or observaciones

        if has_data:
            if not sueldo:
                self.add_error('sueldo_diario', 'Este campo es obligatorio al registrar un salario.')
            if not fecha:
                self.add_error('fecha_efectiva', 'La fecha efectiva es obligatoria.')

        return cleaned_data

class HistorialLaboralForm(forms.ModelForm):
    class Meta:
        model = HistorialLaboral
        fields = ['tipo_evento', 'fecha_inicio', 'fecha_fin', 'puesto', 'departamento', 'descripcion', 'motivo_salida', 'documento_adjunto']
        widgets = {
            'tipo_evento': forms.Select(attrs={'class': 'form-select history-event-type'}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'puesto': forms.TextInput(attrs={'class': 'form-control'}),
            'departamento': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'motivo_salida': forms.Select(attrs={'class': 'form-select history-reason-select'}),
            'documento_adjunto': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- NUEVO: Hacer todos los campos no obligatorios ---
        for field_name, field in self.fields.items():
            field.required = False

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass
            
    def clean(self):
        cleaned_data = super().clean()
        
        tipo = cleaned_data.get('tipo_evento')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        puesto = cleaned_data.get('puesto')
        departamento = cleaned_data.get('departamento')
        descripcion = cleaned_data.get('descripcion')
        motivo = cleaned_data.get('motivo_salida')
        documento = cleaned_data.get('documento_adjunto')

        # Verificamos absolutamente todos los campos de la fila
        has_data = any([tipo, fecha_inicio, fecha_fin, puesto, departamento, descripcion, motivo, documento])

        if has_data:
            if not tipo:
                self.add_error('tipo_evento', 'El tipo de evento es obligatorio.')
            if not fecha_inicio:
                self.add_error('fecha_inicio', 'La fecha de inicio es obligatoria.')
        
        return cleaned_data
    
    def clean_fecha_inicio(self):
        fecha = self.cleaned_data.get('fecha_inicio')
        if fecha == '':
            return None
        return fecha
    
    def clean_fecha_fin(self):
        fecha = self.cleaned_data.get('fecha_fin')
        if fecha == '':
            return None
        return fecha

class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        fields = ['tipo_contrato', 'fecha_inicio', 'fecha_fin', 'archivo_contrato', 'comentarios']
        widgets = {
            'tipo_contrato': forms.Select(attrs={'class': 'form-select contract-type-select'}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control contract-end-date'}),
            'archivo_contrato': forms.FileInput(attrs={'class': 'form-control'}),
            'comentarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- NUEVO: Hacer todos los campos no obligatorios ---
        for field_name, field in self.fields.items():
            field.required = False

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass
    
    def clean(self):
        cleaned_data = super().clean()
        
        tipo = cleaned_data.get('tipo_contrato')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        archivo = cleaned_data.get('archivo_contrato')
        comentarios = cleaned_data.get('comentarios')

        # Incluimos fecha_fin en la validación
        has_data = any([tipo, fecha_inicio, fecha_fin, archivo, comentarios])

        if has_data:
            if not tipo:
                self.add_error('tipo_contrato', 'El tipo de contrato es obligatorio.')
            if not fecha_inicio:
                self.add_error('fecha_inicio', 'La fecha de inicio es obligatoria.')
        
        return cleaned_data
    
    def clean_fecha_inicio(self):
        fecha = self.cleaned_data.get('fecha_inicio')
        if fecha == '':
            return None
        return fecha
    
    def clean_fecha_fin(self):
        fecha = self.cleaned_data.get('fecha_fin')
        if fecha == '':
            return None
        return fecha
    
# En RH/forms.py - Agrega estos formularios

class BajaEmpleadoForm(forms.ModelForm):
    """Formulario para dar de baja a un empleado"""
    
    class Meta:
        model = BajaEmpleado
        fields = [
            'motivo_principal',
            'motivo_secundario',
            'motivo_detalle',
            'fecha_baja',
            'comentario_baja',
            'documento_baja',
            'es_recontratable',
            'motivo_recontratable',
            'fecha_posible_recontratacion',
            # NUEVOS CAMPOS
            'fue_conciliacion_arbitraje',
            'fecha_conciliacion_arbitraje',
            'documento_conciliacion',
            'observaciones_conciliacion',
        ]
        widgets = {
            'fecha_baja': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'fecha_posible_recontratacion': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'fecha_conciliacion_arbitraje': forms.DateInput(  # NUEVO
                attrs={'type': 'date', 'class': 'form-control', 'id': 'fecha_conciliacion'}
            ),
            'comentario_baja': forms.Textarea(
                attrs={'rows': 4, 'class': 'form-control'}
            ),
            'observaciones_conciliacion': forms.Textarea(  # NUEVO
                attrs={'rows': 3, 'class': 'form-control', 'id': 'observaciones_conciliacion'}
            ),
            'motivo_recontratable': forms.Textarea(
                attrs={'rows': 3, 'class': 'form-control'}
            ),
            'documento_baja': forms.ClearableFileInput(
                attrs={'class': 'form-control'}
            ),
            'documento_conciliacion': forms.ClearableFileInput(  # NUEVO
                attrs={'class': 'form-control', 'id': 'documento_conciliacion'}
            ),
        }
        labels = {
            'comentario_baja': 'Comentarios de la Baja',
            'documento_baja': 'Documento de Baja (PDF, Word, etc.)',
            'fue_conciliacion_arbitraje': '¿El empleado acudió a Conciliación y Arbitraje?',  # NUEVO
            'documento_conciliacion': 'Documento de Conciliación y Arbitraje',  # NUEVO
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filtrar opciones según tipo de motivo
        self.fields['motivo_principal'].queryset = MotivoBaja.objects.filter(
            tipo_motivo='PRINCIPAL', 
            activo=True
        )
        self.fields['motivo_secundario'].queryset = MotivoBaja.objects.filter(
            tipo_motivo='SECUNDARIO', 
            activo=True
        )
        self.fields['motivo_detalle'].queryset = MotivoBaja.objects.filter(
            tipo_motivo='DETALLE', 
            activo=True
        )
        
        # Hacer campos requeridos
        self.fields['motivo_principal'].required = True
        self.fields['fecha_baja'].required = True
        self.fields['comentario_baja'].required = True
        
        # Agregar clases CSS
        for field in self.fields:
            if field not in ['documento_baja']:
                self.fields[field].widget.attrs.update({'class': 'form-control'})
        
        # Agregar placeholders
        self.fields['comentario_baja'].widget.attrs['placeholder'] = (
            'Describe los detalles de la baja, situación, antecedentes, etc.'
        )
        self.fields['motivo_recontratable'].widget.attrs['placeholder'] = (
            '¿Por qué consideras que este empleado es recontratable?'
        )

        # Agregar clases CSS a los nuevos campos
        self.fields['fue_conciliacion_arbitraje'].widget.attrs.update({
            'class': 'form-check-input',
            'id': 'id_fue_conciliacion'
        })
        
        # Configurar ayuda para nuevos campos
        self.fields['observaciones_conciliacion'].widget.attrs['placeholder'] = (
            'Detalles sobre el proceso de conciliación, acuerdos, etc.'
        )
        
        # Hacer campos condicionales (manejados con JavaScript)
        self.fields['fecha_conciliacion_arbitraje'].required = False
        self.fields['documento_conciliacion'].required = False

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass
        
    def clean(self):
        cleaned_data = super().clean()
        fue_conciliacion = cleaned_data.get('fue_conciliacion_arbitraje')
        fecha_conciliacion = cleaned_data.get('fecha_conciliacion_arbitraje')
        documento_conciliacion = cleaned_data.get('documento_conciliacion')
        
        # Validación condicional
        if fue_conciliacion:
            if not fecha_conciliacion:
                self.add_error('fecha_conciliacion_arbitraje', 
                              'Este campo es obligatorio si el empleado fue a Conciliación y Arbitraje')
            if not documento_conciliacion:
                self.add_error('documento_conciliacion',
                              'Es necesario subir el documento de Conciliación y Arbitraje')
        
        return cleaned_data


class RecontratacionForm(forms.ModelForm):
    """Formulario para recontratar a un empleado"""
    
    class Meta:
        model = BajaEmpleado
        fields = [
            'fecha_recontratacion',
            'comentario_recontratacion'
        ]
        widgets = {
            'fecha_recontratacion': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'comentario_recontratacion': forms.Textarea(
                attrs={'rows': 4, 'class': 'form-control'}
            ),
        }
        labels = {
            'fecha_recontratacion': 'Fecha de Recontratación',
            'comentario_recontratacion': 'Comentarios de Recontratación',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_recontratacion'].required = True
        self.fields['comentario_recontratacion'].required = True
        
        # Establecer fecha mínima (hoy)
        hoy = date.today()
        self.fields['fecha_recontratacion'].widget.attrs['min'] = hoy.strftime('%Y-%m-%d')
        
        # Placeholder
        self.fields['comentario_recontratacion'].widget.attrs['placeholder'] = (
            'Motivos de la recontratación, condiciones acordadas, etc.'
        )

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass

# RH/forms.py - Agrega estos formularios después de RecontratacionForm

class VacacionForm(forms.ModelForm):
    """Formulario para solicitud de vacaciones con modo histórico y modo libre/normal"""
    
    class Meta:
        model = Vacacion
        fields = [
            'tipo_vacacion',
            'fecha_inicio',
            'fecha_fin',
            'periodo_correspondiente',
            'observaciones',
            'documento_solicitud'
        ]
        widgets = {
            'fecha_inicio': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'fecha_fin': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'periodo_correspondiente': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'YYYY-MM'}
            ),
            'observaciones': forms.Textarea(
                attrs={'rows': 4, 'class': 'form-control'}
            ),
        }
    
    def __init__(self, *args, **kwargs):
        self.empleado = kwargs.pop('empleado', None)
        self.modo_historico = kwargs.pop('modo_historico', False)
        
        # Guardar data para uso posterior si existe
        self.request_data = None
        if args:
            self.request_data = args[0]
        
        super().__init__(*args, **kwargs)
        
        hoy = date.today()
        
        # Asegurar que las opciones del campo tipo_vacacion estén disponibles
        self.fields['tipo_vacacion'].choices = Vacacion.TIPO_VACACION_CHOICES
        
        if self.modo_historico:
            # MODO HISTÓRICO / LIBRE: NO bloqueamos fechas futuras
            # self.fields['fecha_inicio'].widget.attrs['max'] = hoy.strftime('%Y-%m-%d')
            # self.fields['fecha_fin'].widget.attrs['max'] = hoy.strftime('%Y-%m-%d')
            
            # Cambiar etiquetas para modo histórico
            self.fields['fecha_inicio'].label = "Fecha de Inicio (Libre/Histórico)"
            self.fields['fecha_fin'].label = "Fecha de Fin (Libre/Histórico)"
            self.fields['observaciones'].label = "Observaciones"
            
            # Forzar tipo de vacación a HISTORICO
            self.fields['tipo_vacacion'].initial = 'HISTORICO'
            self.fields['tipo_vacacion'].widget = forms.HiddenInput()
            
            # Establecer fechas iniciales sugeridas (Mes actual, NO el año pasado)
            self.fields['fecha_inicio'].initial = date(hoy.year, hoy.month, 1)
            self.fields['fecha_fin'].initial = date(hoy.year, hoy.month, 15)
            
        else:
            # MODO NORMAL: Mantener restricciones actuales pero calendario desbloqueado
            # fecha_minima_normal = hoy + timedelta(days=15)
            # self.fields['fecha_inicio'].widget.attrs['min'] = fecha_minima_normal.strftime('%Y-%m-%d')
            # self.fields['fecha_fin'].widget.attrs['min'] = fecha_minima_normal.strftime('%Y-%m-%d')
            
            # Establecer tipo de vacación normal como ORDINARIAS
            self.fields['tipo_vacacion'].initial = 'ORDINARIAS'
            self.fields['tipo_vacacion'].widget = forms.Select(attrs={'class': 'form-control'})
        
        # Sugerir período correspondiente basado en datos disponibles
        if self.modo_historico:
            año_actual = hoy.year
            self.fields['periodo_correspondiente'].initial = f"{año_actual}-{hoy.month:02d}"
        elif self.empleado and self.empleado.fecha_contratacion:
            año_actual = hoy.year
            self.fields['periodo_correspondiente'].initial = f"{año_actual}-{hoy.month:02d}"
        
        # Si hay data en la request, intentar sugerir período basado en fecha_inicio
        if self.request_data and 'fecha_inicio' in self.request_data:
            fecha_inicio_str = self.request_data.get('fecha_inicio')
            try:
                fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                self.fields['periodo_correspondiente'].initial = f"{fecha_inicio_obj.year}-{fecha_inicio_obj.month:02d}"
                
                # También establecer las fechas iniciales si es modo histórico
                if self.modo_historico:
                    self.fields['fecha_inicio'].initial = fecha_inicio_obj
                    
                    # Calcular fecha_fin sugerida (14 días después)
                    fecha_fin_sugerida = fecha_inicio_obj + timedelta(days=14)
                    self.fields['fecha_fin'].initial = fecha_fin_sugerida
                        
            except (ValueError, TypeError):
                pass
        
        # Ayuda contextual
        if self.modo_historico:
            self.fields['fecha_inicio'].help_text = "Puede seleccionar fechas pasadas o futuras"
            self.fields['fecha_fin'].help_text = "Puede seleccionar fechas pasadas o futuras"
            self.fields['periodo_correspondiente'].help_text = "Período al que corresponden las vacaciones (ej: 2024-04)"
        else:
            self.fields['fecha_inicio'].help_text = "Mínimo 15 días hábiles de anticipación recomendados"
            self.fields['fecha_fin'].help_text = "Máximo 15 días continuos"

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass
    
    def calcular_dias_disponibles(self, empleado, año):
        """Calcula días de vacaciones disponibles según antigüedad"""
        if not empleado.fecha_contratacion:
            return 0
        
        # Calcular antigüedad al final del año especificado
        fin_de_año = date(año, 12, 31)
        antiguedad_dias = (fin_de_año - empleado.fecha_contratacion).days
        antiguedad_anios = antiguedad_dias / 365.25
        
        # Aplicar escala según antigüedad
        if antiguedad_anios < 1:
            return 0
        elif antiguedad_anios < 2:
            return 12
        elif antiguedad_anios < 3:
            return 14
        elif antiguedad_anios < 4:
            return 16
        elif antiguedad_anios < 5:
            return 18
        else:
            años_enteros = int(antiguedad_anios)
            años_extra = años_enteros - 5
            dias_extra = (años_extra // 5) * 2
            return 20 + dias_extra
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Si hay errores en campos individuales, no continuar
        if self.errors:
            return cleaned_data
        
        # Obtener fechas
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        periodo_correspondiente = cleaned_data.get('periodo_correspondiente')
        
        # --- CONVERSIÓN DE FECHAS ---
        fecha_inicio_obj = None
        fecha_fin_obj = None
        
        if fecha_inicio:
            if isinstance(fecha_inicio, str):
                try:
                    fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        fecha_inicio_obj = datetime.strptime(fecha_inicio, '%d/%m/%Y').date()
                    except ValueError:
                        self.add_error('fecha_inicio', 'Formato de fecha inválido. Use DD/MM/YYYY')
                        return cleaned_data
            else:
                fecha_inicio_obj = fecha_inicio
            cleaned_data['fecha_inicio'] = fecha_inicio_obj
        
        if fecha_fin:
            if isinstance(fecha_fin, str):
                try:
                    fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        fecha_fin_obj = datetime.strptime(fecha_fin, '%d/%m/%Y').date()
                    except ValueError:
                        self.add_error('fecha_fin', 'Formato de fecha inválido. Use DD/MM/YYYY')
                        return cleaned_data
            else:
                fecha_fin_obj = fecha_fin
            cleaned_data['fecha_fin'] = fecha_fin_obj
        
        if fecha_inicio_obj and fecha_fin_obj:
            # Validar que la fecha de inicio sea anterior a la de fin
            if fecha_inicio_obj > fecha_fin_obj:
                self.add_error('fecha_fin', 'La fecha de fin debe ser posterior a la fecha de inicio.')
                return cleaned_data
            
            # Calcular días solicitados (incluyendo ambos días)
            dias_calendario = (fecha_fin_obj - fecha_inicio_obj).days + 1
            cleaned_data['dias_solicitados'] = dias_calendario
            
            # Validaciones específicas por modo
            if not self.modo_historico:
                # MODO NORMAL: Validaciones para vacaciones regulares
                hoy = date.today()
                
                # Validar máximo 15 días continuos
                if dias_calendario > 15:
                    self.add_error(
                        'fecha_fin',
                        f'El máximo permitido es 15 días continuos. Ha solicitado {dias_calendario} días.'
                    )
                
                # Validar días disponibles (permitimos enviar si es necesario, pero calculamos bien)
                if self.empleado:
                    año_vacaciones = fecha_inicio_obj.year
                    dias_disponibles = self.calcular_dias_disponibles(self.empleado, año_vacaciones)
                    
                    from django.db.models import Sum
                    dias_tomados_este_año = Vacacion.objects.filter(
                        empleado=self.empleado,
                        fecha_inicio__year=año_vacaciones,
                        estado__in=['APROBADO', 'GOZADO'],
                        tipo_vacacion='ORDINARIAS'
                    ).aggregate(total=Sum('dias_reales'))['total'] or 0
                    
                    dias_disponibles_reales = dias_disponibles - dias_tomados_este_año
                    
                    # COMENTAMOS la restricción dura de días insuficientes para dar flexibilidad a RH
                    # if dias_calendario > dias_disponibles_reales:
                    #     self.add_error(...)
            
            else:
                # MODO HISTÓRICO / LIBRE: Validaciones más flexibles
                hoy = date.today()
                
                # Validar que la fecha no sea demasiado antigua (más de 5 años)
                fecha_limite_historica = date(hoy.year - 5, 1, 1)
                if fecha_inicio_obj < fecha_limite_historica:
                    self.add_error(
                        'fecha_inicio',
                        f'Las fechas no pueden ser mayores a 5 años atrás. '
                        f'Fecha mínima permitida: {fecha_limite_historica.strftime("%d/%m/%Y")}'
                    )
                
                if fecha_fin_obj < fecha_limite_historica:
                    self.add_error(
                        'fecha_fin',
                        f'Las fechas no pueden ser mayores a 5 años atrás. '
                        f'Fecha mínima permitida: {fecha_limite_historica.strftime("%d/%m/%Y")}'
                    )
                
                # Validar período correspondiente si se especificó
                if periodo_correspondiente:
                    try:
                        año_periodo = int(periodo_correspondiente.split('-')[0])
                        if año_periodo != fecha_inicio_obj.year:
                            self.add_error(
                                'periodo_correspondiente',
                                f'El período debe corresponder al año de la fecha de inicio ({fecha_inicio_obj.year}). '
                                f'Sugerencia: {fecha_inicio_obj.year}-{fecha_inicio_obj.month:02d}'
                            )
                    except (ValueError, IndexError):
                        self.add_error(
                            'periodo_correspondiente',
                            'Formato inválido. Use YYYY-MM (ej: 2024-04).'
                        )
                else:
                    # Sugerir período si no se especificó
                    cleaned_data['periodo_correspondiente'] = f"{fecha_inicio_obj.year}-{fecha_inicio_obj.month:02d}"
                
                # Validar que no haya vacaciones duplicadas exactamente iguales
                if self.empleado and fecha_inicio_obj and fecha_fin_obj:
                    vacaciones_existentes = Vacacion.objects.filter(
                        empleado=self.empleado,
                        tipo_vacacion='HISTORICO',
                        fecha_inicio__year=fecha_inicio_obj.year
                    ).exclude(id=self.instance.id if self.instance else None)
                    
                    for vacacion_existente in vacaciones_existentes:
                        if (fecha_inicio_obj <= vacacion_existente.fecha_fin and 
                            fecha_fin_obj >= vacacion_existente.fecha_inicio):
                            self.add_error(
                                'fecha_inicio',
                                f'Ya existe un registro histórico para este período: '
                                f'{vacacion_existente.fecha_inicio.strftime("%d/%m/%Y")} - '
                                f'{vacacion_existente.fecha_fin.strftime("%d/%m/%Y")}'
                            )
                            break
        
        return cleaned_data
    
    def save(self, commit=True):
        """Guardar la vacación con configuraciones consolidadas"""
        vacacion = super().save(commit=False)
        
        # Establecer empleado si se proporcionó
        if self.empleado:
            vacacion.empleado = self.empleado
        
        # Establecer estado basado en el modo
        if self.modo_historico:
            vacacion.tipo_vacacion = 'HISTORICO'
            vacacion.estado = 'GOZADO'  # Históricas/Libres se marcan como gozadas automáticamente
        else:
            vacacion.tipo_vacacion = 'ORDINARIAS'
            vacacion.estado = 'PENDIENTE'  # Normales inician como pendientes
        
        # Asignar días solicitados si se calcularon en clean()
        if 'dias_solicitados' in self.cleaned_data:
            vacacion.dias_solicitados = self.cleaned_data['dias_solicitados']
        elif not hasattr(vacacion, 'dias_solicitados') or not vacacion.dias_solicitados:
            if vacacion.fecha_inicio and vacacion.fecha_fin:
                vacacion.dias_solicitados = (vacacion.fecha_fin - vacacion.fecha_inicio).days + 1
        
        # Establecer fecha de solicitud
        if not vacacion.fecha_solicitud:
            vacacion.fecha_solicitud = date.today()
        
        if commit:
            vacacion.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()
        
        return vacacion
    
    def calcular_dias_disponibles(self, empleado, año):
        """Calcula días de vacaciones disponibles según antigüedad"""
        if not empleado.fecha_contratacion:
            return 0
        
        # Calcular antigüedad al final del año especificado
        fin_de_año = date(año, 12, 31)
        antiguedad_dias = (fin_de_año - empleado.fecha_contratacion).days
        antiguedad_anios = antiguedad_dias / 365.25
        
        # Aplicar escala según antigüedad
        if antiguedad_anios < 1:
            return 0
        elif antiguedad_anios < 2:
            return 12
        elif antiguedad_anios < 3:
            return 14
        elif antiguedad_anios < 4:
            return 16
        elif antiguedad_anios < 5:
            return 18
        else:
            años_enteros = int(antiguedad_anios)
            años_extra = años_enteros - 5
            dias_extra = (años_extra // 5) * 2
            return 20 + dias_extra
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Asignar empleado si se proporcionó
        if self.empleado:
            instance.empleado = self.empleado
        
        # Asignar días solicitados si se calcularon en clean()
        if 'dias_solicitados' in self.cleaned_data:
            instance.dias_solicitados = self.cleaned_data['dias_solicitados']
        
        # En modo histórico, marcar como GOZADO automáticamente
        if self.modo_historico:
            instance.estado = 'GOZADO'
        
        if commit:
            instance.save()
        
        return instance





class PrestamoForm(forms.ModelForm):
    """Formulario para solicitud de préstamos con plazos en SEMANAS (1-52)"""
    
    class Meta:
        model = Prestamo
        fields = [
            'tipo_prestamo',
            'monto_total',
            'tasa_interes',
            'plazo_semanas',
            'fecha_primer_pago',
            'concepto',
            'observaciones',
            'documento_solicitud'
        ]
        widgets = {
            'fecha_primer_pago': forms.DateInput(
                attrs={
                    'type': 'date', 
                    'class': 'form-control',
                    'id': 'fecha_primer_pago'
                }
            ),
            'monto_total': forms.NumberInput(
                attrs={
                    'class': 'form-control', 
                    'step': '0.01',
                    'id': 'monto_total'
                }
            ),
            'tasa_interes': forms.NumberInput(
                attrs={
                    'class': 'form-control', 
                    'step': '0.01', 
                    'value': '0',
                    'id': 'tasa_interes'
                }
            ),
            'plazo_semanas': forms.NumberInput(
                attrs={
                    'class': 'form-control', 
                    'min': '1',
                    'max': '52',
                    'step': '1',
                    'id': 'plazo_semanas'
                }
            ),
            'tipo_prestamo': forms.Select(
                attrs={'class': 'form-control'}
            ),
            'concepto': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej: Préstamo para emergencia médica'
                }
            ),
            'observaciones': forms.Textarea(
                attrs={
                    'rows': 4, 
                    'class': 'form-control',
                    'placeholder': 'Detalles adicionales del préstamo...'
                }
            ),
            'documento_solicitud': forms.FileInput(
                attrs={'class': 'form-control'}
            ),
        }
        help_texts = {
            'plazo_semanas': 'Ingrese el plazo en semanas (1 a 52 semanas)',
            'tasa_interes': 'Tasa de interés anual en porcentaje. Use 0 para préstamo sin interés.',
        }
    
    def __init__(self, *args, **kwargs):
        self.empleado = kwargs.pop('empleado', None)
        super().__init__(*args, **kwargs)
        
        # Establecer fecha mínima (hoy + 1 semana)
        hoy = date.today()
        fecha_minima = hoy + timedelta(days=7)
        self.fields['fecha_primer_pago'].widget.attrs['min'] = fecha_minima.strftime('%Y-%m-%d')
        
        # Valor por defecto para fecha_primer_pago (2 semanas desde hoy)
        fecha_sugerida = hoy + timedelta(weeks=2)
        if not self.initial.get('fecha_primer_pago'):
            self.initial['fecha_primer_pago'] = fecha_sugerida
        
        # Labels personalizados
        self.fields['plazo_semanas'].label = 'Plazo en semanas (1-52)'
        self.fields['monto_total'].label = 'Monto total del préstamo'
        self.fields['tasa_interes'].label = 'Tasa de interés anual (%)'
        self.fields['fecha_primer_pago'].label = 'Fecha del primer pago'
        
        # Agregar placeholder para plazo
        self.fields['plazo_semanas'].widget.attrs['placeholder'] = 'Ej: 12 (12 semanas ≈ 3 meses)'

        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass
    
    def clean_plazo_semanas(self):
        plazo_semanas = self.cleaned_data.get('plazo_semanas')
        
        if not plazo_semanas:
            raise forms.ValidationError('Debe especificar el plazo en semanas')
        if plazo_semanas < 1:
            raise forms.ValidationError('El plazo mínimo es 1 semana')
        if plazo_semanas > 52:
            raise forms.ValidationError('El plazo máximo es 52 semanas (1 año)')
        
        return plazo_semanas
    
    def clean_monto_total(self):
        monto = self.cleaned_data.get('monto_total')
        
        if not monto:
            raise forms.ValidationError('Debe especificar el monto del préstamo')
        if monto <= 0:
            raise forms.ValidationError('El monto debe ser mayor a 0')
        if monto < 100:
            raise forms.ValidationError('El monto mínimo es $100.00')
        
        if self.empleado:
            salario_actual = self.empleado.salario_actual
            if salario_actual and salario_actual.sueldo_mensual:
                limite_maximo = salario_actual.sueldo_mensual * Decimal('3')
                if monto > limite_maximo:
                    raise forms.ValidationError(
                        f'El monto máximo permitido es ${limite_maximo:,.2f} '
                        f'(3 meses de sueldo).'
                    )
        
        return monto
    
    def clean_tasa_interes(self):
        tasa = self.cleaned_data.get('tasa_interes')
        
        if tasa is None:
            tasa = Decimal('0')
        if tasa < 0:
            raise forms.ValidationError('La tasa de interés no puede ser negativa')
        if tasa > 50:
            raise forms.ValidationError('La tasa de interés máxima permitida es 50%')
        
        return tasa
    
    def clean_fecha_primer_pago(self):
        fecha = self.cleaned_data.get('fecha_primer_pago')
        
        if not fecha:
            raise forms.ValidationError('Debe especificar la fecha del primer pago')
        
        hoy = date.today()
        if fecha < hoy + timedelta(days=7):
            raise forms.ValidationError('La fecha del primer pago debe ser al menos 7 días después de hoy')
        if fecha > hoy + timedelta(days=90):
            raise forms.ValidationError('La fecha del primer pago no puede ser más de 3 meses en el futuro')
        
        return fecha
    
    def clean(self):
        cleaned_data = super().clean()
        
        monto = cleaned_data.get('monto_total')
        plazo_semanas = cleaned_data.get('plazo_semanas')
        tasa = cleaned_data.get('tasa_interes', Decimal('0'))
        
        if monto and plazo_semanas and tasa is not None:
            monto_decimal = Decimal(str(monto))
            plazo_decimal = Decimal(str(plazo_semanas))
            tasa_decimal = Decimal(str(tasa))
            
            interes_anual = tasa_decimal / Decimal('100')
            pago_semanal = Decimal('0')
            
            if interes_anual > 0:
                tasa_semanal = interes_anual / Decimal('52')
                n = int(plazo_semanas)
                r = float(tasa_semanal)
                
                if r > 0 and n > 0:
                    uno_mas_r = 1 + r
                    uno_mas_r_pow_n = uno_mas_r ** n
                    numerador = r * uno_mas_r_pow_n
                    denominador = uno_mas_r_pow_n - 1
                    
                    if denominador != 0:
                        pago_semanal_float = float(monto_decimal) * (numerador / denominador)
                        pago_semanal = Decimal(str(pago_semanal_float))
                    else:
                        pago_semanal = monto_decimal / plazo_decimal
                else:
                    pago_semanal = monto_decimal / plazo_decimal
            else:
                pago_semanal = monto_decimal / plazo_decimal
            
            pago_semanal = round(pago_semanal, 2)
            cleaned_data['pago_semanal_calculado'] = pago_semanal
            
            pago_mensual_aproximado = pago_semanal * Decimal('4.33')
            
            if self.empleado and self.empleado.salario_actual:
                salario_actual = self.empleado.salario_actual
                if salario_actual and salario_actual.sueldo_mensual:
                    sueldo_mensual = salario_actual.sueldo_mensual
                    limite_pago = sueldo_mensual * Decimal('0.4')
                    
                    if pago_mensual_aproximado > limite_pago:
                        pago_semanal_maximo = limite_pago / Decimal('4.33')
                        if pago_semanal_maximo > 0:
                            monto_float = float(monto_decimal)
                            pago_max_float = float(pago_semanal_maximo)
                            plazo_minimo_float = (monto_float / pago_max_float) + 1
                            plazo_minimo_sugerido = int(plazo_minimo_float)
                            plazo_minimo_sugerido = min(plazo_minimo_sugerido, 52)
                            
                            self.add_error(
                                'plazo_semanas',
                                f'El pago semanal sería de ${pago_semanal:,.2f} '
                                f'(equivalente a ${pago_mensual_aproximado:,.2f} mensual). '
                                f'Esto excede el 40% del sueldo (${limite_pago:,.2f}). '
                                f'Recomendación: aumente el plazo a al menos {plazo_minimo_sugerido} semanas.'
                            )
            
            if pago_semanal < Decimal('10'):
                self.add_error(
                    'plazo_semanas',
                    f'El plazo es muy largo. El pago semanal sería de solo ${pago_semanal:,.2f}. '
                    f'Considere un plazo más corto.'
                )
            
            total_interes = (pago_semanal * plazo_decimal) - monto_decimal
            cleaned_data['total_interes'] = round(total_interes, 2)
            
            fecha_primer_pago = cleaned_data.get('fecha_primer_pago')
            if fecha_primer_pago:
                fecha_final_estimada = fecha_primer_pago + timedelta(weeks=int(plazo_semanas))
                cleaned_data['fecha_final_estimada'] = fecha_final_estimada
        
        return cleaned_data
    
    def get_info_calculo(self):
        if self.is_valid():
            data = self.cleaned_data
            info = {
                'pago_semanal': data.get('pago_semanal_calculado', 0),
                'total_interes': data.get('total_interes', 0),
                'fecha_final_estimada': data.get('fecha_final_estimada'),
                'plazo_meses_aproximado': round(data.get('plazo_semanas', 0) / 4.33, 1),
            }
            if info['pago_semanal']:
                info['pago_mensual_aproximado'] = round(info['pago_semanal'] * Decimal('4.33'), 2)
            return info
        return None


class AprobarVacacionForm(forms.ModelForm):
    """Formulario para aprobar/rechazar vacaciones"""
    
    class Meta:
        model = Vacacion
        fields = ['estado', 'observaciones', 'documento_aprobacion']
        widgets = {
            'observaciones': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }


class PagoPrestamoForm(forms.ModelForm):
    """Formulario para registrar pagos de préstamos"""
    
    class Meta:
        model = PagoPrestamo
        fields = ['monto_pagado', 'fecha_pago', 'observaciones', 'comprobante']  # Cambiado a 'fecha_pago'
        widgets = {
            'monto_pagado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'fecha_pago': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),  # Cambiado aquí también
            'observaciones': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'comprobante': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIX FECHAS
        for field_name, field in self.fields.items():
            if isinstance(field, forms.DateField) or isinstance(field.widget, forms.DateInput):
                field.widget.format = '%Y-%m-%d'
                if self.initial.get(field_name):
                    try:
                        self.initial[field_name] = self.initial[field_name].strftime('%Y-%m-%d')
                    except AttributeError:
                        pass

class ControlVacanteForm(forms.ModelForm):
    class Meta:
        model = ControlVacante
        fields = ['empresa', 'puesto', 'division', 'cantidad_presupuestada']
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'puesto': forms.Select(attrs={'class': 'form-select'}),
            'division': forms.Select(attrs={'class': 'form-select'}),
            'cantidad_presupuestada': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
        labels = {
            'cantidad_presupuestada': 'Cantidad Objetivo / Presupuestada',
            'division': 'División Operativa (Opcional)',
        }