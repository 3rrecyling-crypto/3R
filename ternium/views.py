# ternium/views.py

import io
import os
import zipfile
import datetime
import decimal
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.styles import Alignment, PatternFill
from openpyxl.utils import get_column_letter
from django.db.models import Q, Sum, F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View, DeleteView
from django.core.files.storage import default_storage
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.forms import inlineformset_factory
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
import datetime
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from django.db.models import Max # <-- Añadir esta importación
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

# === IMPORTS ADICIONALES PARA CARGA MANUAL A S3 ===
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
from django.conf import settings
# ===================================================

from .models import (
    Empresa, Lugar, Remision, EntradaMaquila, LineaTransporte,
    Operador, Material, Unidad, Contenedor, DetalleRemision,
    InventarioPatio, Descarga, RegistroLogistico
)
from .forms import (
    EmpresaForm, LugarForm, RemisionForm, DetalleRemisionForm,
    EntradaMaquilaForm, LineaTransporteForm, OperadorForm,
    MaterialForm, UnidadForm, ContenedorForm, DescargaForm,
    RegistroLogisticoForm
)
from .models import Lugar, Empresa, Origen # <-- ¡Asegúrate de que Empresa esté importada!
from .forms import LugarForm, EmpresaOrigenesForm # <-- ¡Importa el nuevo form!
from django.contrib.auth.mixins import LoginRequiredMixin
# ==============================================================================
# === NUEVAS FUNCIONES AUXILIARES PARA GESTIONAR ARCHIVOS EN S3 MANUALMENTE ===
# ==============================================================================

def _subir_archivo_a_s3(archivo_obj, s3_ruta_relativa):
    """
    Sube un archivo a S3.
    - `s3_ruta_relativa` es la ruta SIN 'media/' (ej: 'entradas_maquila/remito/foto.jpg').
    - Devuelve la misma ruta relativa si tiene éxito, para guardarla en la DB.
    """
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # Boto3 necesita la ruta completa (Key) dentro del bucket
        full_s3_path = f"{settings.AWS_MEDIA_LOCATION}/{s3_ruta_relativa}"

        s3_client.upload_fileobj(
            archivo_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            full_s3_path
        )
        return s3_ruta_relativa
        
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al subir el archivo a S3: {e}")
        return None

def _eliminar_archivo_de_s3(ruta_completa_s3):
    """
    Elimina un archivo de S3.
    - `ruta_completa_s3` es la ruta que Django provee (ej: 'media/entradas/foto.jpg'),
      que es lo que Boto3 necesita como 'Key'.
    """
    if not ruta_completa_s3:
        return
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=str(ruta_completa_s3)
        )
    except (BotoCoreError, NoCredentialsError, Exception) as e:
        print(f"Error al eliminar archivo antiguo de S3: {e}")
        
def _update_inventory_from_remision(remision, revert=False):
    """
    Ajusta el inventario en los patios basado en una remisión.
    """
    TON_TO_KG = decimal.Decimal('1000.0')

    if remision.origen and remision.origen.es_patio:
        for detalle in remision.detalles.all():
            if detalle.peso_ld > 0:
                inventario, _ = InventarioPatio.objects.get_or_create(
                    patio=remision.origen, material=detalle.material
                )
                cantidad_kg = detalle.peso_ld * TON_TO_KG
                current_inventory = decimal.Decimal(inventario.cantidad)
                new_inventory = current_inventory - cantidad_kg if not revert else current_inventory + cantidad_kg
                inventario.cantidad = new_inventory
                inventario.save()

    if remision.destino and remision.destino.es_patio:
        for detalle in remision.detalles.all():
            if detalle.peso_dlv > 0:
                inventario, _ = InventarioPatio.objects.get_or_create(
                    patio=remision.destino, material=detalle.material
                )
                cantidad_kg = detalle.peso_dlv * TON_TO_KG
                current_inventory = decimal.Decimal(inventario.cantidad)
                new_inventory = current_inventory + cantidad_kg if not revert else current_inventory - cantidad_kg
                inventario.cantidad = new_inventory
                inventario.save()


@login_required
def home(request):
    total_entradas = EntradaMaquila.objects.count()
    total_alertas = EntradaMaquila.objects.filter(alerta=True).count()
    total_registros_logistica = RegistroLogistico.objects.count()
    
    patios_activos = Lugar.objects.filter(es_patio=True).order_by('nombre')
    patios_data = []
    
    KG_TO_TON = decimal.Decimal('1000.0')

    for patio in patios_activos:
        inventario_kg = InventarioPatio.objects.filter(
            patio=patio, cantidad__gt=0
        ).select_related('material').order_by('material__nombre')
        
        total_kg = inventario_kg.aggregate(total=Sum('cantidad'))['total'] or 0
        total_toneladas = decimal.Decimal(total_kg) / KG_TO_TON
        
        materiales_en_toneladas = [{
            'material_nombre': item.material.nombre,
            'cantidad_toneladas': item.cantidad / KG_TO_TON
        } for item in inventario_kg]

        ultima_actualizacion_obj = InventarioPatio.objects.filter(patio=patio).order_by('-ultima_actualizacion').first()

        patios_data.append({
            'nombre': patio.nombre,
            'materiales': materiales_en_toneladas,
            'total_toneladas': total_toneladas,
            'ultima_actualizacion': ultima_actualizacion_obj.ultima_actualizacion if ultima_actualizacion_obj else None,
        })

    context = {
        'total_entradas': total_entradas,
        'total_alertas': total_alertas,
        'patios_inventario': patios_data,
        'total_registros_logistica': total_registros_logistica,
    }
    return render(request, 'ternium/home.html', context)


@login_required
@permission_required('ternium.view_ternium_module', raise_exception=True)
def home_portal_view(request):
    return render(request, 'ternium/home_portal.html')


# --- VISTAS DE ENTRADA MAQUILA ---
@method_decorator(login_required, name='dispatch')
class EntradaMaquilaListView(PermissionRequiredMixin, ListView):
    permission_required = 'ternium.view_ternium_module' 
    model = EntradaMaquila
    template_name = 'ternium/lista_entradas.html'
    context_object_name = 'entradas'
    paginate_by = 10
    ordering = ['-fecha_ingreso', '-creado_en']


@login_required
def detalle_entrada(request, pk):
    entrada = get_object_or_404(EntradaMaquila, pk=pk)
    return render(request, 'ternium/detalle_entrada.html', {'entrada': entrada})

from .models import EntradaMaquila
from .forms import EntradaMaquilaForm
@login_required
def crear_entrada(request):
    if request.method == 'POST':
        form = EntradaMaquilaForm(request.POST, request.FILES)
        if form.is_valid():
            # Paso 1: Guardar el formulario sin commit para tener un objeto en memoria
            entrada = form.save(commit=False)
            remito_id = form.cleaned_data.get('c_id_remito', 'sin_remito').strip()

            # Paso 2: Definir los campos de archivo y sus sufijos de nombre
            archivos_a_subir = {
                'foto_frontal': '1', 'foto_superior_cargada': '2', 'foto_trasera': '3',
                'foto_superior_vacia': '4', 'documento_remision_clientes': '5'
            }

            # Paso 3: Iterar y subir cada archivo manualmente
            for campo, sufijo in archivos_a_subir.items():
                if campo in request.FILES:
                    archivo = request.FILES[campo]
                    _nombre_base, extension = os.path.splitext(archivo.name)
                    # Construir la ruta relativa que se guardará en la DB
                    s3_path = f"entradas_maquila/{remito_id}/{remito_id}-{sufijo}{extension}"
                    
                    ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
                    if ruta_guardada:
                        # Asignar la ruta guardada al campo del modelo
                        setattr(entrada, campo, ruta_guardada)
                    else:
                        messages.error(request, f"No se pudo subir el archivo para '{campo}'.")
                        # Si un archivo falla, es mejor no guardar nada
                        return render(request, 'ternium/formulario_entrada.html', {'form': form, 'titulo': 'Nuevo Registro de Entrada'})

            # Paso 4: Guardar el objeto en la base de datos con las rutas de los archivos ya asignadas
            entrada.save()
            messages.success(request, 'Entrada registrada y archivos subidos exitosamente.')
            return redirect('detalle_entrada', pk=entrada.pk)
    else:
        form = EntradaMaquilaForm()
        
    context = {'form': form, 'titulo': 'Nuevo Registro de Entrada'}
    return render(request, 'ternium/formulario_entrada.html', context)

