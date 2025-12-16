# compras/forms.py

from django import forms
from django.forms import inlineformset_factory
from .models import (
    Proveedor, Articulo, ArticuloProveedor, SolicitudCompra, DetalleSolicitud,
    OrdenCompra, DetalleOrdenCompra, Categoria, UnidadMedida
)
from ternium.models import Empresa, Origen,Lugar

# --- Formularios de Catálogos ---

class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            'empresa',  # Operación
            'lugar',    # Empresa
            'razon_social', 'rfc', 'direccion', 'contacto_principal',
            'email_contacto', 'telefono_contacto', 'cuentas_bancarias', 
            'dias_credito', 'activo'
        ]
        widgets = {
            # Damos IDs para el JavaScript
            'empresa': forms.Select(attrs={'class': 'form-select', 'id': 'id_operacion'}),
            'lugar': forms.Select(attrs={'class': 'form-select', 'id': 'id_empresa_lugar'}),
            
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control'}),
            'direccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'contacto_principal': forms.TextInput(attrs={'class': 'form-control'}),
            'email_contacto': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono_contacto': forms.TextInput(attrs={'class': 'form-control'}),
            'cuentas_bancarias': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'dias_credito': forms.NumberInput(attrs={'class': 'form-control'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'empresa': 'Operación', # Cambiamos la etiqueta
            'lugar': 'Empresa',     # Nueva etiqueta
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Lógica para el dropdown dinámico
        empresa_queryset = Lugar.objects.none()

        if self.instance and self.instance.pk and self.instance.empresa:
            # Caso 1: Editando un Proveedor existente
            empresa_queryset = Lugar.objects.filter(
                empresas=self.instance.empresa, 
                tipo='ORIGEN'
            ).order_by('nombre')
        
        elif 'empresa' in self.data:
            # Caso 2: El formulario se está enviando (POST)
            try:
                operacion_id = int(self.data.get('empresa'))
                operacion = Empresa.objects.get(pk=operacion_id)
                empresa_queryset = Lugar.objects.filter(
                    empresas=operacion, 
                    tipo='ORIGEN'
                ).order_by('nombre')
            except (ValueError, TypeError, Empresa.DoesNotExist):
                pass 

        self.fields['lugar'].queryset = empresa_queryset

class ArticuloForm(forms.ModelForm):
    class Meta:
        model = Articulo
        # --- CAMPOS ACTIVADOS ---
        fields = [
            'empresa', 
            'origen',
            'nombre', 'sku', 'descripcion', 'categoria', 
            'unidad_medida', 'tipo', 
            'porcentaje_iva',            # <--- NUEVO
            'porcentaje_retencion_iva',  # <--- NUEVO
            'activo'
        ]
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select', 'id': 'id_empresa'}),
            'origen': forms.Select(attrs={'class': 'form-select', 'id': 'id_origen'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'unidad_medida': forms.Select(attrs={'class': 'form-select'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            
            # --- WIDGETS NUEVOS PARA PORCENTAJES ---
            'porcentaje_iva': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': '0', 
                'max': '100', 
                'step': '0.01',
                'placeholder': '16.00'
            }),
            'porcentaje_retencion_iva': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': '0', 
                'max': '100', 
                'step': '0.01',
                'placeholder': '0.00'
            }),
            
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.all().order_by('nombre')
        self.fields['unidad_medida'].queryset = UnidadMedida.objects.all().order_by('nombre')
        
        # Lógica de filtrado para Origen
        origen_queryset = Lugar.objects.none()

        if self.instance and self.instance.pk and self.instance.empresa:
            origen_queryset = Lugar.objects.filter(
                empresas=self.instance.empresa, 
                tipo='ORIGEN'
            ).order_by('nombre')
        elif 'empresa' in self.data:
            try:
                empresa_id = int(self.data.get('empresa'))
                empresa = Empresa.objects.get(pk=empresa_id)
                origen_queryset = Lugar.objects.filter(
                    empresas=empresa, 
                    tipo='ORIGEN'
                ).order_by('nombre')
            except (ValueError, TypeError, Empresa.DoesNotExist):
                pass 
        
        self.fields['origen'].queryset = origen_queryset
        # --- FIN LÓGICA HABILITADA ---     
class ArticuloProveedorForm(forms.ModelForm):
    """Formulario para un solo proveedor de artículo."""
    class Meta:
        model = ArticuloProveedor
        fields = ['proveedor', 'precio_unitario']
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
        }

ArticuloProveedorFormSet = inlineformset_factory(
    Articulo,
    ArticuloProveedor,
    form=ArticuloProveedorForm,
    extra=1, # Empieza con 1 formulario vacío
    can_delete=True,
    fk_name='articulo'
)
# --- FIN DEL CÓDIGO FALTANTE ---


class SolicitudCompraForm(forms.ModelForm):
    class Meta:
        model = SolicitudCompra
        # --- INICIO MODIFICACIÓN ---
        fields = ['empresa', 'lugar', 'proveedor', 'motivo', 'prioridad', 'cotizacion']
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select', 'id': 'id_operacion'}), # ID cambiado
            'lugar': forms.Select(attrs={'class': 'form-select', 'id': 'id_empresa_lugar'}), # Nuevo widget
            'proveedor': forms.Select(attrs={'class': 'form-select', 'id': 'id_proveedor'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'cotizacion': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'empresa': 'Operación', # Etiqueta cambiada
            'lugar': 'Empresa (Lugar de Origen)', # Nueva etiqueta
        }
        # --- FIN MODIFICACIÓN ---

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Renombramos 'empresa' a 'operacion' para claridad
        self.fields['empresa'].queryset = Empresa.objects.all().order_by('nombre')
        
        lugar_queryset = Lugar.objects.none()
        proveedor_queryset = Proveedor.objects.none()

        # Variable para la Operación (ID de la Empresa)
        operacion_id = None

        if self.instance and self.instance.pk and self.instance.empresa:
            # Caso 1: Editando una Solicitud existente
            operacion_id = self.instance.empresa_id
        
        elif 'empresa' in self.data:
            # Caso 2: El formulario se está enviando (POST)
            try:
                operacion_id = int(self.data.get('empresa'))
            except (ValueError, TypeError):
                pass 

        if operacion_id:
            try:
                operacion = Empresa.objects.get(pk=operacion_id)
                # Filtra los Lugares (Empresas)
                lugar_queryset = Lugar.objects.filter(
                    empresas=operacion, 
                    tipo='ORIGEN'
                ).order_by('nombre')
                
                # Filtra los Proveedores (basado en la Operación)
                proveedor_queryset = Proveedor.objects.filter(
                    empresa_id=operacion_id, 
                    activo=True
                ).order_by('razon_social')
                
            except Empresa.DoesNotExist:
                pass

        self.fields['lugar'].queryset = lugar_queryset
        self.fields['proveedor'].queryset = proveedor_queryset
            
class DetalleSolicitudForm(forms.ModelForm):
    class Meta:
        model = DetalleSolicitud
        fields = ['articulo', 'cantidad', 'precio_unitario']
        widgets = {
            'articulo': forms.Select(attrs={'class': 'form-select articulo-select'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        proveedor_id = kwargs.pop('proveedor_id', None)
        super().__init__(*args, **kwargs)
        if proveedor_id:
            self.fields['articulo'].queryset = Articulo.objects.filter(
                proveedores__id=proveedor_id, activo=True
            ).distinct()
        else:
            self.fields['articulo'].queryset = Articulo.objects.none()


class OrdenCompraForm(forms.ModelForm):
    class Meta:
        model = OrdenCompra
        fields = ['proveedor', 'fecha_entrega_esperada', 'moneda', 'tipo_cambio', 'condiciones_pago', 'modalidad_pago', 'cantidad_plazos']
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select'}),
            'fecha_entrega_esperada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'moneda': forms.Select(attrs={'class': 'form-select'}),
            'tipo_cambio': forms.NumberInput(attrs={'class': 'form-control'}),
            'condiciones_pago': forms.TextInput(attrs={'class': 'form-control'}),
            # --- NUEVOS WIDGETS ---
            'modalidad_pago': forms.Select(attrs={'class': 'form-select'}),
            'cantidad_plazos': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': '1', 
                'placeholder': 'Ej: 3'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        modalidad = cleaned_data.get('modalidad_pago')
        plazos = cleaned_data.get('cantidad_plazos')
        
        if modalidad == 'A_PLAZOS' and not plazos:
            raise forms.ValidationError("Debes especificar la cantidad de plazos si el pago es a plazos.")
        
        return cleaned_data

class DetalleOrdenCompraForm(forms.ModelForm):
    class Meta:
        model = DetalleOrdenCompra
        fields = ['articulo', 'cantidad', 'precio_unitario', 'descuento']
        widgets = {
            'articulo': forms.HiddenInput(),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control text-center'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control text-end'}),
            'descuento': forms.NumberInput(attrs={
                'class': 'form-control text-end descuento-input',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
        }

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nombre', 'parent']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'nombre': 'Nombre de la Categoría',
            'parent': 'Categoría Padre (Opcional, para crear una subcategoría)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].required = False
        if self.instance.pk:
            self.fields['parent'].queryset = Categoria.objects.exclude(pk=self.instance.pk).order_by('nombre')
        else:
            self.fields['parent'].queryset = Categoria.objects.all().order_by('nombre')
    
    def clean_parent(self):
        parent = self.cleaned_data.get('parent')
        if parent and self.instance.pk:
            if parent.pk == self.instance.pk:
                raise forms.ValidationError("Una categoría no puede ser su propia categoría padre.")
            p = parent
            while p is not None:
                if p.pk == self.instance.pk:
                    raise forms.ValidationError("No puedes asignar una subcategoría como categoría padre (crearía un bucle).")
                p = p.parent
        return parent
    
class OrdenCompraArchivosForm(forms.ModelForm):
    class Meta:
        model = OrdenCompra
        fields = ['factura', 'comprobante_pago', 'archivo_opcional']
        widgets = {
            'factura': forms.FileInput(attrs={'class': 'form-control'}),
            'comprobante_pago': forms.FileInput(attrs={'class': 'form-control'}),
            'archivo_opcional': forms.FileInput(attrs={'class': 'form-control'}),
        }
        
class EmpresaOrigenesForm(forms.ModelForm):
    """
    Este formulario se usa para editar una Empresa
    y asignar sus Orígenes.
    """
    class Meta:
        model = Empresa
        # Solo nos interesa mostrar el campo ManyToMany
        fields = ['origenes'] 
        
        widgets = {
            # Usamos CheckboxSelectMultiple para que sea más fácil de usar
            'origenes': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Nos aseguramos de que el campo muestre todos los orígenes disponibles
        self.fields['origenes'].queryset = Origen.objects.all().order_by('nombre')
        self.fields['origenes'].label = "Orígenes Vinculados a esta Empresa"
        self.fields['origenes'].help_text = "Selecciona todos los orígenes que esta empresa puede usar."