# compras/forms.py

from django import forms
from django.forms import inlineformset_factory
from .models import (
    Proveedor, Articulo, ArticuloProveedor, SolicitudCompra, DetalleSolicitud,
    OrdenCompra, DetalleOrdenCompra, Categoria, UnidadMedida
)
from ternium.models import Empresa

# --- Formularios de Catálogos ---

class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            'empresa', 'razon_social', 'rfc', 'direccion', 'contacto_principal',
            'email_contacto', 'telefono_contacto', 'cuentas_bancarias', 'dias_credito', 'activo'
        ]
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
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

class ArticuloForm(forms.ModelForm):
    class Meta:
        model = Articulo
        # --- FIX IS HERE ---
        # Remove 'lleva_retencion_isr' from this list
        fields = [
            'empresa', 'nombre', 'sku', 'descripcion', 'categoria', 'unidad_medida', 'tipo',
            'lleva_iva', 'lleva_retencion_iva', 'activo'
        ]
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'unidad_medida': forms.Select(attrs={'class': 'form-select'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'lleva_iva': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # The widget for the removed field should also be deleted
            # 'lleva_retencion_isr': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'lleva_retencion_iva': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.all().order_by('nombre')
        self.fields['unidad_medida'].queryset = UnidadMedida.objects.all().order_by('nombre')


ArticuloProveedorFormSet = inlineformset_factory(
    Articulo,
    ArticuloProveedor,
    fields=('proveedor', 'precio_unitario'),
    extra=1,
    can_delete=True,
    widgets={
        'proveedor': forms.Select(attrs={'class': 'form-select'}),
        'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    }
)

# --- Formularios del Proceso de Compra ---

class SolicitudCompraForm(forms.ModelForm):
    class Meta:
        model = SolicitudCompra
        fields = ['empresa', 'proveedor', 'motivo', 'prioridad', 'cotizacion']
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select', 'id': 'id_empresa'}),
            'proveedor': forms.Select(attrs={'class': 'form-select', 'id': 'id_proveedor'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'cotizacion': forms.FileInput(attrs={'class': 'form-control'}),
        }

    # --- REEMPLAZA TU MÉTODO __init__ CON ESTE ---
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].queryset = Empresa.objects.all().order_by('nombre')

        # Por defecto, el queryset de proveedores está vacío
        proveedor_queryset = Proveedor.objects.none()

        # CASO 1: Si el formulario está procesando datos enviados (ej. un POST)
        if 'empresa' in self.data:
            try:
                empresa_id = int(self.data.get('empresa'))
                proveedor_queryset = Proveedor.objects.filter(empresa_id=empresa_id).order_by('razon_social')
            except (ValueError, TypeError):
                pass  # El ID de empresa no es válido, se mantiene el queryset vacío
        
        # CASO 2: Si el formulario es para editar una instancia ya existente (carga inicial GET)
        elif self.instance and self.instance.pk:
            proveedor_queryset = Proveedor.objects.filter(empresa=self.instance.empresa).order_by('razon_social')

        # Asignamos el queryset determinado al campo del proveedor
        self.fields['proveedor'].queryset = proveedor_queryset
            
class DetalleSolicitudForm(forms.ModelForm):
    class Meta:
        model = DetalleSolicitud
        fields = ['articulo', 'cantidad', 'precio_unitario']
        widgets = {
            'articulo': forms.Select(attrs={'class': 'form-select articulo-select'}), # Puedes añadir la clase que usas para Select2
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        # Extraemos 'proveedor_id' antes de llamar al constructor padre
        proveedor_id = kwargs.pop('proveedor_id', None)
        super().__init__(*args, **kwargs)
        
        # Si recibimos un proveedor_id, filtramos el queryset de artículos
        if proveedor_id:
            self.fields['articulo'].queryset = Articulo.objects.filter(
                proveedores__id=proveedor_id, activo=True
            ).distinct()
        else:
            # Si no, el queryset está vacío para evitar mostrar artículos incorrectos
            self.fields['articulo'].queryset = Articulo.objects.none()


class OrdenCompraForm(forms.ModelForm):
    class Meta:
        model = OrdenCompra
        fields = ['proveedor', 'fecha_entrega_esperada', 'moneda', 'tipo_cambio', 'condiciones_pago']
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select'}),
            'fecha_entrega_esperada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            
            # --- INICIO DE LA MODIFICACIÓN ---
            'moneda': forms.Select(attrs={'class': 'form-select'}), # Cambiado de TextInput a Select
            # --- FIN DE LA MODIFICACIÓN ---

            'tipo_cambio': forms.NumberInput(attrs={'class': 'form-control'}),
            'condiciones_pago': forms.TextInput(attrs={'class': 'form-control'}),
        }
from .models import Articulo, DetalleOrdenCompra # Asegúrate que Articulo esté importado

class DetalleOrdenCompraForm(forms.ModelForm):
    # --- START OF CORRECTION ---
    """
    Formulario para el detalle de la OC. Ahora el descuento es visible y editable
    para permitir una mayor flexibilidad al generar la orden.
    """
    class Meta:
        model = DetalleOrdenCompra
        fields = ['articulo', 'cantidad', 'precio_unitario', 'descuento']
        widgets = {
            'articulo': forms.HiddenInput(),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control text-center'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control text-end'}),
            # Se cambia el widget para que el descuento sea visible.
            # Se le añaden atributos para el cálculo dinámico en el frontend.
            'descuento': forms.NumberInput(attrs={
                'class': 'form-control text-end descuento-input',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
        }
    # --- END OF CORRECTION ---

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
        # Excluimos la categoría actual de las opciones para ser su propio padre
        if self.instance.pk:
            self.fields['parent'].queryset = Categoria.objects.exclude(pk=self.instance.pk).order_by('nombre')
        else:
            self.fields['parent'].queryset = Categoria.objects.all().order_by('nombre')
    
    def clean_parent(self):
        # CAMBIO: Validación avanzada para evitar dependencias circulares.
        parent = self.cleaned_data.get('parent')
        
        # self.instance es el objeto que se está editando. Si no existe, es un objeto nuevo.
        if parent and self.instance.pk:
            # Re-confirmamos que no sea su propio padre (aunque ya se excluyó del queryset)
            if parent.pk == self.instance.pk:
                raise forms.ValidationError("Una categoría no puede ser su propia categoría padre.")
            
            # Recorremos hacia arriba desde el padre propuesto para asegurarnos de que la
            # categoría actual no esté en su árbol de ancestros.
            p = parent
            while p is not None:
                if p.pk == self.instance.pk:
                    raise forms.ValidationError("No puedes asignar una subcategoría como categoría padre (crearía un bucle).")
                p = p.parent
        return parent
    
class OrdenCompraArchivosForm(forms.ModelForm):
    """
    Formulario dedicado a la gestión de archivos administrativos de la OC.
    """
    class Meta:
        model = OrdenCompra
        fields = ['factura', 'comprobante_pago', 'archivo_opcional']
        widgets = {
            'factura': forms.FileInput(attrs={'class': 'form-control'}),
            'comprobante_pago': forms.FileInput(attrs={'class': 'form-control'}),
            'archivo_opcional': forms.FileInput(attrs={'class': 'form-control'}),
        }