@login_required
def editar_entrada(request, pk):
    entrada_original = get_object_or_404(EntradaMaquila, pk=pk)
    
    if request.method == 'POST':
        form = EntradaMaquilaForm(request.POST, request.FILES, instance=entrada_original)
        if form.is_valid():
            entrada = form.save(commit=False)
            remito_id = form.cleaned_data.get('c_id_remito', 'sin_remito').strip()

            archivos_a_subir = {
                'foto_frontal': '1', 'foto_superior_cargada': '2', 'foto_trasera': '3',
                'foto_superior_vacia': '4', 'documento_remision_clientes': '5'
            }

            for campo, sufijo in archivos_a_subir.items():
                if campo in request.FILES:
                    # 1. Eliminar el archivo antiguo ANTES de subir el nuevo
                    ruta_antigua = getattr(entrada_original, campo)
                    if ruta_antigua and hasattr(ruta_antigua, 'name'):
                        _eliminar_archivo_de_s3(ruta_antigua.name)

                    # 2. Subir el archivo nuevo
                    archivo = request.FILES[campo]
                    _nombre_base, extension = os.path.splitext(archivo.name)
                    s3_path = f"entradas_maquila/{remito_id}/{remito_id}-{sufijo}{extension}"
                    
                    ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
                    if ruta_guardada:
                        setattr(entrada, campo, ruta_guardada)
                    else:
                        messages.error(request, f"No se pudo actualizar el archivo para '{campo}'.")
                        # Re-renderizar el formulario con el error
                        context = {'form': form, 'object': entrada_original, 'titulo': f'Editar Entrada: {remito_id}'}
                        return render(request, 'ternium/formulario_entrada.html', context)

            entrada.save()
            messages.success(request, 'Entrada actualizada correctamente.')
            return redirect('detalle_entrada', pk=entrada.pk)
    else:
        form = EntradaMaquilaForm(instance=entrada_original)

    context = {
        'form': form, 'object': entrada_original, 'titulo': f'Editar Entrada: {entrada_original.c_id_remito}'
    }
    return render(request, 'ternium/formulario_entrada.html', context)


@login_required
@require_POST # Asegura que esta vista solo acepte peticiones POST por seguridad
def eliminar_entrada(request, pk):
    """
    Vista para eliminar una EntradaMaquila.
    El borrado de archivos en S3 se maneja automáticamente por la señal post_delete.
    """
    entrada = get_object_or_404(EntradaMaquila, pk=pk)
    
    if entrada.status == 'AUDITADO':
        messages.error(request, "No se puede eliminar una entrada que ya ha sido auditada.")
    else:
        # Al hacer .delete(), la señal que ya tienes se activará 
        # y borrará los archivos de S3 automáticamente.
        entrada.delete()
        messages.success(request, 'La entrada ha sido eliminada exitosamente.')
        
    return redirect('lista_entradas')


@login_required
@require_POST
def auditar_entrada(request, pk):
    entrada = get_object_or_404(EntradaMaquila, pk=pk)
    if entrada.status != 'TERMINADO':
        messages.error(request, 'Esta entrada no cumple los requisitos para ser auditada.')
    else:
        entrada.status = 'AUDITADO'
        entrada.auditado_por = request.user
        entrada.auditado_en = timezone.now()
        entrada.save(update_fields=['status', 'auditado_por', 'auditado_en'])
        messages.success(request, f'La entrada {entrada.c_id_remito} ha sido auditada.')
    return redirect('detalle_entrada', pk=pk)


@login_required
def export_entradas_to_excel(request):
    # Crear libro y hoja
    wb = Workbook()
    ws = wb.active
    ws.title = "Entradas Maquila"
    
    # Encabezados
    headers = [
        "ID", "C_ID_REMITO", "PESO-REMISION", "Num Boleta/Remision Bascula", "Peso Tara", 
        "Peso Bruto", "Peso Neto", "Fecha de Ingreso", "Calidad", "Dif Ton", 
        "TRANSPORTE", "FECHA ENTREGA A TERNIUM"
    ]
    ws.append(headers)
    
    # Obtener y escribir datos
    entradas = EntradaMaquila.objects.all().order_by('-fecha_ingreso')
    
    for entrada in entradas:
        ws.append([
            entrada.id, 
            entrada.c_id_remito, 
            entrada.peso_remision, 
            entrada.num_boleta_remision,
            entrada.peso_tara, 
            entrada.peso_bruto, 
            entrada.peso_neto, 
            entrada.fecha_ingreso,
            entrada.calidad, 
            entrada.diferencia_toneladas, 
            entrada.transporte, 
            entrada.fecha_entrega_ternium
        ])

    # --- NUEVA LÓGICA DE FORMATO ---
    
    # 1. Crear la Tabla de Excel (Formato General)
    # Definimos el rango: A1 hasta la última columna y fila
    last_col_letter = get_column_letter(len(headers))
    last_row = ws.max_row
    # Validamos que haya datos para crear la tabla
    if last_row >= 1:
        table_ref = f"A1:{last_col_letter}{last_row}"
        
        tabla = Table(displayName="TablaEntradasMaquila", ref=table_ref)
        
        # Estilo azul estándar
        style = TableStyleInfo(
            name="TableStyleMedium9", 
            showFirstColumn=False,
            showLastColumn=False, 
            showRowStripes=True, 
            showColumnStripes=False
        )
        tabla.tableStyleInfo = style
        ws.add_table(tabla)

    # 2. Centrar contenido y 3. Ajustar ancho de columnas
    center_alignment = Alignment(horizontal='center', vertical='center')
    
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter # Letra de la columna (A, B, C...)
        
        for cell in col:
            # Aplicar centrado a cada celda
            cell.alignment = center_alignment
            
            # Calcular longitud máxima para el autoajuste
            try:
                if cell.value:
                    length = len(str(cell.value))
                    if length > max_length:
                        max_length = length
            except:
                pass
        
        # Ajustar ancho (sumamos un extra para espacio visual)
        adjusted_width = (max_length + 4)
        ws.column_dimensions[column].width = adjusted_width

    # Generar respuesta
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Entradas_Maquila_{datetime.date.today()}.xlsx"'
    wb.save(response)
    return response


@method_decorator(login_required, name='dispatch')
class DescargarZipMaquilaView(View):
    """
    Vista CORREGIDA para descargar un ZIP con todos los archivos de una EntradaMaquila.
    Usa boto3 para descargar explícitamente cada archivo desde S3.
    """
    def get(self, request, *args, **kwargs):
        entrada = get_object_or_404(EntradaMaquila, pk=self.kwargs['pk'])
        
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
        except (BotoCoreError, NoCredentialsError) as e:
            messages.error(request, f"Error de configuración con S3: {e}")
            return redirect('detalle_entrada', pk=entrada.pk)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            file_fields = [
                'foto_frontal', 'foto_superior_cargada', 'foto_trasera',
                'foto_superior_vacia', 'documento_remision_clientes'
            ]
            
            archivos_agregados = 0
            for field_name in file_fields:
                file_field = getattr(entrada, field_name)
                # Nos aseguramos que el campo tenga un nombre de archivo guardado
                if file_field and file_field.name:
                    # La ruta completa en S3 (la "Key") incluye el prefijo 'media/'
                    s3_key = f"{settings.AWS_MEDIA_LOCATION}/{file_field.name}"
                    file_content_buffer = io.BytesIO()
                    
                    try:
                        # Descargamos el archivo desde S3 a un buffer en memoria
                        s3_client.download_fileobj(settings.AWS_STORAGE_BUCKET_NAME, s3_key, file_content_buffer)
                        file_content_buffer.seek(0) # Rebobinamos el buffer para leerlo
                        
                        # Usamos el nombre base del archivo para guardarlo en el ZIP
                        filename_in_zip = os.path.basename(file_field.name)
                        zip_file.writestr(filename_in_zip, file_content_buffer.read())
                        archivos_agregados += 1
                    except s3_client.exceptions.ClientError as e:
                        if e.response['Error']['Code'] == '404':
                            print(f"Advertencia: El archivo {s3_key} no fue encontrado en S3 para la entrada {entrada.c_id_remito}.")
                        else:
                            messages.error(request, f"No se pudo descargar el archivo '{s3_key}' de S3.")

        if archivos_agregados == 0:
            messages.warning(request, "No se encontraron archivos en S3 para descargar en este registro.")
            return redirect('detalle_entrada', pk=entrada.pk)

        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="ENTRADA-{entrada.c_id_remito}.zip"'
        return response


# --- VISTAS DE REMISIONES ---

@method_decorator(login_required, name='dispatch')
class RemisionListView(ListView):
    model = Remision
    template_name = 'ternium/remision_lista.html'
    context_object_name = 'remisiones'
    paginate_by = 15
    
    def get_queryset(self):
        queryset = Remision.objects.select_related(
            'empresa', 'origen', 'destino'
        ).prefetch_related(
            'detalles__material'
        ).order_by('-fecha', '-creado_en')
        
        search_params = self.request.GET
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Filtros actualizados según tu solicitud.
        filters = {
            'remision__icontains': search_params.get('q_remision'),     # Filtro por N° Remisión
            'empresa__prefijo__icontains': search_params.get('q_prefijo'), # Filtro por Prefijo (Operación)
            'detalles__material_id': search_params.get('q_material'),  # Filtro por Material
            'origen_id': search_params.get('q_origen'),                  # Filtro por Origen
            'destino_id': search_params.get('q_destino'),                # Filtro por Destino
            'status': search_params.get('q_status'),                   # Filtro por Estatus
            'fecha__gte': search_params.get('q_fecha_desde'),
            'fecha__lte': search_params.get('q_fecha_hasta'),
        }
        # --- FIN DE LA MODIFICACIÓN ---
        
        for key, value in filters.items():
            if value:
                queryset = queryset.filter(**{key: value})
                
        if filters.get('detalles__material_id'):
            queryset = queryset.distinct()
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_params'] = self.request.GET
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se cambia 'empresas' por 'prefijos'
        context['prefijos'] = Empresa.objects.exclude(prefijo__isnull=True).exclude(prefijo='').values_list('prefijo', flat=True).distinct().order_by('prefijo')
        # --- FIN DE LA MODIFICACIÓN ---
        context['materiales'] = Material.objects.all().order_by('nombre')
        context['origenes'] = Lugar.objects.filter(tipo__in=['ORIGEN', 'AMBOS']).order_by('nombre')
        context['destinos'] = Lugar.objects.filter(tipo__in=['DESTINO', 'AMBOS']).order_by('nombre')
        context['estatus_choices'] = Remision.STATUS_CHOICES
        context['all_remision_numbers'] = Remision.objects.values_list('remision', flat=True).distinct().order_by('remision')
        return context
    
