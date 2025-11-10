# compras/forms.py

from django import forms
from django.forms import inlineformset_factory
from .models import (
    Proveedor, Articulo, ArticuloProveedor, SolicitudCompra, DetalleSolicitud,
    OrdenCompra, DetalleOrdenCompra, Categoria, UnidadMedida
)
<<<<<<< HEAD
from ternium.models import Empresa, Origen,Lugar
=======
from ternium.models import Empresa
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b

# --- Formularios de Catálogos ---

class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
<<<<<<< HEAD
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
            
=======
            'empresa', 'razon_social', 'rfc', 'direccion', 'contacto_principal',
            'email_contacto', 'telefono_contacto', 'cuentas_bancarias', 'dias_credito', 'activo'
        ]
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
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
<<<<<<< HEAD
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
=======
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b

class ArticuloForm(forms.ModelForm):
    class Meta:
        model = Articulo
<<<<<<< HEAD
        # --- CAMPOS ACTIVADOS ---
        fields = [
            'empresa', 
            'origen',  # <--- HABILITADO
            'nombre', 'sku', 'descripcion', 'categoria', 
            'unidad_medida', 'tipo', 'lleva_iva', 'lleva_retencion_iva', 'activo'
        ]
        widgets = {
            # --- IDs HABILITADOS ---
            'empresa': forms.Select(attrs={'class': 'form-select', 'id': 'id_empresa'}),
            'origen': forms.Select(attrs={'class': 'form-select', 'id': 'id_origen'}), # <--- HABILITADO
            
=======
        # --- FIX IS HERE ---
        # Remove 'lleva_retencion_isr' from this list
        fields = [
            'empresa', 'nombre', 'sku', 'descripcion', 'categoria', 'unidad_medida', 'tipo',
            'lleva_iva', 'lleva_retencion_iva', 'activo'
        ]
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'unidad_medida': forms.Select(attrs={'class': 'form-select'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'lleva_iva': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
<<<<<<< HEAD
=======
            # The widget for the removed field should also be deleted
            # 'lleva_retencion_isr': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
            'lleva_retencion_iva': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.all().order_by('nombre')
        self.fields['unidad_medida'].queryset = UnidadMedida.objects.all().order_by('nombre')

<<<<<<< HEAD
        # --- ¡INICIO DE LA LÓGICA MODIFICADA! ---
        
        # El queryset ahora debe ser del modelo 'Lugar'
        origen_queryset = Lugar.objects.none() # Iniciar vacío por defecto

        if self.instance and self.instance.pk and self.instance.empresa:
            # Caso 1: Editando un artículo que YA tiene una empresa
            # (Usamos la misma lógica de la API)
            origen_queryset = Lugar.objects.filter(
                empresas=self.instance.empresa, 
                tipo='ORIGEN'
            ).order_by('nombre')
        
        elif 'empresa' in self.data:
            # Caso 2: El formulario se está enviando (POST)
            try:
                empresa_id = int(self.data.get('empresa'))
                empresa = Empresa.objects.get(pk=empresa_id)
                
                # (Usamos la misma lógica de la API)
                origen_queryset = Lugar.objects.filter(
                    empresas=empresa, 
                    tipo='ORIGEN'
                ).order_by('nombre')
                
            except (ValueError, TypeError, Empresa.DoesNotExist):
                pass # Mantener vacío si hay un error
        
        # Asignamos el queryset filtrado (de Lugares) al campo 'origen'
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
=======
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b

ArticuloProveedorFormSet = inlineformset_factory(
    Articulo,
    ArticuloProveedor,
<<<<<<< HEAD
    form=ArticuloProveedorForm,
    extra=1, # Empieza con 1 formulario vacío
    can_delete=True,
    fk_name='articulo'
)
# --- FIN DEL CÓDIGO FALTANTE ---

=======
    fields=('proveedor', 'precio_unitario'),
    extra=1,
    can_delete=True,
    widgets={
        'proveedor': forms.Select(attrs={'class': 'form-select'}),
        'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    }
)

# --- Formularios del Proceso de Compra ---
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b

class SolicitudCompraForm(forms.ModelForm):
    class Meta:
        model = SolicitudCompra
<<<<<<< HEAD
        # --- INICIO MODIFICACIÓN ---
        fields = ['empresa', 'lugar', 'proveedor', 'motivo', 'prioridad', 'cotizacion']
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select', 'id': 'id_operacion'}), # ID cambiado
            'lugar': forms.Select(attrs={'class': 'form-select', 'id': 'id_empresa_lugar'}), # Nuevo widget
=======
        fields = ['empresa', 'proveedor', 'motivo', 'prioridad', 'cotizacion']
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select', 'id': 'id_empresa'}),
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
            'proveedor': forms.Select(attrs={'class': 'form-select', 'id': 'id_proveedor'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'cotizacion': forms.FileInput(attrs={'class': 'form-control'}),
        }
<<<<<<< HEAD
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
=======

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
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
        self.fields['proveedor'].queryset = proveedor_queryset
            
class DetalleSolicitudForm(forms.ModelForm):
    class Meta:
        model = DetalleSolicitud
        fields = ['articulo', 'cantidad', 'precio_unitario']
        widgets = {
<<<<<<< HEAD
            'articulo': forms.Select(attrs={'class': 'form-select articulo-select'}),
=======
            'articulo': forms.Select(attrs={'class': 'form-select articulo-select'}), # Puedes añadir la clase que usas para Select2
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
<<<<<<< HEAD
        proveedor_id = kwargs.pop('proveedor_id', None)
        super().__init__(*args, **kwargs)
=======
        # Extraemos 'proveedor_id' antes de llamar al constructor padre
        proveedor_id = kwargs.pop('proveedor_id', None)
        super().__init__(*args, **kwargs)
        
        # Si recibimos un proveedor_id, filtramos el queryset de artículos
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
        if proveedor_id:
            self.fields['articulo'].queryset = Articulo.objects.filter(
                proveedores__id=proveedor_id, activo=True
            ).distinct()
        else:
<<<<<<< HEAD
=======
            # Si no, el queryset está vacío para evitar mostrar artículos incorrectos
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
            self.fields['articulo'].queryset = Articulo.objects.none()


class OrdenCompraForm(forms.ModelForm):
    class Meta:
        model = OrdenCompra
<<<<<<< HEAD
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
=======
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
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
    class Meta:
        model = DetalleOrdenCompra
        fields = ['articulo', 'cantidad', 'precio_unitario', 'descuento']
        widgets = {
            'articulo': forms.HiddenInput(),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control text-center'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control text-end'}),
<<<<<<< HEAD
=======
            # Se cambia el widget para que el descuento sea visible.
            # Se le añaden atributos para el cálculo dinámico en el frontend.
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
            'descuento': forms.NumberInput(attrs={
                'class': 'form-control text-end descuento-input',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
        }
<<<<<<< HEAD
=======
    # --- END OF CORRECTION ---
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b

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
<<<<<<< HEAD
=======
        # Excluimos la categoría actual de las opciones para ser su propio padre
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
        if self.instance.pk:
            self.fields['parent'].queryset = Categoria.objects.exclude(pk=self.instance.pk).order_by('nombre')
        else:
            self.fields['parent'].queryset = Categoria.objects.all().order_by('nombre')
    
    def clean_parent(self):
<<<<<<< HEAD
        parent = self.cleaned_data.get('parent')
        if parent and self.instance.pk:
            if parent.pk == self.instance.pk:
                raise forms.ValidationError("Una categoría no puede ser su propia categoría padre.")
=======
        # CAMBIO: Validación avanzada para evitar dependencias circulares.
        parent = self.cleaned_data.get('parent')
        
        # self.instance es el objeto que se está editando. Si no existe, es un objeto nuevo.
        if parent and self.instance.pk:
            # Re-confirmamos que no sea su propio padre (aunque ya se excluyó del queryset)
            if parent.pk == self.instance.pk:
                raise forms.ValidationError("Una categoría no puede ser su propia categoría padre.")
            
            # Recorremos hacia arriba desde el padre propuesto para asegurarnos de que la
            # categoría actual no esté en su árbol de ancestros.
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
            p = parent
            while p is not None:
                if p.pk == self.instance.pk:
                    raise forms.ValidationError("No puedes asignar una subcategoría como categoría padre (crearía un bucle).")
                p = p.parent
        return parent
    
class OrdenCompraArchivosForm(forms.ModelForm):
<<<<<<< HEAD
=======
    """
    Formulario dedicado a la gestión de archivos administrativos de la OC.
    """
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
    class Meta:
        model = OrdenCompra
        fields = ['factura', 'comprobante_pago', 'archivo_opcional']
        widgets = {
            'factura': forms.FileInput(attrs={'class': 'form-control'}),
            'comprobante_pago': forms.FileInput(attrs={'class': 'form-control'}),
            'archivo_opcional': forms.FileInput(attrs={'class': 'form-control'}),
<<<<<<< HEAD
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
=======
        }
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