@login_required
def get_next_remision_number(request, empresa_id):
    """
    Genera el siguiente número de remisión basado en el prefijo
    definido en el modelo Empresa.
    """
    try:
        empresa = Empresa.objects.get(pk=empresa_id)
        
        # Nueva lógica: Obtener el prefijo del modelo
        prefix = empresa.prefijo
        
        if prefix:
            # Aseguramos que el prefijo termine con guión para la búsqueda
            prefix_with_dash = f"{prefix.strip().upper()}-"

            # Buscar la última remisión que COMIENCE con este prefijo
            last_remision = Remision.objects.filter(
                remision__startswith=prefix_with_dash
            ).aggregate(
                max_remision=Max('remision')
            )['max_remision']
            
            next_num = 1 # Por defecto, empezamos en 1
            
            if last_remision:
                # Extraer el número, convertir a int, sumar 1
                try:
                    # Intentar obtener el número después del último guión
                    last_num_str = last_remision.split('-')[-1]
                    last_num = int(last_num_str)
                    next_num = last_num + 1
                except (ValueError, IndexError):
                    # Fallback si hay un formato inesperado (ej. "MTY-ABC")
                    # En este caso, simplemente usa 1
                    next_num = 1 
            
            # Formatear el número con 3 ceros a la izquierda (ej: MTY-001)
            next_remision_str = f"{prefix_with_dash}{str(next_num).zfill(3)}"
            
            return JsonResponse({'next_remision': next_remision_str, 'is_manual': False})
        else:
            # Si la empresa no tiene prefijo, el campo es manual
            return JsonResponse({'is_manual': True})

    except Empresa.DoesNotExist:
        return JsonResponse({'error': 'Empresa no encontrada'}, status=404)




@login_required
def crear_remision(request):
    DetalleFormSet = inlineformset_factory(
        Remision, DetalleRemision, form=DetalleRemisionForm, extra=1, can_delete=True
    )
    empresa_seleccionada = None

    if request.method == 'POST':
        empresa_id = request.POST.get('empresa')
        if empresa_id:
            try:
                empresa_seleccionada = Empresa.objects.get(pk=empresa_id)
            except (Empresa.DoesNotExist, ValueError):
                pass
        
        # Le pasamos la 'empresa' al RemisionForm para una validación correcta
        # 'remision' ya no está en el form, así que no se valida aquí.
        form = RemisionForm(request.POST, request.FILES, empresa=empresa_seleccionada)
        
        material_qs = Material.objects.filter(empresas=empresa_seleccionada) if empresa_seleccionada else Material.objects.none()
        lugar_qs = Lugar.objects.filter(empresas=empresa_seleccionada, tipo__in=['DESTINO', 'AMBOS']) if empresa_seleccionada else Lugar.objects.none()

        formset = DetalleFormSet(
            request.POST, 
            prefix='detalles', 
            form_kwargs={'material_queryset': material_qs, 'lugar_queryset': lugar_qs}
        )

        if form.is_valid() and formset.is_valid():
            try:
                # --- INICIO DE LA LÓGICA DE GUARDADO SEGURO ---
                with transaction.atomic(): 
                    remision = form.save(commit=False) # Objeto en memoria
                    
                    if not empresa_seleccionada or not empresa_seleccionada.prefijo:
                        messages.error(request, 'La empresa seleccionada no tiene un prefijo configurado.')
                        # Usamos una excepción para detener la transacción
                        raise ValidationError("Empresa sin prefijo.")

                    prefix_with_dash = f"{empresa_seleccionada.prefijo.strip().upper()}-"
                    
                    # 1. Bloquea la tabla (o filas) para evitar "race conditions"
                    last_remision_data = Remision.objects.select_for_update().filter(
                        remision__startswith=prefix_with_dash
                    ).aggregate(
                        max_remision=Max('remision')
                    )
                    last_remision = last_remision_data['max_remision']
                    
                    # 2. Calcula el siguiente número de forma segura
                    next_num = 1
                    if last_remision:
                        try:
                            last_num_str = last_remision.split('-')[-1]
                            last_num = int(last_num_str)
                            next_num = last_num + 1
                        except (ValueError, IndexError):
                            next_num = 1 # Fallback si hay un formato inesperado
                    
                    # 3. Asigna el folio consecutivo y seguro
                    remision.remision = f"{prefix_with_dash}{str(next_num).zfill(3)}"
                    
                    # 4. Guarda el objeto principal en la BD con el folio ya asignado
                    remision.save() 
                    
                    # 5. Asigna la instancia al formset y guarda los detalles
                    formset.instance = remision
                    formset.save()
                    
                    # 6. Llama al save() final de la remisión (para la lógica de estatus)
                    remision.save()
                    
                    # 7. Actualiza el inventario
                    _update_inventory_from_remision(remision, revert=False)
                    
                    messages.success(request, f'Remisión {remision.remision} creada exitosamente.')
                    return redirect('remision_lista')
                # --- FIN DE LA LÓGICA DE GUARDADO SEGURO ---
                
            except Exception as e:
                # Si algo falla (incluida nuestra ValidationError), la transacción se revierte
                messages.error(request, f'Ocurrió un error al guardar: {e}')
    else:
        # En GET, no pasamos empresa, así el formulario se inicializa con campos vacíos
        form = RemisionForm()
        formset = DetalleFormSet(
            prefix='detalles', 
            form_kwargs={'material_queryset': Material.objects.none(), 'lugar_queryset': Lugar.objects.none()}
        )

    context = {
        'form': form, 
        'formset': formset, 
        'titulo': 'Nueva Remisión',
        'is_editing': False  # Se mantiene para el JS
    }
    return render(request, 'ternium/remision_formulario.html', context)

@login_required
def editar_remision(request, pk):
    remision_original = get_object_or_404(Remision, pk=pk)
    if remision_original.status == 'AUDITADO':
        messages.error(request, 'No se puede editar una remisión auditada.')
        return redirect('detalle_remision', pk=remision_original.pk)

    DetalleFormSet = inlineformset_factory(
        Remision, DetalleRemision, form=DetalleRemisionForm, extra=0, can_delete=True, min_num=1
    )
    
    # --- INICIO DE LA MODIFICACIÓN ---
    # La empresa SIEMPRE será la original. Ya no se lee del POST.
    empresa_para_form = remision_original.empresa
    # --- FIN DE LA MODIFICACIÓN ---

    if request.method == 'POST':
        # Ya no necesitamos buscar la 'empresa_id' en el POST
        
        # Pasamos la empresa original para una validación correcta de catálogos
        form = RemisionForm(request.POST, request.FILES, instance=remision_original, empresa=empresa_para_form)
        
        material_qs = Material.objects.filter(empresas=empresa_para_form) if empresa_para_form else Material.objects.none()
        lugar_qs = Lugar.objects.filter(empresas=empresa_para_form, tipo__in=['DESTINO', 'AMBOS']) if empresa_para_form else Lugar.objects.none()

        formset = DetalleFormSet(
            request.POST, 
            instance=remision_original, 
            prefix='detalles', 
            form_kwargs={'material_queryset': material_qs, 'lugar_queryset': lugar_qs}
        )
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    _update_inventory_from_remision(remision_original, revert=True)
                    
                    remision = form.save(commit=False)
                    
                    # --- INICIO DE LA MODIFICACIÓN ---
                    # Usamos el folio original para las rutas de archivos
                    remision_num = remision_original.remision 
                    # --- FIN DE LA MODIFICACIÓN ---

                    if 'evidencia_carga' in request.FILES:
                        _eliminar_archivo_de_s3(remision_original.evidencia_carga.name if remision_original.evidencia_carga else None)
                        archivo = request.FILES['evidencia_carga']
                        # Usamos el remision_num (que es el original)
                        s3_path = f"remisiones/{remision_num}/carga_{archivo.name}"
                        remision.evidencia_carga = _subir_archivo_a_s3(archivo, s3_path)
                    
                    if 'evidencia_descarga' in request.FILES:
                        _eliminar_archivo_de_s3(remision_original.evidencia_descarga.name if remision_original.evidencia_descarga else None)
                        archivo = request.FILES['evidencia_descarga']
                        # Usamos el remision_num (que es el original)
                        s3_path = f"remisiones/{remision_num}/descarga_{archivo.name}"
                        remision.evidencia_descarga = _subir_archivo_a_s3(archivo, s3_path)

                    remision.save()
                    form.save_m2m()
                    formset.save()
                    
                    _update_inventory_from_remision(remision, revert=False)
                    messages.success(request, 'Remisión actualizada y el inventario ha sido ajustado.')
                    return redirect('detalle_remision', pk=remision.pk)
            except ValidationError as e:
                form.add_error(None, e)
                messages.error(request, f'Error de validación: {e.message}')
    else:
        # En GET, pasamos la empresa original para que los campos se carguen con las opciones correctas
        form = RemisionForm(instance=remision_original, empresa=empresa_para_form)
        material_qs = Material.objects.filter(empresas=empresa_para_form) if empresa_para_form else Material.objects.none()
        lugar_qs = Lugar.objects.filter(empresas=empresa_para_form, tipo__in=['DESTINO', 'AMBOS']) if empresa_para_form else Lugar.objects.none()
        
        formset = DetalleFormSet(
            instance=remision_original, 
            prefix='detalles', 
            form_kwargs={'material_queryset': material_qs, 'lugar_queryset': lugar_qs}
        )

    context = {
        'form': form,
        'formset': formset,
        'remision': remision_original, # <-- Pasamos la remisión al contexto
        'titulo': f'Editar Remisión {remision_original.remision}',
        'is_editing': True  # <-- Se mantiene para el JS y el HTML
    }
    return render(request, 'ternium/remision_formulario.html', context)

    
@login_required
def detalle_remision(request, pk):
    remision = get_object_or_404(Remision.objects.select_related('empresa', 'linea_transporte', 'operador', 'unidad', 'contenedor', 'origen', 'destino', 'auditado_por').prefetch_related('detalles__material'), pk=pk)
    return render(request, 'ternium/remision_detalle.html', {'remision': remision})


@login_required
@require_POST
@permission_required('ternium.can_audit_remision', raise_exception=True)
def auditar_remision(request, pk):
    remision = get_object_or_404(Remision, pk=pk)
    if remision.status == 'TERMINADO':
        remision.status = 'AUDITADO'
        remision.auditado_por = request.user
        remision.auditado_en = timezone.now()
        remision.save()
        messages.success(request, f'La remisión {remision.remision} ha sido auditada.')
    else:
        messages.error(request, 'Esta remisión no puede ser auditada.')
    return redirect('detalle_remision', pk=pk)


@method_decorator(login_required, name='dispatch')
class RemisionDeleteView(DeleteView):
    model = Remision
    template_name = 'ternium/remision_confirm_delete.html'
    success_url = reverse_lazy('remision_lista')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        if self.object.status == 'AUDITADO':
            messages.error(self.request, 'No se puede eliminar una remisión auditada.')
            return redirect('remision_lista')
            
        try:
            with transaction.atomic():
                # Revertir el inventario primero
                _update_inventory_from_remision(self.object, revert=True)

                # --- LÓGICA MANUAL DE BORRADO EN S3 ---
                if self.object.evidencia_carga and hasattr(self.object.evidencia_carga, 'name'):
                    _eliminar_archivo_de_s3(self.object.evidencia_carga.name)
                if self.object.evidencia_descarga and hasattr(self.object.evidencia_descarga, 'name'):
                    _eliminar_archivo_de_s3(self.object.evidencia_descarga.name)

                # Llamar al método original de borrado de la base de datos
                response = super().delete(request, *args, **kwargs)

            messages.success(self.request, f'Remisión {self.object.remision} eliminada y el inventario ha sido ajustado.')
            return response
        except Exception as e:
            messages.error(self.request, f"Ocurrió un error al eliminar la remisión: {e}")
            return redirect('remision_lista')


# --- VISTAS DE REGISTRO LOGISTICO ---

@method_decorator(login_required, name='dispatch')
class RegistroLogisticoListView(ListView):
    model = RegistroLogistico
    template_name = 'ternium/lista_logistica_ternium.html'
    context_object_name = 'registros'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().select_related('transportista', 'tractor', 'material').order_by('-fecha_carga')
        q_remision = self.request.GET.get('q_remision')
        q_transportista = self.request.GET.get('q_transportista')
        if q_remision:
            queryset = queryset.filter(Q(remision__icontains=q_remision) | Q(boleta_bascula__icontains=q_remision))
        if q_transportista:
            queryset = queryset.filter(transportista__nombre__icontains=q_transportista)
        return queryset


@method_decorator(login_required, name='dispatch')
class RegistroLogisticoDetailView(DetailView):
    model = RegistroLogistico
    template_name = 'ternium/detalle_logistica_ternium.html' 
    context_object_name = 'registro'


@method_decorator(login_required, name='dispatch')
class RegistroLogisticoCreateView(CreateView):
    model = RegistroLogistico
    form_class = RegistroLogisticoForm
    template_name = 'ternium/formulario_logistica_ternium.html'

    def get_success_url(self):
        return reverse_lazy('detalle_registro_logistica', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Nuevo Registro de Logística'
        return context
    
    def form_valid(self, form):
        # --- MODIFICACIÓN S3 ---
        self.object = form.save(commit=False)
        remision_num = form.cleaned_data.get('remision', 'sin_remision').strip()
        request = self.request

        archivos_a_subir = {
            'pdf_registro_camion_remision': '4.pdf', 'pdf_remision_permiso': '5.pdf',
            'foto_superior_vacia': '0', 'foto_frontal': '1',
            'foto_superior_llena': '2', 'foto_trasera': '3'
        }

        for campo, sufijo in archivos_a_subir.items():
            if campo in request.FILES:
                archivo = request.FILES[campo]
                if sufijo.endswith('.pdf'):
                    s3_path = f"logistica_ternium/{remision_num}/{remision_num}-{sufijo}"
                else:
                    _nombre_base, extension = os.path.splitext(archivo.name)
                    s3_path = f"logistica_ternium/{remision_num}/{remision_num}-{sufijo}{extension}"
                
                ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
                if ruta_guardada:
                    setattr(self.object, campo, ruta_guardada)

        self.object.save()
        form.save_m2m() # Important for ManyToMany fields
        messages.success(self.request, f"Registro {self.object.remision} creado con estatus '{self.object.get_status_display()}'.")
        return redirect(self.get_success_url())



@method_decorator(login_required, name='dispatch')
class RegistroLogisticoUpdateView(UpdateView):
    model = RegistroLogistico
    form_class = RegistroLogisticoForm
    template_name = 'ternium/formulario_logistica_ternium.html'
    
    def dispatch(self, request, *args, **kwargs):
        registro = self.get_object()
        if registro.status == 'AUDITADO':
            messages.error(request, "No se puede editar un registro auditado.")
            return redirect('detalle_registro_logistica', pk=registro.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('detalle_registro_logistica', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f"Editando Registro: {self.object.remision}"
        return context

    def form_valid(self, form):
        # --- MODIFICACIÓN S3 ---
        registro_original = self.get_object()
        self.object = form.save(commit=False)
        remision_num = form.cleaned_data.get('remision', 'sin_remision').strip()
        request = self.request

        archivos_a_subir = {
            'pdf_registro_camion_remision': '4.pdf', 'pdf_remision_permiso': '5.pdf',
            'foto_superior_vacia': '0', 'foto_frontal': '1',
            'foto_superior_llena': '2', 'foto_trasera': '3'
        }

        for campo, sufijo in archivos_a_subir.items():
            if campo in request.FILES:
                ruta_antigua = getattr(registro_original, campo)
                if ruta_antigua and hasattr(ruta_antigua, 'name'):
                    _eliminar_archivo_de_s3(ruta_antigua.name)
                
                archivo = request.FILES[campo]
                if sufijo.endswith('.pdf'):
                    s3_path = f"logistica_ternium/{remision_num}/{remision_num}-{sufijo}"
                else:
                    _nombre_base, extension = os.path.splitext(archivo.name)
                    s3_path = f"logistica_ternium/{remision_num}/{remision_num}-{sufijo}{extension}"

                ruta_guardada = _subir_archivo_a_s3(archivo, s3_path)
                if ruta_guardada:
                    setattr(self.object, campo, ruta_guardada)

        self.object.save()
        form.save_m2m() # Important for ManyToMany fields
        messages.success(self.request, f"Registro {self.object.remision} actualizado. Estatus: '{self.object.get_status_display()}'.")
        return redirect(self.get_success_url())

@login_required
@require_POST
def auditar_registro_logistico(request, pk):
    registro = get_object_or_404(RegistroLogistico, pk=pk)
    if registro.status == 'TERMINADO':
        registro.status = 'AUDITADO'
        registro.auditado_por = request.user
        registro.auditado_en = timezone.now()
        registro.save(update_fields=['status', 'auditado_por', 'auditado_en'])
        messages.success(request, f'El registro {registro.remision} ha sido auditado.')
    else:
        messages.error(request, 'Este registro no cumple los requisitos para ser auditado.')
    return redirect('detalle_registro_logistica', pk=pk)


@method_decorator(login_required, name='dispatch')
class DescargarPaqueteZipView(View):
    """
    Vista CORREGIDA para descargar un ZIP con todos los archivos de un RegistroLogistico.
    Usa boto3 para descargar explícitamente cada archivo desde S3.
    """
    def get(self, request, *args, **kwargs):
        registro = get_object_or_404(RegistroLogistico, pk=self.kwargs.get('pk'))

        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
        except (BotoCoreError, NoCredentialsError) as e:
            messages.error(request, f"Error de configuración con S3: {e}")
            return redirect('detalle_registro_logistica', pk=registro.pk)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            file_fields = [
                'pdf_registro_camion_remision', 'pdf_remision_permiso',
                'foto_superior_vacia', 'foto_frontal',
                'foto_superior_llena', 'foto_trasera'
            ]
            
            archivos_agregados = 0
            for field_name in file_fields:
                file_field = getattr(registro, field_name)
                if file_field and file_field.name:
                    s3_key = f"{settings.AWS_MEDIA_LOCATION}/{file_field.name}"
                    file_content_buffer = io.BytesIO()
                    
                    try:
                        s3_client.download_fileobj(settings.AWS_STORAGE_BUCKET_NAME, s3_key, file_content_buffer)
                        file_content_buffer.seek(0)
                        
                        filename_in_zip = os.path.basename(file_field.name)
                        zip_file.writestr(filename_in_zip, file_content_buffer.read())
                        archivos_agregados += 1
                    except s3_client.exceptions.ClientError as e:
                        if e.response['Error']['Code'] == '404':
                            print(f"Advertencia: El archivo {s3_key} no fue encontrado en S3 para el registro {registro.remision}.")
                        else:
                            messages.error(request, f"No se pudo descargar el archivo '{s3_key}' de S3.")
        
        if archivos_agregados == 0:
            messages.warning(request, "No se encontraron archivos en S3 para descargar en este registro.")
            return redirect('detalle_registro_logistica', pk=registro.pk)
            
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{registro.remision}.zip"'
        return response

# --- VISTAS DE EXPORTACIÓN Y API ---

@login_required
def export_logistica_to_excel(request):
    yellow_fill = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")
    wb = Workbook()
    ws = wb.active
    ws.title = "Registros Logísticos"
    columns = [
        'ID', 'FECHA CARGA', '# BOLETA BASCULA', 'REMISION', 'TRANSPORTISTA', 
        'PLACA TRACTOR', 'PLACA TOLVA', 'No. TRACTOR', 'No. TOLVA', 'CHOFER', 
        'TONELADAS REMISIONADAS', 'FECHA ENTREGA A TERNIUM', 'TONELADAS RECIBIDAS TERNIUM', 
        'MERMA (TON)', 'CODIGO MATERIAL', 'DESCRIPCION DEL MATERIAL', 'PERMISO CIRCULACION', 
        'COMENTARIOS 3R', 'PAPELES', 'FACTURA', 'MERMA (%)'
    ]
    ws.append(columns)
    ws.freeze_panes = 'A2'

    registros = RegistroLogistico.objects.select_related(
        'transportista', 'tractor', 'tolva', 'chofer', 'material'
    ).order_by('-fecha_carga')

    for registro in registros:
        row_data = [
            registro.id, registro.fecha_carga, registro.boleta_bascula, registro.remision,
            registro.transportista.nombre if registro.transportista else 'N/A',
            registro.tractor.placas if registro.tractor else 'N/A',
            registro.tolva.placas if registro.tolva else 'N/A',
            registro.tractor.nombre if registro.tractor else 'N/A',
            registro.tolva.nombre if registro.tolva else 'N/A',
            registro.chofer.nombre if registro.chofer else 'N/A',
            registro.toneladas_remisionadas, registro.fecha_envio, registro.toneladas_recibidas,
            registro.merma_absoluta,
            registro.material.id if registro.material else 'N/A',
            registro.material.nombre if registro.material else 'N/A',
            '', '', '', '',
            registro.merma_porcentaje if registro.merma_porcentaje is not None else 0,
        ]
        ws.append(row_data)
        if registro.merma_porcentaje is not None and abs(registro.merma_porcentaje) > 1:
            for cell in ws[ws.max_row]:
                cell.fill = yellow_fill

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Registros_Logisticos_{datetime.date.today()}.xlsx"'
    wb.save(response)
    return response


def get_catalogos_por_empresa(request, empresa_id):
    """
    Devuelve los catálogos filtrados por una empresa específica.
    ESTA ES LA VERSIÓN CORREGIDA.
    """
    try:
        # La línea 'unidades' fallaba porque 'models.F' no estaba definido.
        # Al importar 'F' directamente, ahora funciona correctamente.
        data = {
            'lineas_transporte': list(LineaTransporte.objects.filter(empresas__id=empresa_id).values('id', 'nombre')),
            'materiales': list(Material.objects.filter(empresas__id=empresa_id).values('id', 'nombre')),
            'unidades': list(Unidad.objects.filter(empresas__id=empresa_id).values('id', nombre=F('internal_id'), placas=F('license_plate'))),
            'contenedores': list(Contenedor.objects.filter(empresas__id=empresa_id).values('id', 'nombre', 'placas')),
            'lugares_origen': list(Lugar.objects.filter(empresas__id=empresa_id, tipo__in=['ORIGEN', 'AMBOS']).values('id', 'nombre')),
            'lugares_destino': list(Lugar.objects.filter(empresas__id=empresa_id, tipo__in=['DESTINO', 'AMBOS']).values('id', 'nombre')),
        }
        return JsonResponse(data)
    except Exception as e:
        # En caso de otro error, devolvemos una respuesta vacía con un error 500
        # para que sea más fácil de depurar en el futuro.
        print(f"Error en get_catalogos_por_empresa: {e}")
        return JsonResponse({'error': 'Ocurrió un error en el servidor'}, status=500)


class CatalogoListView(ListView):
    """
    Clase base Premium. Incluye búsqueda avanzada, filtro dinámico por 'Empresa'
    y paginación.
    """
    template_name = 'ternium/catalogo_lista.html'
    paginate_by = 15

    def get_queryset(self):
        # Esta versión ya está corregida y no debería dar errores.
        queryset = super().get_queryset()
        query = self.request.GET.get('q')
        
        empresa_id = self.request.GET.get('empresa')

        if empresa_id and hasattr(self.model, 'empresas'):
            queryset = queryset.filter(empresas__id=empresa_id)

        if query:
            if hasattr(self.model, 'search_fields'):
                q_objects = Q()
                for field in self.model.search_fields:
                    q_objects |= Q(**{f'{field}__icontains': query})
                queryset = queryset.filter(q_objects).distinct()
            # Fallback seguro por si un modelo no define `search_fields`
            elif hasattr(self.model, 'internal_id'):
                queryset = queryset.filter(internal_id__icontains=query)
            elif hasattr(self.model, 'nombre'):
                 queryset = queryset.filter(nombre__icontains=query)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        model_name = self.model._meta.model_name
        
        context['verbose_name_plural'] = self.model._meta.verbose_name_plural
        context['verbose_name'] = self.model._meta.verbose_name
        context['model_name'] = model_name
        context['search_query'] = self.request.GET.get('q', '')
        
        # Check if the model has 'empresas' m2m field
        context['has_empresa_filter'] = hasattr(self.model, 'empresas') and model_name != 'empresa'
        if context['has_empresa_filter']:
            context['empresas'] = Empresa.objects.all().order_by('nombre')
            try:
                context['selected_empresa'] = int(self.request.GET.get('empresa', ''))
            except (ValueError, TypeError):
                context['selected_empresa'] = ''

        return context
    
# --- VISTAS DE CATÁLOGOS ---
class EmpresaListView(CatalogoListView): 
    model = Empresa
    template_name = 'ternium/empresa_list.html' # Template nuevo

class EmpresaCreateView(CreateView): 
    model = Empresa
    form_class = EmpresaForm
    template_name = 'ternium/empresa_form.html' # Template modificado
    success_url = reverse_lazy('lista_empresas')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Crear Nueva Empresa'
        return context

class EmpresaDetailView(DetailView): 
    model = Empresa
    template_name = 'ternium/empresa_detail.html' # Template nuevo

class EmpresaUpdateView(UpdateView): 
    model = Empresa
    form_class = EmpresaForm
    template_name = 'ternium/empresa_form.html' # Template modificado
    success_url = reverse_lazy('lista_empresas')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f'Editar Empresa: {self.object.nombre}'
        return context

class LineaTransporteListView(CatalogoListView): model = LineaTransporte
class LineaTransporteCreateView(CreateView): model = LineaTransporte; form_class = LineaTransporteForm; success_url = reverse_lazy('lista_lineas_transporte')
class LineaTransporteDetailView(DetailView): model = LineaTransporte
class LineaTransporteUpdateView(UpdateView): model = LineaTransporte; form_class = LineaTransporteForm; success_url = reverse_lazy('lista_lineas_transporte')

class OperadorListView(CatalogoListView): model = Operador
class OperadorCreateView(CreateView): model = Operador; form_class = OperadorForm; success_url = reverse_lazy('lista_operadores')
class OperadorDetailView(DetailView): model = Operador
class OperadorUpdateView(UpdateView): model = Operador; form_class = OperadorForm; success_url = reverse_lazy('lista_operadores')

class MaterialListView(CatalogoListView): model = Material
class MaterialCreateView(CreateView): model = Material; form_class = MaterialForm; success_url = reverse_lazy('lista_materiales')
class MaterialDetailView(DetailView): model = Material
class MaterialUpdateView(UpdateView): model = Material; form_class = MaterialForm; success_url = reverse_lazy('lista_materiales')


@method_decorator(login_required, name='dispatch')
class UnidadListView(CatalogoListView): 
    model = Unidad
    template_name = 'ternium/unidad_list.html' # Asegúrate que este template exista
class UnidadCreateView(CreateView): model = Unidad; form_class = UnidadForm; success_url = reverse_lazy('lista_unidades')
class UnidadDetailView(DetailView): model = Unidad
class UnidadUpdateView(UpdateView): model = Unidad; form_class = UnidadForm; success_url = reverse_lazy('lista_unidades')

class ContenedorListView(CatalogoListView): model = Contenedor
class ContenedorCreateView(CreateView): model = Contenedor; form_class = ContenedorForm; success_url = reverse_lazy('lista_contenedores')
class ContenedorDetailView(DetailView): model = Contenedor
class ContenedorUpdateView(UpdateView): model = Contenedor; form_class = ContenedorForm; success_url = reverse_lazy('lista_contenedores')

class LugarListView(CatalogoListView): model = Lugar
class LugarCreateView(CreateView): model = Lugar; form_class = LugarForm; success_url = reverse_lazy('lista_lugares')
class LugarDetailView(DetailView): model = Lugar
class LugarUpdateView(UpdateView): model = Lugar; form_class = LugarForm; success_url = reverse_lazy('lista_lugares')

class DescargaListView(ListView):
    model = Descarga
    paginate_by = 15
    def get_queryset(self):
        return Descarga.objects.select_related('origen', 'destino', 'material', 'registrado_por').order_by('-fecha_descarga')

class DescargaCreateView(CreateView):
    model = Descarga
    form_class = DescargaForm
    success_url = reverse_lazy('descarga_lista')
    def form_valid(self, form):
        descarga = form.save(commit=False)
        descarga.registrado_por = self.request.user
        try:
            descarga.save()
            messages.success(self.request, "Descarga registrada y el inventario ha sido actualizado.")
            return redirect(self.success_url)
        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)
        
@login_required
def export_remisiones_to_excel(request):
    # Crear el libro de trabajo
    wb = Workbook()
    ws = wb.active
    ws.title = "Remisiones"
    
    # Encabezados
    headers = [
        'ID', 'Remisión', 'Fecha', 'Estatus', 'Empresa',
        'Origen', 'Destino', 'Línea de Transporte', 'Operador',
        'Unidad', 'Contenedor', 'Total Peso Carga (Ton)', 'Total Peso Descarga (Ton)',
        'Diferencia (Ton)'
    ]
    ws.append(headers)
    
    # Obtener datos
    remisiones = Remision.objects.select_related(
        'empresa', 'origen', 'destino', 'linea_transporte', 'operador', 'unidad', 'contenedor'
    ).all().order_by('-fecha')
    
    # Escribir filas
    for remision in remisiones:
        ws.append([
            remision.pk,
            remision.remision,
            remision.fecha,
            remision.get_status_display(),
            remision.empresa.nombre if remision.empresa else '',
            remision.origen.nombre if remision.origen else '',
            remision.destino.nombre if remision.destino else '',
            remision.linea_transporte.nombre if remision.linea_transporte else '',
            remision.operador.nombre if remision.operador else '',
            str(remision.unidad) if remision.unidad else '',
            str(remision.contenedor) if remision.contenedor else '',
            remision.total_peso_ld,
            remision.total_peso_dlv,
            remision.diff
        ])

    # --- NUEVA LÓGICA DE FORMATO ---
    
    # 1. Crear la Tabla de Excel (Formato General)
    # Definimos el rango: Desde A1 hasta la última columna y última fila
    last_col_letter = get_column_letter(len(headers))
    last_row = ws.max_row
    table_ref = f"A1:{last_col_letter}{last_row}"
    
    tabla = Table(displayName="TablaRemisiones", ref=table_ref)
    
    # Estilo de tabla (TableStyleMedium9 es un estilo azul estándar agradable)
    style = TableStyleInfo(
        name="TableStyleMedium9", 
        showFirstColumn=False,
        showLastColumn=False, 
        showRowStripes=True, 
        showColumnStripes=False
    )
    tabla.tableStyleInfo = style
    ws.add_table(tabla)

    # 2. Centrar contenido y 3. Ajustar ancho de columnas
    center_alignment = Alignment(horizontal='center', vertical='center')
    
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter # Letra de la columna
        
        for cell in col:
            # Aplicar centrado a cada celda
            cell.alignment = center_alignment
            
            # Calcular longitud máxima para el autoajuste
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        
        # Ajustar ancho (se suma un extra para que no quede apretado)
        adjusted_width = (max_length + 4)
        ws.column_dimensions[column].width = adjusted_width

    # Generar respuesta
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Remisiones_{datetime.date.today()}.xlsx"'
    wb.save(response)
    return response


@login_required
def detalles_genericos(request, model_name, pk):
    model_map = {
        'empresa': Empresa, 'material': Material, 'unidad': Unidad,
        'contenedor': Contenedor, 'operador': Operador, 'lugar': Lugar,
        'lineatransporte': LineaTransporte,
    }
    model = model_map.get(model_name)
    if not model:
        return HttpResponse('Modelo no encontrado', status=404)
    
    objeto = get_object_or_404(model, pk=pk)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'ternium/detalles_genericos.html', {
            'objeto': objeto, 'model_name': model_name,
            'verbose_name': model._meta.verbose_name
        })
    
    return redirect(f'/{model_name}/editar/{pk}/')

@login_required
def busqueda_avanzada(request):
    query = request.GET.get('q', '')
    filter_type = request.GET.get('filter_type', 'all')
    
    if not query:
        return JsonResponse({'results': []})
    
    models_to_search = {
        'empresa': Empresa, 'material': Material, 'unidad': Unidad,
        'contenedor': Contenedor, 'operador': Operador, 'lugar': Lugar,
        'lineatransporte': LineaTransporte,
    }
    
    results = []
    
    for model_name, model in models_to_search.items():
        queryset = model.objects.all()
        
        if filter_type == 'all':
            q_objects = Q(nombre__icontains=query)
            if model_name == 'empresa':
                q_objects |= Q(rfc__icontains=query) | Q(contacto_principal__icontains=query)
            elif model_name == 'operador':
                q_objects |= Q(licencia__icontains=query) | Q(telefono__icontains=query)
            elif model_name in ['unidad', 'contenedor']:
                q_objects |= Q(placas__icontains=query)
            queryset = queryset.filter(q_objects)
        elif filter_type == 'nombre':
            queryset = queryset.filter(nombre__icontains=query)
        elif filter_type == 'rfc' and hasattr(model, 'rfc'):
            queryset = queryset.filter(rfc__icontains=query)
        
        for obj in queryset[:5]:
            edit_url_name = f'editar_{model_name}'
            try:
                url = reverse(edit_url_name, args=[obj.id])
            except:
                url = '#' 

            results.append({
                'model': model_name,
                'model_verbose': model._meta.verbose_name,
                'id': obj.id,
                'nombre': obj.nombre,
                'detalles': getattr(obj, 'rfc', '') or getattr(obj, 'licencia', '') or getattr(obj, 'placas', '') or '',
                'url': url
            })
    
    return JsonResponse({'results': results})


import os
import re
import io
import logging
import pandas as pd
import boto3
from botocore.exceptions import NoCredentialsError, BotoCoreError

from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from langchain_deepseek import ChatDeepSeek
from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from sqlalchemy import create_engine
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font

# Configura un logger para un mejor seguimiento de errores
logger = logging.getLogger(__name__)

# Función auxiliar para extraer SQL de la respuesta del LLM
def _extraer_sql(texto_respuesta_ia: str) -> str:
    """
    Extrae el código SQL de la respuesta de un LLM de forma más robusta.
    """
    match = re.search(r"```sql\n(.*?)\n```", texto_respuesta_ia, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    select_pos = texto_respuesta_ia.upper().find("SELECT")
    if select_pos != -1:
        # Limpia el texto que a veces el LLM añade después del SQL
        sql_text = texto_respuesta_ia[select_pos:]
        if ';' in sql_text:
            sql_text = sql_text.split(';')[0]
        return sql_text.strip()
        
    return texto_respuesta_ia.strip()


@login_required
@permission_required('ternium.use_ai_assistant', raise_exception=True)
@csrf_exempt
def asistente_ia(request):
    """
    Gestiona las solicitudes al Asistente de IA, generando respuestas de texto,
    tablas HTML y, opcionalmente, archivos Excel bajo demanda.
    """
    if request.method == 'POST':
        pregunta = request.POST.get('pregunta', '').strip()
        if not pregunta:
            return JsonResponse({'error': 'La pregunta no puede estar vacía.'}, status=400)

        try:
            # 1. Verificación de configuración
            api_key = os.environ.get('DEEPSEEK_API_KEY')
            db_url = os.environ.get('DATABASE_URL_READONLY')
            if not api_key or not db_url:
                error_msg = 'Error de configuración del servidor: Faltan claves de API o la URL de la base de datos.'
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 2. Configuración de IA y Base de Datos
            db_engine = create_engine(db_url)
            db = SQLDatabase(engine=db_engine)
            llm = ChatDeepSeek(model="deepseek-chat", api_key=api_key, temperature=0)

            # 3. Determinar la intención del usuario
            router_prompt = PromptTemplate.from_template(
                """Analiza la pregunta del usuario y clasifícala en UNA de las siguientes categorías:
                1. 'saludo': Saludos generales o preguntas sobre tu función.
                2. 'excel': Solicitudes explícitas para generar un archivo. Busca palabras clave como "excel", "reporte", "genera", "dame", "entrégame", "exporta", "descarga".
                3. 'consulta': Cualquier otra pregunta que requiera buscar datos pero NO pide un archivo.
                
                Responde ÚNICAMENTE con la palabra de la categoría (ej: 'excel').
                Pregunta: "{pregunta}" """
            )
            router_chain = router_prompt | llm | StrOutputParser()
            intencion = router_chain.invoke({"pregunta": pregunta}).strip().lower()

            if 'saludo' in intencion:
                return JsonResponse({'respuesta': "¡Hola! Soy tu asistente de datos. Puedes hacerme preguntas o pedirme que genere reportes en Excel."})

            # 4. Generar y validar la consulta SQL
            table_info = db.get_table_info()
            template_sql = """Eres un experto en PostgreSQL. Genera SOLO consultas SELECT para responder la pregunta.
            ESQUEMA DISPONIBLE:
            {table_info}
            REGLAS ESTRICTAS:
            1. SOLO usa SELECT. NUNCA uses INSERT, UPDATE, DELETE.
            2. Usa únicamente las tablas y columnas del esquema.
            3. Para "hoy", usa CURRENT_DATE.
            4. Incluye siempre LIMIT 1000 para evitar consultas muy grandes.
            5. Si no es posible responder, devuelve 'INVALIDO'.
            PREGUNTA: {question}
            SQL QUERY:"""
            prompt_sql = PromptTemplate(input_variables=["question", "table_info"], template=template_sql)
            chain_sql = prompt_sql | llm | StrOutputParser()
            respuesta_sql = chain_sql.invoke({"question": pregunta, "table_info": table_info})

            if 'INVALIDO' in respuesta_sql.upper():
                return JsonResponse({'respuesta': 'No pude generar una consulta para esa pregunta. ¿Podrías reformularla?'})

            consulta_sql = _extraer_sql(respuesta_sql)
            if not consulta_sql.upper().startswith('SELECT'):
                return JsonResponse({'error': 'Solo se permiten consultas SELECT.'}, status=400)
            if 'LIMIT' not in consulta_sql.upper():
                consulta_sql += " LIMIT 1000"

            # 5. Ejecutar consulta y obtener datos
            with db_engine.connect() as connection:
                df = pd.read_sql(consulta_sql, connection)

            file_url = None
            tabla_html = ""
            
            # 6. Lógica condicional para generar el archivo Excel
            if 'excel' in intencion and not df.empty:
                nombre_base = re.sub(r'[^a-zA-Z0-9]+', '_', pregunta.lower())[:30] or "reporte"
                timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
                # Esta es la ruta relativa donde se guardará el archivo
                file_name = f"reportes_ia/{nombre_base}_{timestamp}.xlsx"
                
                # Generar el archivo en memoria (sin cambios aquí)
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df_excel = df.copy()
                    for col in df_excel.select_dtypes(include=['datetimetz']).columns:
                        df_excel[col] = df_excel[col].dt.tz_localize(None)
                    df_excel.to_excel(writer, index=False, sheet_name='Datos')
                    
                    worksheet = writer.sheets['Datos']
                    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
                    header_font = Font(color="FFFFFF", bold=True)
                    for col_num, value in enumerate(df_excel.columns.values):
                        cell = worksheet.cell(row=1, column=col_num + 1)
                        cell.fill = header_fill
                        cell.font = header_font
                    for column in worksheet.columns:
                        max_length = max((len(str(cell.value)) for cell in column if cell.value), default=0)
                        adjusted_width = min(max_length + 2, 50)
                        worksheet.column_dimensions[get_column_letter(column[0].column)].width = adjusted_width
                
                excel_buffer.seek(0)
                
                # --- INICIO: CAMBIO IMPORTANTE ---
                # Usamos la función _subir_archivo_a_s3 que ya existe en tu proyecto.
                # Esto unifica la lógica de subida de archivos.
                file_path_relative = _subir_archivo_a_s3(excel_buffer, file_name)
                
                if file_path_relative:
                    try:
                        s3_client = boto3.client(
                            's3',
                            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                            region_name=settings.AWS_S3_REGION_NAME,
                            config=boto3.session.Config(signature_version='s3v4')
                        )
                        # CORRECCIÓN: La "Key" en S3 debe incluir la ruta completa, incluyendo 'media/'.
                        full_s3_key = f"{settings.AWS_MEDIA_LOCATION}/{file_path_relative}"
                        
                        file_url = s3_client.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': full_s3_key},
                            ExpiresIn=172800  # URL válida por 2 días
                        )
                    except (NoCredentialsError, BotoCoreError, Exception) as e:
                        logger.error(f"No se pudo generar la URL prefirmada para S3: {e}")
                        # Fallback a una URL simple si la prefirmada falla
                        file_url = default_storage.url(file_path_relative)
                else:
                    logger.error(f"Fallo al subir el archivo de IA a S3: {file_name}")
                # --- FIN: CAMBIO IMPORTANTE ---

            # 7. Generar respuesta de texto y tabla HTML (sin cambios aquí)
            if not df.empty:
                template_respuesta = """Eres un analista de datos experto. Basado en los datos, proporciona una respuesta clara y concisa en español.
                CONTEXTO: El usuario preguntó: "{pregunta}"
                DATOS (resumen):
                - Columnas: {columnas}
                - Total de registros: {total_registros}
                - Primeras filas: {muestra_datos}
                RESPUESTA: (Resume los hallazgos, destaca números importantes y menciona que el Excel está listo si se generó)"""
                prompt_respuesta = PromptTemplate.from_template(template_respuesta)
                chain_respuesta = prompt_respuesta | llm | StrOutputParser()
                muestra_datos = df.head(3).to_string()
                respuesta_final = chain_respuesta.invoke({
                    "pregunta": pregunta, 
                    "columnas": ", ".join(df.columns.tolist()),
                    "total_registros": len(df),
                    "muestra_datos": muestra_datos
                })
                
                tabla_html = df.head(10).to_html(classes='table table-sm table-striped mt-3', index=False, border=0, escape=False)
                if len(df) > 10:
                    preview_text = f'Mostrando 10 de {len(df)} registros.'
                    if file_url:
                        preview_text += f' <a href="{file_url}" download class="text-decoration-none">📥 Descargar el reporte completo</a>'
                    tabla_html += f'<div class="mt-2 text-center text-muted"><small>{preview_text}</small></div>'
            else:
                respuesta_final = "🔍 La consulta no devolvió resultados. Intenta con otros criterios."

            # 8. Ensamblar la respuesta final (sin cambios aquí)
            if file_url:
                respuesta_final += f"""
                <div class="alert alert-success mt-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas fa-file-excel fa-2x text-success"></i>
                            <strong class="ms-2">¡Tu reporte está listo!</strong>
                            <div class="text-muted">Contiene {len(df)} registros.</div>
                        </div>
                        <a href="{file_url}" download class="btn btn-success">
                            <i class="fas fa-download"></i> Descargar
                        </a>
                    </div>
                </div>
                """
            
            return JsonResponse({
                'respuesta': respuesta_final,
                'tabla_html': tabla_html,
                'url_excel': file_url
            })

        except Exception as e:
            logger.error(f"Error inesperado en asistente_ia: {str(e)}", exc_info=True)
            error_msg = "❌ Ocurrió un error inesperado. Por favor, intenta de nuevo."
            if settings.DEBUG:
                error_msg += f"<br><small>Detalle: {str(e)}</small>"
            return JsonResponse({'error': error_msg}, status=500)

    # Si es una petición GET, solo muestra la página
    return render(request, 'ternium/asistente_ia.html')


@method_decorator(login_required, name='dispatch')
class UnidadListView(CatalogoListView): # <-- MODIFICADO: Hereda de CatalogoListView
    """
    Vista para listar TODOS los activos (Unidades).
    Incluye filtros avanzados.
    """
    model = Unidad
    template_name = 'ternium/unidad_list.html'
    context_object_name = 'unidades' # Mantenemos 'unidades' para el template
    paginate_by = 20

    def get_queryset(self):
        # 1. Empezamos con el queryset del padre (que ya filtra por 'q' y 'empresa')
        queryset = super().get_queryset().prefetch_related('empresas') # <-- Optimizado con prefetch
        
        # 2. Obtenemos los filtros adicionales
        asset_type = self.request.GET.get('asset_type')
        status = self.request.GET.get('status')

        # 3. Aplicamos los filtros adicionales
        if asset_type:
            queryset = queryset.filter(asset_type=asset_type)
        if status:
            queryset = queryset.filter(operational_status=status)
        
        return queryset.order_by('internal_id') # Ordenamos por ID

    def get_context_data(self, **kwargs):
        # 1. Obtenemos el contexto del padre (que ya incluye 'empresas', 'search_query', etc.)
        context = super().get_context_data(**kwargs)
        
        # 2. Renombramos 'object_list' a 'unidades' para que el template funcione
        context['unidades'] = context.get('object_list')
        
        # 3. Añadimos las opciones para los nuevos filtros
        context['asset_type_choices'] = Unidad.AssetType.choices
        context['status_choices'] = Unidad.OperationalStatus.choices
        
        # 4. Pasamos todos los filtros aplicados para mantener el estado del form
        context['filtros_aplicados'] = self.request.GET
        return context

@login_required
def editar_unidad(request, pk):
    unidad_original = get_object_or_404(Unidad, pk=pk)
    
    if request.method == 'POST':
        form = UnidadForm(request.POST, request.FILES, instance=unidad_original)
        if form.is_valid():
            unidad = form.save(commit=False)
            unidad_id_folder = form.cleaned_data.get('internal_id', 'sin_id').strip()

            # Lógica para actualizar foto
            if 'display_photo' in request.FILES:
                _eliminar_archivo_de_s3(unidad_original.display_photo.name if unidad_original.display_photo else None)
                archivo = request.FILES['display_photo']
                s3_path = f"activos_unidades/{unidad_id_folder}/foto_{archivo.name}"
                unidad.display_photo = _subir_archivo_a_s3(archivo, s3_path)
            
            # Lógica para actualizar documentos
            if 'unit_documents' in request.FILES:
                _eliminar_archivo_de_s3(unidad_original.unit_documents.name if unidad_original.unit_documents else None)
                archivo = request.FILES['unit_documents']
                s3_path = f"activos_unidades/{unidad_id_folder}/doc_{archivo.name}"
                unidad.unit_documents = _subir_archivo_a_s3(archivo, s3_path)

            unidad.save()
            form.save_m2m()
            messages.success(request, f'Activo "{unidad.internal_id}" actualizado.')
            return redirect('lista_unidades')
    else:
        form = UnidadForm(instance=unidad_original)

    context = {
        'form': form, 'object': unidad_original, 'titulo': f'Editar Activo: {unidad_original.internal_id}'
    }
    return render(request, 'ternium/unidad_form.html', context)

@method_decorator(login_required, name='dispatch')
class UnidadDetailView(DetailView): 
    model = Unidad
    template_name = 'ternium/unidad_detail.html' # Asegúrate que este template exista


from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from .models import Profile # Asegúrate de que Profile esté importado

@login_required
def vista_perfil(request):
    user = request.user
    # Se usa transaction.atomic para asegurar que todos los cambios se guarden o ninguno.
    with transaction.atomic():
        profile, created = Profile.objects.select_for_update().get_or_create(user=user)
    
    password_form = PasswordChangeForm(user)

    if request.method == 'POST':
        # --- Formulario para actualizar la información del perfil ---
        if 'update_profile' in request.POST:
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = request.POST.get('email', '')
            user.save()

            profile.area = request.POST.get('area', '')
            profile.empresa = request.POST.get('empresa', '')
            profile.telefono = request.POST.get('telefono', '')

            # --- INICIO: LÓGICA MODIFICADA PARA SUBIR AVATAR A S3 ---
            if 'avatar' in request.FILES:
                archivo_avatar = request.FILES['avatar']
                
                # 1. Obtenemos la ruta del avatar antiguo para poder borrarlo después.
                #    Nos aseguramos de no intentar borrar el avatar por defecto.
                ruta_avatar_antiguo = None
                if profile.avatar and profile.avatar.name != 'avatars/default-avatar.png':
                    ruta_avatar_antiguo = profile.avatar.name

                # 2. Construimos la nueva ruta en S3.
                s3_path_relativa = f"avatars/user_{user.id}/{archivo_avatar.name}"
                
                # 3. Subimos el nuevo archivo usando la función auxiliar.
                ruta_guardada = _subir_archivo_a_s3(archivo_avatar, s3_path_relativa)

                if ruta_guardada:
                    # 4. Asignamos la nueva ruta al perfil.
                    profile.avatar = ruta_guardada
                    
                    # 5. Si la subida fue exitosa y había un avatar antiguo, lo eliminamos.
                    if ruta_avatar_antiguo:
                        _eliminar_archivo_de_s3(ruta_avatar_antiguo)
                else:
                    messages.error(request, "Hubo un error al subir tu nueva foto de perfil.")
            # --- FIN: LÓGICA MODIFICADA ---
            
            profile.save()
            messages.success(request, '¡Tu perfil se ha actualizado correctamente!')
            return redirect('perfil')

        # --- Formulario para cambiar la contraseña (sin cambios) ---
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, '¡Tu contraseña fue cambiada con éxito!')
                return redirect('perfil')
            else:
                messages.error(request, 'No se pudo cambiar la contraseña. Por favor, corrige los errores.')

    user_groups = user.groups.all()
    context = {
        'password_form': password_form,
        'user_groups': user_groups
    }
    return render(request, 'ternium/perfil.html', context)


class EmpresaVincularOrigenesView(LoginRequiredMixin, UpdateView):
    model = Empresa
    form_class = EmpresaOrigenesForm
    template_name = 'ternium/empresa_vincular_origenes.html' # <-- Un template nuevo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = f"Vinculando Orígenes para: {self.object.nombre}"
        return context

    def get_success_url(self):
        # Redirige a donde tengas tu lista de empresas o lugares
        # (Ajusta 'lista_lugares' si tienes una lista de empresas)
        return reverse_lazy('lista_lugares')
    
# --- COLOCAR AL FINAL DE ternium/views.py ---

# Asegúrate de que estas importaciones estén presentes
from django.db.models import Count, Sum, F, Avg, Q
from django.db.models.functions import TruncMonth, Coalesce

@login_required
def dashboard_analisis_view(request):
    # 1. DATOS TERNIUM (LOGÍSTICA)
    logistica_qs = RegistroLogistico.objects.filter(status='TERMINADO')
    
    log_kpis = logistica_qs.aggregate(
        total_viajes=Count('id'),
        total_enviado=Sum('toneladas_remisionadas'),
        total_recibido=Sum('toneladas_recibidas'),
        merma_total=Sum(F('toneladas_remisionadas') - F('toneladas_recibidas')),
    )
    
    if log_kpis['total_enviado'] and log_kpis['total_enviado'] > 0:
        porcentaje_merma = (log_kpis['merma_total'] / log_kpis['total_enviado']) * 100
    else:
        porcentaje_merma = 0

    log_materiales = logistica_qs.values('material__nombre').annotate(
        total_tons=Sum('toneladas_remisionadas')
    ).order_by('-total_tons')[:5]

    log_transportistas = logistica_qs.values('transportista__nombre').annotate(
        viajes=Count('id')
    ).order_by('-viajes')[:5]

    # 2. DATOS BOLETAS (MAQUILA)
    entradas_qs = EntradaMaquila.objects.all()

    maq_kpis = entradas_qs.aggregate(
        total_entradas=Count('id'),
        total_peso_neto=Sum('peso_neto'),
        total_alertas=Count('id', filter=Q(alerta=True)),
        promedio_tara=Avg('peso_tara')
    )

    maq_calidades = entradas_qs.values('calidad').annotate(
        cantidad=Count('id'),
        toneladas=Sum('peso_neto')
    ).order_by('-toneladas')

    maq_timeline = entradas_qs.annotate(
        mes=TruncMonth('fecha_ingreso')
    ).values('mes').annotate(
        total=Sum('peso_neto')
    ).order_by('mes')

    # 3. INVENTARIO
    inventario_actual = InventarioPatio.objects.values('patio__nombre', 'material__nombre').annotate(
        total_kg=Sum('cantidad')
    ).order_by('patio__nombre')

    context = {
        'log_kpis': log_kpis,
        'porcentaje_merma': porcentaje_merma,
        'log_materiales': list(log_materiales),
        'log_transportistas': list(log_transportistas),
        'maq_kpis': maq_kpis,
        'maq_calidades': list(maq_calidades),
        'maq_timeline': list(maq_timeline),
        'inventario': inventario_actual,
    }
    
    return render(request, 'ternium/dashboard_analisis.html', context)