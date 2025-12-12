# ternium/views.py

import io
import os
import zipfile
import datetime
from django.db import IntegrityError # <--- AGREGAR ESTO AL INICIO DE views.py
import decimal
from django.db.models import Count, Sum, F, Avg, Q, FloatField, Case, When, Value
from django.db.models.functions import TruncMonth, Coalesce # <-- AGREGAR ESTA LÍNEA
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
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.clickjacking import xframe_options_exempt
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
def home_bienvenida(request):
    """
    Vista simple que carga la landing page.
    Accesible para todos los usuarios logueados.
    """
    return render(request, 'ternium/bienvenida.html')


# --- 2. VISTA DASHBOARD OPERACIONES (ANTIGUO HOME) ---
@login_required
def dashboard_operaciones_view(request):
    
    # Solo calculamos los datos SI el usuario tiene permiso
    if request.user.has_perm('ternium.acceso_dashboard_patio'):
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
                'cantidad_toneladas': item.cantidad / KG_TO_TON,
                # Simulamos porcentaje para la barra visual (puedes ajustar lógica real)
                'porcentaje_ocupacion': 75 
            } for item in inventario_kg]

            ultima_actualizacion_obj = InventarioPatio.objects.filter(patio=patio).order_by('-ultima_actualizacion').first()

            patios_data.append({
                'nombre': patio.nombre,
                'materiales': materiales_en_toneladas,
                'total_toneladas': total_toneladas,
                'ultima_actualizacion': ultima_actualizacion_obj.ultima_actualizacion if ultima_actualizacion_obj else None,
                'estado': 'ok' # Puedes añadir lógica para 'warning' o 'danger'
            })

        context = {
            'total_entradas': total_entradas,
            'total_alertas': total_alertas,
            'patios_inventario': patios_data,
            'total_registros_logistica': total_registros_logistica,
            'has_permission': True # Bandera para el template
        }
        return render(request, 'ternium/home.html', context)
    
    else:
        # Si NO tiene permiso, renderizamos la página vacía (el HTML mostrará el bloqueo)
        return render(request, 'ternium/home.html', {'has_permission': False})


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

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

# Busca la clase RemisionListView y modifícala así:
class RemisionListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'ternium.acceso_remisiones' # <--- PROTECCIÓN
    model = Remision
    template_name = 'ternium/remision_lista.html'
    context_object_name = 'remisiones'
    paginate_by = 15
    
    def get_queryset(self):
        # CAMBIO CRÍTICO AQUÍ:
        # Usamos .order_by('-pk') en lugar de '-remision'.
        # '-pk' ordena por el ID interno de la base de datos (el último creado aparece primero).
        # Esto soluciona el error de que 999 aparezca antes que 1000.
        queryset = Remision.objects.select_related(
            'empresa', 'origen', 'destino'
        ).prefetch_related(
            'detalles__material'
        ).order_by('-pk') 
        
        self.search_params = self.request.GET.copy()
        
        # Detectar si hay filtros activos
        filtros_activos = any(
            k.startswith('q_') and v for k, v in self.request.GET.items()
        )
        
        # Lógica de fechas por defecto (Hoy y hace 1 mes) si no hay filtros
        if not filtros_activos:
            today = timezone.now().date()
            month_ago = today - datetime.timedelta(days=30)
            self.search_params['q_fecha_desde'] = month_ago.strftime('%Y-%m-%d')
            self.search_params['q_fecha_hasta'] = today.strftime('%Y-%m-%d')

        # Aplicar filtros
        filters = {
            'remision__icontains': self.search_params.get('q_remision'),
            'empresa__prefijo__icontains': self.search_params.get('q_prefijo'),
            'detalles__material_id': self.search_params.get('q_material'),
            'origen_id': self.search_params.get('q_origen'),
            'destino_id': self.search_params.get('q_destino'),
            'status': self.search_params.get('q_status'),
            'fecha__gte': self.search_params.get('q_fecha_desde'),
            'fecha__lte': self.search_params.get('q_fecha_hasta'),
        }
        
        for key, value in filters.items():
            if value:
                queryset = queryset.filter(**{key: value})
                
        if filters.get('detalles__material_id'):
            queryset = queryset.distinct()
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pasamos search_params para que los inputs de fecha en el HTML se llenen solos
        context['search_params'] = self.search_params 
        
        context['prefijos'] = Empresa.objects.exclude(prefijo__isnull=True).exclude(prefijo='').values_list('prefijo', flat=True).distinct().order_by('prefijo')
        context['materiales'] = Material.objects.all().order_by('nombre')
        context['origenes'] = Lugar.objects.filter(tipo__in=['ORIGEN', 'AMBOS']).order_by('nombre')
        context['destinos'] = Lugar.objects.filter(tipo__in=['DESTINO', 'AMBOS']).order_by('nombre')
        context['estatus_choices'] = Remision.STATUS_CHOICES
        context['all_remision_numbers'] = Remision.objects.values_list('remision', flat=True).distinct().order_by('remision')
        return context
    
def calcular_siguiente_folio(prefijo):
    """
    Calcula el siguiente folio basado en números enteros para evitar
    que 'MTY-999' sea mayor que 'MTY-1000' alfabéticamente.
    """
    prefix_with_dash = f"{prefijo.strip().upper()}-"
    
    # Obtenemos solo los textos de las remisiones que coinciden con el prefijo
    remisiones_existentes = Remision.objects.filter(
        remision__startswith=prefix_with_dash
    ).values_list('remision', flat=True)

    max_num = 0
    
    for rem_str in remisiones_existentes:
        try:
            # Separamos el texto por guiones y tomamos la última parteaaaa
            # Ejemplo: "MTY-1005" -> "1005" -> 1005 (int)
            parts = rem_str.split('-')
            if len(parts) > 1:
                # Intentamos convertir a entero para comparar numéricamente
                num = int(parts[-1])
                if num > max_num:
                    max_num = num
        except ValueError:
            continue

    next_num = max_num + 1
    # Rellenamos con ceros a la izquierda (mínimo 3 dígitos)
    return f"{prefix_with_dash}{str(next_num).zfill(3)}"


@login_required
def get_next_remision_number(request, empresa_id):
    """
    Esta es la vista que llama el JavaScript para obtener el folio.
    """
    try:
        empresa = Empresa.objects.get(pk=empresa_id)
        
        if empresa.prefijo:
            # Usamos la función auxiliar que definimos arriba
            next_remision = calcular_siguiente_folio(empresa.prefijo)
            return JsonResponse({'next_remision': next_remision, 'is_manual': False})
        else:
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
        
        form = RemisionForm(request.POST, request.FILES, empresa=empresa_seleccionada)
        
        material_qs = Material.objects.filter(empresas=empresa_seleccionada) if empresa_seleccionada else Material.objects.none()
        lugar_qs = Lugar.objects.filter(empresas=empresa_seleccionada, tipo__in=['DESTINO', 'AMBOS']) if empresa_seleccionada else Lugar.objects.none()

        formset = DetalleFormSet(
            request.POST, 
            prefix='detalles', 
            form_kwargs={'material_queryset': material_qs, 'lugar_queryset': lugar_qs}
        )

        if form.is_valid() and formset.is_valid():
            # --- SOLUCIÓN CONCURRENCIA: INTENTOS AUTOMÁTICOS ---
            max_intentos = 5
            guardado_exitoso = False
            intento_actual = 0
            
            while intento_actual < max_intentos and not guardado_exitoso:
                try:
                    # Iniciamos una transacción atómica para este intento
                    with transaction.atomic(): 
                        remision = form.save(commit=False)
                        
                        # --- CÁLCULO DE FOLIO ---
                        if not empresa_seleccionada or not empresa_seleccionada.prefijo:
                            if not remision.remision:
                                raise ValidationError("La empresa no tiene prefijo y no se ingresó folio manual.")
                        else:
                            # Calculamos el folio AL MOMENTO de guardar
                            remision.remision = calcular_siguiente_folio(empresa_seleccionada.prefijo)
                        # ------------------------

                        # Intentamos guardar. Si el folio ya existe (por otro usuario), 
                        # esto lanzará IntegrityError y saltaremos al 'except'
                        remision.save() 
                        
                        formset.instance = remision
                        formset.save()
                        
                        # Guardado final para actualizar estatus
                        remision.save()
                        
                        # Actualizar inventarios
                        _update_inventory_from_remision(remision, revert=False)
                        
                        # Si llegamos aquí, todo salió bien
                        guardado_exitoso = True
                        messages.success(request, f'Remisión {remision.remision} creada exitosamente.')
                        return redirect('remision_lista')
                
                except IntegrityError:
                    # ¡AQUÍ ESTÁ LA MAGIA!
                    # Si falla porque el folio ya existe, incrementamos el contador 
                    # y el 'while' volverá a ejecutar el código, calculando el folio SIGUIENTE.
                    intento_actual += 1
                    if intento_actual >= max_intentos:
                        messages.error(request, 'El sistema está recibiendo demasiadas solicitudes simultáneas. Por favor intente de nuevo.')
                
                except Exception as e:
                    # Otros errores no relacionados con el folio rompen el bucle
                    messages.error(request, f'Ocurrió un error al guardar: {e}')
                    break 
                    
    else:
        form = RemisionForm()
        formset = DetalleFormSet(
            prefix='detalles', 
            form_kwargs={'material_queryset': Material.objects.none(), 'lugar_queryset': Lugar.objects.none()}
        )

    context = {
        'form': form, 
        'formset': formset, 
        'titulo': 'Nueva Remisión',
        'is_editing': False
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

class LugarListView(CatalogoListView): 
    model = Lugar
    template_name = 'ternium/lugar_lista.html'
    context_object_name = 'lugares'
    paginate_by = 20

    def get_queryset(self):
        # 1. Obtener queryset base
        queryset = super().get_queryset().prefetch_related('empresas')
        
        # 2. Obtener el ID de la empresa del filtro (si existe)
        empresa_id = self.request.GET.get('empresa')
        
        # 3. Filtrar
        if empresa_id:
            queryset = queryset.filter(empresas__id=empresa_id)
            
        return queryset.order_by('nombre')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pasamos la lista de todas las empresas para el "Select" del HTML
        context['empresas_list'] = Empresa.objects.all().order_by('nombre')
        
        # Pasamos la empresa seleccionada actualmente para mantener el filtro activo visualmente
        selected_empresa = self.request.GET.get('empresa')
        if selected_empresa:
            context['selected_empresa_id'] = int(selected_empresa)
            
        return context
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
    # 1. Crear el libro de trabajo
    wb = Workbook()
    ws = wb.active
    ws.title = "Remisiones"
    
    # 2. Definir Encabezados
    headers = [
        'ID', 'Remisión', 'Fecha', 'Estatus', 'Empresa',
        'Origen', 'Destino', 'Línea de Transporte', 'Operador',
        'Unidad', 'Contenedor', 'Material', 'Total Peso Carga (Ton)', 'Total Peso Descarga (Ton)',
        'Diferencia (Ton)'
    ]
    ws.append(headers)
    
    # 3. Construir la consulta Base
    queryset = Remision.objects.select_related(
        'empresa', 'origen', 'destino', 'linea_transporte', 'operador', 'unidad', 'contenedor'
    ).prefetch_related('detalles__material')

    # 4. APLICAR FILTROS (Misma lógica que en RemisionListView)
    # ---------------------------------------------------------
    q_remision = request.GET.get('q_remision')
    q_prefijo = request.GET.get('q_prefijo')
    q_material = request.GET.get('q_material')
    q_origen = request.GET.get('q_origen')
    q_destino = request.GET.get('q_destino')
    q_status = request.GET.get('q_status')
    q_fecha_desde = request.GET.get('q_fecha_desde')
    q_fecha_hasta = request.GET.get('q_fecha_hasta')

    filters = {}
    
    if q_remision:
        filters['remision__icontains'] = q_remision
    if q_prefijo:
        filters['empresa__prefijo__icontains'] = q_prefijo
    if q_material:
        filters['detalles__material_id'] = q_material
    if q_origen:
        filters['origen_id'] = q_origen
    if q_destino:
        filters['destino_id'] = q_destino
    if q_status:
        filters['status'] = q_status
    if q_fecha_desde:
        filters['fecha__gte'] = q_fecha_desde
    if q_fecha_hasta:
        filters['fecha__lte'] = q_fecha_hasta

    # Aplicamos los filtros acumulados
    if filters:
        queryset = queryset.filter(**filters)
    
    # Si filtramos por detalles (material), evitamos duplicados
    if q_material:
        queryset = queryset.distinct()

    # 5. ORDENAMIENTO (Mayor a Menor por ID)
    # ---------------------------------------
    # '-pk' asegura que salgan los registros más nuevos primero.
    queryset = queryset.order_by('-pk')
    
    # 6. Iterar y escribir datos en Excel
    for remision in queryset:
        # Obtener nombres de materiales concatenados
        materiales_str = ", ".join([d.material.nombre for d in remision.detalles.all() if d.material])

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
            materiales_str,
            remision.total_peso_ld,
            remision.total_peso_dlv,
            remision.diff
        ])

    # 7. Formato de Tabla Excel (Estilos)
    last_col_letter = get_column_letter(len(headers))
    last_row = ws.max_row
    
    # Validamos que haya datos antes de crear la tabla para evitar error de Excel corrupto
    if last_row > 1:
        table_ref = f"A1:{last_col_letter}{last_row}"
        tabla = Table(displayName="TablaRemisiones", ref=table_ref)
        style = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
        tabla.tableStyleInfo = style
        ws.add_table(tabla)

    # 8. Ajuste de anchos y centrado
    center_alignment = Alignment(horizontal='center', vertical='center')
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            cell.alignment = center_alignment
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 4)
        ws.column_dimensions[column].width = adjusted_width

    # 9. Retornar respuesta HTTP
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
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
from .models import RegistroLogistico, EntradaMaquila, InventarioPatio # Asegúrate de importar tus modelos
import boto3
from botocore.exceptions import NoCredentialsError, BotoCoreError
import json
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
@permission_required('ternium.acceso_ia', raise_exception=True) # <--- PROTECCIÓN
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
    
    # Inicializamos el formulario de contraseña (se usará en GET y POST)
    password_form = PasswordChangeForm(user)

    if request.method == 'POST':
        # --- CASO 1: ACTUALIZAR INFORMACIÓN DEL PERFIL ---
        if 'update_profile' in request.POST:
            try:
                # Actualizar datos del modelo User
                user.first_name = request.POST.get('first_name', user.first_name)
                user.last_name = request.POST.get('last_name', user.last_name)
                user.email = request.POST.get('email', user.email)
                user.save()

                # Actualizar datos del modelo Profile (ternium_profile)
                if hasattr(user, 'ternium_profile'):
                    profile = user.ternium_profile
                    profile.telefono = request.POST.get('telefono', profile.telefono)
                    profile.area = request.POST.get('area', profile.area)
                    profile.empresa = request.POST.get('empresa', profile.empresa)
                    
                    # Manejo de archivo (Avatar)
                    if 'avatar' in request.FILES:
                        profile.avatar = request.FILES['avatar']
                    
                    profile.save()
                
                messages.success(request, 'Tu información de perfil ha sido actualizada.')
                return redirect('perfil')
            except Exception as e:
                messages.error(request, f'Ocurrió un error al actualizar el perfil: {e}')

        # --- CASO 2: CAMBIAR CONTRASEÑA ---
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                # Importante: Mantener la sesión activa tras cambiar contraseña
                update_session_auth_hash(request, user) 
                messages.success(request, 'Tu contraseña ha sido actualizada correctamente.')
                return redirect('perfil')
            else:
                messages.error(request, 'Error al cambiar contraseña. Revisa los campos.')

    # =======================================================
    # LÓGICA PARA MOSTRAR PERMISOS (SOLICITADO)
    # =======================================================
    permisos_usuario = user.get_all_permissions()
    lista_permisos_legibles = []
    
    # Diccionario para traducir los códigos técnicos a texto amigable
    nombres_amigables = {
        # Permisos Ternium / Operaciones
        'ternium.acceso_dashboard_patio': 'Dashboard de Patios',
        'ternium.acceso_remisiones': 'Módulo de Remisiones',
        'ternium.acceso_ia': 'Asistente de IA',
        'ternium.acceso_catalogos': 'Catálogos Operativos',
        'ternium.acceso_reportes_kpi': 'Reportes y KPIs',
        'ternium.view_ternium_module': 'Logística General',
        
        # Permisos Compras
        'compras.acceso_compras': 'Gestión de Compras',
        'compras.aprobar_solicitudes': 'Aprobar Solicitudes',
        
        # Permisos CXP
        'cuentas_por_pagar.acceso_cxp': 'Cuentas por Pagar',
        'cuentas_por_pagar.autorizar_pagos': 'Autorizar Pagos',
    }

    for perm_code in permisos_usuario:
        if perm_code in nombres_amigables:
            lista_permisos_legibles.append(nombres_amigables[perm_code])
        # Opcional: Si quieres mostrar otros permisos estándar de Django, descomenta esto:
        # else:
        #     lista_permisos_legibles.append(perm_code.split('.')[1].replace('_', ' ').capitalize())

    lista_permisos_legibles.sort()

    context = {
        'password_form': password_form,
        'user_groups': user.groups.all(),
        'permisos_detallados': lista_permisos_legibles, # <--- Enviamos la lista al HTML
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

@login_required
@permission_required('ternium.acceso_reportes_kpi', raise_exception=True) # <--- PROTECCIÓN
def dashboard_analisis_view(request):
    
    # 1. FILTROS DE TIEMPO
    now = timezone.now()
    
    # Filtro Global de Maquila (Entradas)
    entradas_qs = EntradaMaquila.objects.all()
    
    # Filtro Global de Logística (Salidas)
    logistica_qs = RegistroLogistico.objects.filter(status='TERMINADO')

    # ==========================================
    # 1. CÁLCULO DE KPIS GLOBALES (MES Y ACUMULADO)
    # ==========================================
    
    # Rango de tiempo: Mes actual y Año actual
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # 1.1 KPIS DE VOLUMEN
    
    # Maquila (Entradas / Compras) -> FloatField
    entradas_mes = entradas_qs.filter(fecha_ingreso__gte=start_of_month)
    entradas_year = entradas_qs.filter(fecha_ingreso__gte=start_of_year)
    
    # Aseguramos que sean float
    toneladas_compradas_mes = float(entradas_mes.aggregate(Sum('peso_neto'))['peso_neto__sum'] or 0)
    toneladas_compradas_year = float(entradas_year.aggregate(Sum('peso_neto'))['peso_neto__sum'] or 0)
    
    # Logística (Salidas / Ventas) -> DecimalField
    salidas_mes = logistica_qs.filter(fecha_carga__gte=start_of_month)
    salidas_year = logistica_qs.filter(fecha_carga__gte=start_of_year)
    
    # CORRECCIÓN DE ERROR: Convertimos Decimal a float explícitamente
    toneladas_vendidas_mes = float(salidas_mes.aggregate(Sum('toneladas_remisionadas'))['toneladas_remisionadas__sum'] or 0)
    toneladas_vendidas_year = float(salidas_year.aggregate(Sum('toneladas_remisionadas'))['toneladas_remisionadas__sum'] or 0)

    # Inventario Actual
    inventario_agg = InventarioPatio.objects.aggregate(total_kg=Coalesce(Sum('cantidad'), 0.0, output_field=FloatField()))
    inventario_actual_tons = float(inventario_agg['total_kg']) / 1000 if inventario_agg['total_kg'] else 0

    # Mermas / Pérdidas (Acumulado)
    merma_maq_tons = float(entradas_qs.aggregate(
        merma_tons=Sum(F('peso_remision') - F('peso_neto'), output_field=FloatField())
    )['merma_tons'] or 0)
    
    merma_log_tons = float(logistica_qs.aggregate(
        merma_tons=Sum(F('toneladas_remisionadas') - F('toneladas_recibidas'), output_field=FloatField())
    )['merma_tons'] or 0)
    
    # Ahora la suma funciona porque ambos son float
    merma_total_global = merma_maq_tons + merma_log_tons
    total_manejado = toneladas_compradas_year + toneladas_vendidas_year
    
    porcentaje_merma_global = (merma_total_global / total_manejado) * 100 if total_manejado > 0 else 0

    # 1.2 KPIS DE OPERACIÓN
    tiempo_almacenamiento_dias = 0 # Valor placeholder
    movimientos_totales = entradas_qs.count() + logistica_qs.count()

    # ==========================================
    # 2. GRÁFICAS PRINCIPALES
    # ==========================================

    # Volumen comprado vs vendido (Línea Mensual)
    compras_mensuales = entradas_qs.annotate(
        mes=TruncMonth('fecha_ingreso')
    ).values('mes').annotate(
        toneladas=Sum('peso_neto')
    ).order_by('mes')

    ventas_mensuales = logistica_qs.annotate(
        mes=TruncMonth('fecha_carga')
    ).values('mes').annotate(
        toneladas=Sum('toneladas_remisionadas')
    ).order_by('mes')
    
    # Consolidar datos mensuales
    timeline_data = {}
    for entry in compras_mensuales:
        if entry['mes']:
            mes_str = entry['mes'].strftime("%Y-%m")
            # Convertimos a float
            timeline_data[mes_str] = {'comprado': float(entry['toneladas'] or 0), 'vendido': 0.0}

    for entry in ventas_mensuales:
        if entry['mes']:
            mes_str = entry['mes'].strftime("%Y-%m")
            val_vendido = float(entry['toneladas'] or 0) # Convertimos Decimal a float
            if mes_str in timeline_data:
                timeline_data[mes_str]['vendido'] = val_vendido
            else:
                timeline_data[mes_str] = {'comprado': 0.0, 'vendido': val_vendido}
    
    sorted_timeline_keys = sorted(timeline_data.keys())
    chart_timeline_labels = sorted_timeline_keys
    chart_timeline_comprado = [timeline_data[k]['comprado'] for k in sorted_timeline_keys]
    chart_timeline_vendido = [timeline_data[k]['vendido'] for k in sorted_timeline_keys]

    # Pérdidas por mes (Proxy usando Entradas)
    merma_mensual = entradas_qs.annotate(
        mes=TruncMonth('fecha_ingreso')
    ).values('mes').annotate(
        avg_merma=Avg('porcentaje_faltante')
    ).order_by('mes')
    
    chart_merma_labels = [item['mes'].strftime("%Y-%m") for item in merma_mensual if item['mes']]
    chart_merma_data = [float(item['avg_merma'] or 0) for item in merma_mensual if item['mes']]


    # ==========================================
    # 3. ANÁLISIS POR MATERIAL
    # ==========================================
    
    materiales_entradas = entradas_qs.values('calidad').annotate(comprado=Sum('peso_neto'), merma_count=Count('id', filter=Q(alerta=True))).order_by('-comprado')
    
    materiales_salidas = logistica_qs.values('material__nombre').annotate(vendido=Sum('toneladas_remisionadas')).order_by('-vendido')

    inventario_por_material = InventarioPatio.objects.values('material__nombre').annotate(
        stock=Sum('cantidad')
    )

    # Consolidar Materiales
    material_analysis = {}
    for item in materiales_entradas:
        calidad = item['calidad'] or "Sin Especificar"
        # Casteo explícito a float
        material_analysis[calidad] = {
            'comprado': float(item['comprado'] or 0), 
            'vendido': 0.0, 
            'merma_incidencias': item['merma_count'], 
            'stock': 0.0
        }
        
    for item in materiales_salidas:
        name = item['material__nombre'] or "Sin Especificar"
        val_vendido = float(item['vendido'] or 0) # Casteo Decimal -> Float
        
        if name in material_analysis:
            material_analysis[name]['vendido'] = val_vendido
        else:
            material_analysis[name] = {
                'comprado': 0.0, 
                'vendido': val_vendido, 
                'merma_incidencias': 0, 
                'stock': 0.0
            }
            
    for item in inventario_por_material:
         name = item['material__nombre'] or "Sin Especificar"
         stock_ton = float(item['stock']) / 1000 if item['stock'] else 0
         if name in material_analysis:
             material_analysis[name]['stock'] = stock_ton
    
    # Ahora la suma en la lambda function funcionará porque ambos valores son float
    sorted_material_analysis = sorted(material_analysis.items(), key=lambda item: item[1]['comprado'] + item[1]['vendido'], reverse=True)[:10]

    # ==========================================
    # 4. RANKING DE PROVEEDORES Y CLIENTES
    # ==========================================

    top_proveedores = entradas_qs.values('transporte').annotate(
        toneladas=Sum('peso_neto'),
        viajes=Count('id'),
        avg_merma_perc=Avg('porcentaje_faltante')
    ).order_by('-toneladas')[:5]

    top_clientes = logistica_qs.values('transportista__nombre').annotate(
        toneladas=Sum('toneladas_remisionadas'),
        viajes=Count('id')
    ).order_by('-toneladas')[:5]

    # ==========================================
    # 5. LISTA DE BOLETAS/REMISIONES
    # ==========================================
    
    ultimas_entradas = entradas_qs.order_by('-fecha_ingreso').values(folio=F('c_id_remito'), calidad_mat=F('calidad'), peso=F('peso_neto'), trans=F('transporte'))[:10]
    
    ultimas_salidas = logistica_qs.order_by('-fecha_carga').values('remision', 'material__nombre', 'toneladas_remisionadas', 'transportista__nombre')[:10]
    
    
    context = {
        'kpi_comp_mes': round(toneladas_compradas_mes, 2),
        'kpi_comp_year': round(toneladas_compradas_year, 2),
        'kpi_vent_mes': round(toneladas_vendidas_mes, 2),
        'kpi_vent_year': round(toneladas_vendidas_year, 2),
        'kpi_inv_act': round(inventario_actual_tons, 2),
        'kpi_merma_perc': round(porcentaje_merma_global, 2),
        'kpi_merma_tons': round(merma_total_global, 2),
        'kpi_movs_total': movimientos_totales,
        'kpi_almacen_dias': tiempo_almacenamiento_dias,
        
        'chart_tl_labels': json.dumps(chart_timeline_labels),
        'chart_tl_comprado': json.dumps(chart_timeline_comprado),
        'chart_tl_vendido': json.dumps(chart_timeline_vendido),
        'chart_merma_labels': json.dumps(chart_merma_labels),
        'chart_merma_data': json.dumps(chart_merma_data),
        
        'material_analysis': sorted_material_analysis,
        'top_proveedores': top_proveedores,
        'top_clientes': top_clientes,
        
        'ultimas_entradas': list(ultimas_entradas),
        'ultimas_salidas': list(ultimas_salidas),
    }

    return render(request, 'ternium/dashboard_analisis.html', context)# nueva actuaolizacopon


from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
import pandas as pd

# Importa tus modelos
from .models import Empresa, Remision, Material, Operador, LineaTransporte, Unidad, Lugar, DetalleRemision, Cliente
from .forms import ImportarRemisionesForm

@login_required
def importar_remisiones_excel(request):
    lista_errores = [] 
    
    if request.method == 'POST':
        form = ImportarRemisionesForm(request.POST, request.FILES)
        
        if form.is_valid():
            archivo = request.FILES['archivo_excel']
            
            try:
                # 1. Leer el Excel
                df = pd.read_excel(archivo)
                df.columns = df.columns.str.strip().str.lower()
                
                conteo_creadas = 0
                conteo_actualizadas = 0

                # --- BUSCAR EMPRESA MONTERREY ---
                empresa_mty = Empresa.objects.filter(
                    Q(nombre__icontains="Monterrey") | Q(prefijo__icontains="MTY")
                ).first()
                
                if not empresa_mty:
                    messages.error(request, "Error Crítico: No se encontró la empresa 'Monterrey' o 'MTY'.")
                    return render(request, 'ternium/importar_remisiones.html', {'form': form})

                # --- ITERAR FILAS ---
                for index, row in df.iterrows():
                    fila_excel = index + 2
                    try:
                        # VALIDAR REMISIÓN
                        remision_num = str(row.get('remision', '')).strip()
                        if not remision_num or remision_num.lower() == 'nan':
                            continue 

                        # =======================================================
                        #      AUTO-ALTA DE CATÁLOGOS
                        # =======================================================

                        # 1. MATERIAL
                        nombre_material = str(row.get('material', 'Genérico')).strip()
                        material_obj, _ = Material.objects.get_or_create(
                            nombre__iexact=nombre_material, defaults={'nombre': nombre_material}
                        )
                        material_obj.empresas.add(empresa_mty) 

                        # 2. OPERADOR
                        nombre_operador = str(row.get('operador', 'Sin Operador')).strip()
                        operador_obj, _ = Operador.objects.get_or_create(
                            nombre__iexact=nombre_operador, defaults={'nombre': nombre_operador}
                        )
                        if hasattr(operador_obj, 'empresas'): operador_obj.empresas.add(empresa_mty)

                        # 3. LÍNEA DE TRANSPORTE
                        nombre_linea = str(row.get('linea de transporte', 'Particular')).strip()
                        linea_obj, _ = LineaTransporte.objects.get_or_create(
                            nombre__iexact=nombre_linea, defaults={'nombre': nombre_linea}
                        )
                        if hasattr(linea_obj, 'empresas'): linea_obj.empresas.add(empresa_mty)

                        # 4. UNIDAD
                        tracto_id = str(row.get('unidad', 'S/N')).strip()
                        unidad_obj, _ = Unidad.objects.get_or_create(
                            internal_id__iexact=tracto_id, defaults={'internal_id': tracto_id}
                        )
                        if hasattr(unidad_obj, 'empresas'): unidad_obj.empresas.add(empresa_mty)

                        # 5. ORIGEN (Lugar)
                        nombre_origen = str(row.get('origen', 'Origen Desconocido')).strip()
                        origen_obj, _ = Lugar.objects.get_or_create(
                            nombre__iexact=nombre_origen, defaults={'nombre': nombre_origen, 'tipo': 'ORIGEN'}
                        )
                        if hasattr(origen_obj, 'empresas'): origen_obj.empresas.add(empresa_mty)

                        # 6. DESTINO (Lugar) -> ESTE ES EL CRUCIAL PARA EL DETALLE
                        nombre_destino = str(row.get('destino', 'Destino Desconocido')).strip()
                        destino_obj, _ = Lugar.objects.get_or_create(
                            nombre__iexact=nombre_destino, defaults={'nombre': nombre_destino, 'tipo': 'DESTINO'}
                        )
                        if hasattr(destino_obj, 'empresas'): destino_obj.empresas.add(empresa_mty)
                        
                        # 7. CLIENTE (Modelo Cliente para cabecera Remisión)
                        cliente_remision_obj, _ = Cliente.objects.get_or_create(
                            nombre__iexact=nombre_destino, defaults={'nombre': nombre_destino}
                        )
                        if hasattr(cliente_remision_obj, 'empresas'): cliente_remision_obj.empresas.add(empresa_mty)

                        # 8. FECHA
                        fecha_str = row.get('fecha')
                        try: fecha_remision = pd.to_datetime(fecha_str).date()
                        except: fecha_remision = timezone.now().date()

                        # =======================================================
                        #      CREAR O ACTUALIZAR (UPSERT)
                        # =======================================================
                        with transaction.atomic():
                            remision_existente = Remision.objects.filter(remision=remision_num).first()
                            
                            if remision_existente:
                                # --- ACTUALIZAR ---
                                remision_obj = remision_existente
                                remision_obj.empresa = empresa_mty
                                remision_obj.fecha = fecha_remision
                                remision_obj.operador = operador_obj
                                remision_obj.linea_transporte = linea_obj
                                remision_obj.unidad = unidad_obj
                                remision_obj.origen = origen_obj
                                remision_obj.destino = destino_obj
                                remision_obj.cliente = cliente_remision_obj
                                remision_obj.descripcion = "Actualizado vía Excel"
                                remision_obj.save()
                                
                                # Limpiar detalles previos para re-insertar
                                DetalleRemision.objects.filter(remision=remision_obj).delete()
                                conteo_actualizadas += 1
                            else:
                                # --- CREAR ---
                                remision_obj = Remision.objects.create(
                                    empresa=empresa_mty,
                                    remision=remision_num,
                                    fecha=fecha_remision,
                                    operador=operador_obj,
                                    linea_transporte=linea_obj,
                                    unidad=unidad_obj,
                                    origen=origen_obj,
                                    destino=destino_obj,
                                    cliente=cliente_remision_obj,
                                    status='PENDIENTE', # Temporal
                                    descripcion="Importación Excel"
                                )
                                conteo_creadas += 1

                            # --- FORZAR ESTATUS A TERMINADO ---
                            # Usamos update() para saltarnos validaciones de fotos
                            Remision.objects.filter(pk=remision_obj.pk).update(status='TERMINADO')

                            # --- DETALLE DE PESOS ---
                            val_peso_origen = row.get('peso carga', 0) 
                            val_peso_destino = row.get('peso', 0)
                            
                            try: p_ld = float(val_peso_origen) if pd.notnull(val_peso_origen) else 0.0
                            except: p_ld = 0.0
                            try: p_dlv = float(val_peso_destino) if pd.notnull(val_peso_destino) else 0.0
                            except: p_dlv = 0.0

                            # --- AQUÍ GUARDAMOS EL CAMPO CLIENTE EN EL DETALLE ---
                            # Usamos 'destino_obj' porque tu modelo DetalleRemision pide un LUGAR
                            DetalleRemision.objects.create(
                                remision=remision_obj,
                                material=material_obj,
                                cliente=destino_obj,  # <--- Asignación explícita del Lugar (Destino)
                                peso_ld=p_ld,
                                peso_dlv=p_dlv
                            )

                    except Exception as e:
                        lista_errores.append(f"Fila {fila_excel}: Error inesperado - {str(e)}")

                # --- MENSAJES FINALES ---
                if conteo_creadas > 0 or conteo_actualizadas > 0:
                    messages.success(request, f"✅ Proceso terminado: {conteo_creadas} creadas, {conteo_actualizadas} actualizadas (Status: TERMINADO).")
                
                if lista_errores:
                    messages.warning(request, f"⚠ Errores en {len(lista_errores)} filas.")
                    return render(request, 'ternium/importar_remisiones.html', {
                        'form': form,
                        'lista_errores': lista_errores
                    })
                
                return redirect('remision_lista')

            except Exception as e:
                messages.error(request, f"❌ Error general: {e}")
                return render(request, 'ternium/importar_remisiones.html', {'form': form})
        else:
            messages.error(request, "Formulario inválido.")
    else:
        form = ImportarRemisionesForm()

    return render(request, 'ternium/importar_remisiones.html', {'form': form})
# --- AGREGAR AL FINAL DE ternium/views.py ---


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, FloatField, F, Q
from django.db.models.functions import TruncMonth, Coalesce
from django.utils import timezone
import json

from .models import Remision, Lugar

@login_required
def dashboard_remisiones_view(request):
    now = timezone.now()
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # 0. FILTROS DE URL
    filtro_origen_id = request.GET.get('origen')
    filtro_destino_id = request.GET.get('destino')

    # 1. BASE COMPLETA (INCLUYE PATIOS)
    # Esta base tiene TODO lo que está Terminado/Auditado y con Peso > 0
    qs_completa = Remision.objects.filter(
        status__in=['TERMINADO', 'AUDITADO'],
        detalles__peso_ld__gt=0,
        detalles__peso_dlv__gt=0
    )

    # Aplicamos filtros de usuario a la base completa
    if filtro_origen_id:
        qs_completa = qs_completa.filter(origen_id=filtro_origen_id)
    if filtro_destino_id:
        qs_completa = qs_completa.filter(destino_id=filtro_destino_id)

    # =======================================================
    # LÓGICA DE NO DUPLICIDAD (CLEAN DATA)
    # =======================================================
    # Regla: 
    # - Si va a PATIO (Destino='Patio') -> NO CONTAR (Es entrada/stock)
    # - Si sale de PATIO o va directo -> CONTAR (Es salida/venta)
    #
    # Esto se usará para: Gráficas, Materiales y KPIs para que todo cuadre.
    qs_sin_duplicados = qs_completa.exclude(destino__nombre__icontains='patio')

    # =======================================================
    # 3. GRÁFICA EVOLUCIÓN
    # =======================================================
    timeline_qs = qs_sin_duplicados.annotate(mes=TruncMonth('fecha')).values('mes').annotate(
        carga=Coalesce(Sum('detalles__peso_ld'), 0.0, output_field=FloatField()),
        descarga=Coalesce(Sum('detalles__peso_dlv'), 0.0, output_field=FloatField())
    ).order_by('mes')

    chart_labels = []
    chart_carga = []
    chart_descarga = []
    for entry in timeline_qs:
        if entry['mes']:
            chart_labels.append(entry['mes'].strftime("%Y-%m"))
            chart_carga.append(entry['carga'])
            chart_descarga.append(entry['descarga'])

    # =======================================================
    # 4. ANÁLISIS MATERIALES (MODIFICADO: Usa qs_sin_duplicados)
    # =======================================================
    # Antes usaba qs_analisis, ahora usa la lógica estricta de no duplicar patios
    materiales_data = qs_sin_duplicados.values('detalles__material__nombre').annotate(
        total_carga=Coalesce(Sum('detalles__peso_ld'), 0.0, output_field=FloatField()),
        total_descarga=Coalesce(Sum('detalles__peso_dlv'), 0.0, output_field=FloatField())
    ).order_by('-total_carga')

    mat_labels = []
    mat_carga_data = []
    mat_descarga_data = []
    
    lista_materiales = []
    # Evitamos división por cero si no hay datos
    total_volumen = materiales_data[0]['total_carga'] if (materiales_data and materiales_data[0]['total_carga'] > 0) else 1

    for mat in materiales_data:
        c = mat['total_carga']
        d = mat['total_descarga']
        n = mat['detalles__material__nombre']
        diff = c - d  # <--- CÁLCULO DE DIFERENCIA
        
        mat_labels.append(n)
        mat_carga_data.append(c)
        mat_descarga_data.append(d)
        
        lista_materiales.append({
            'nombre': n,
            'carga': c,
            'descarga': d,
            'diff': diff,  # <--- AGREGADO AL DICCIONARIO
            'porcentaje_relativo': (c / total_volumen * 100)
        })

    # =======================================================
    # 5. DATA PARA EL DESLIZADOR (OFFCANVAS) (MODIFICADO)
    # =======================================================
    # También debe usar qs_sin_duplicados para que coincida con la tabla
    raw_details = qs_sin_duplicados.values(
        'fecha', 'remision', 'origen__nombre', 'destino__nombre', 
        'detalles__material__nombre', 'detalles__peso_ld', 'detalles__peso_dlv'
    ).order_by('-fecha')

    materiales_detalle_map = {}
    for item in raw_details:
        mat_nombre = item['detalles__material__nombre'] or "Sin Material"
        if mat_nombre not in materiales_detalle_map:
            materiales_detalle_map[mat_nombre] = []
        
        # Conversiones y cálculos
        p_carga = float(item['detalles__peso_ld'] or 0)
        p_descarga = float(item['detalles__peso_dlv'] or 0)
        faltante = p_carga - p_descarga
        
        # Calcular porcentaje de faltante (evitando división por cero)
        porcentaje = (faltante / p_carga * 100) if p_carga > 0 else 0.0
        
        materiales_detalle_map[mat_nombre].append({
            'fecha': item['fecha'].strftime("%d/%m/%Y"),
            'remision': item['remision'],
            'material': mat_nombre,
            'origen': item['origen__nombre'],
            'destino': item['destino__nombre'],
            'carga': p_carga,
            'descarga': p_descarga,
            'faltante': faltante,
            'porcentaje': porcentaje
        })

    # =======================================================
    # 6. RANKING OPERADORES (Mantiene qs_completa)
    # =======================================================
    # Aquí SIEMPRE usamos la completa porque al operador se le paga todo el movimiento
    operadores_data = qs_completa.values('operador__nombre').annotate(
        total_viajes=Count('id', distinct=True),
        total_cargado=Coalesce(Sum('detalles__peso_ld'), 0.0, output_field=FloatField()),
        
        # CÁLCULO DE MERMA ACUMULADA (Solo suma si Carga > Descarga)
        merma_acumulada=Sum(
            Case(
                When(
                    detalles__peso_ld__gt=F('detalles__peso_dlv'),
                    then=F('detalles__peso_ld') - F('detalles__peso_dlv')
                ),
                default=0.0,
                output_field=FloatField()
            )
        )
    ).order_by('-merma_acumulada')[:50] # Ordenamos por quién ha perdido más material

    ranking_operadores = []
    
    for op in operadores_data:
        cargado = op['total_cargado'] or 0
        merma_real = op['merma_acumulada'] or 0 # Esta es la suma pura de faltantes
        
        # Porcentaje de Riesgo: Cuánto material pierde del total que mueve
        riesgo_perc = ((merma_real / cargado) * 100) if cargado > 0 else 0
        
        # Obtener detalle de viajes CON FALTANTE para el deslizador
        # Filtramos merma > 0.02 (20kg) para limpiar tolerancias mínimas
        viajes_con_faltante = qs_completa.filter(
            operador__nombre=op['operador__nombre'],
            detalles__peso_ld__gt=F('detalles__peso_dlv') + 0.02 
        ).values(
            'fecha', 'remision', 'detalles__material__nombre',
            'origen__nombre', 'destino__nombre',
            'detalles__peso_ld', 'detalles__peso_dlv'
        ).order_by('-fecha')

        detalles_list = []
        for v in viajes_con_faltante:
            p_carga = float(v['detalles__peso_ld'] or 0)
            p_descarga = float(v['detalles__peso_dlv'] or 0)
            faltante = p_carga - p_descarga
            
            detalles_list.append({
                'fecha': v['fecha'].strftime("%d/%m/%Y"),
                'remision': v['remision'],
                'material': v['detalles__material__nombre'] or 'S/M',
                'origen': v['origen__nombre'],
                'destino': v['destino__nombre'],
                'carga': p_carga,
                'descarga': p_descarga,
                'faltante': round(faltante, 3)
            })

        ranking_operadores.append({
            'nombre': op['operador__nombre'] or "S/N", 
            'viajes': op['total_viajes'],
            'cargado': cargado,
            'diff': merma_real, # Ahora 'diff' representa solo pérdida
            'riesgo_perc': riesgo_perc,
            'json_detalles': json.dumps(detalles_list)
        })

    # =======================================================
    # 7. PENDIENTES
    # =======================================================
    pendientes_qs = Remision.objects.filter(status='PENDIENTE')
    if filtro_origen_id: pendientes_qs = pendientes_qs.filter(origen_id=filtro_origen_id)
    if filtro_destino_id: pendientes_qs = pendientes_qs.filter(destino_id=filtro_destino_id)

    resumen_pend = pendientes_qs.aggregate(
        total_carga=Coalesce(Sum('detalles__peso_ld'), 0.0, output_field=FloatField()),
        total_descarga=Coalesce(Sum('detalles__peso_dlv'), 0.0, output_field=FloatField())
    )
    
    lista_pendientes = []
    hoy_date = now.date()
    for rem in pendientes_qs:
        try: det=rem.detalles.first(); p_ld=float(det.peso_ld); p_dlv=float(det.peso_dlv)
        except: p_ld=0; p_dlv=0
        dias = (hoy_date - rem.fecha).days
        if p_dlv == 0: e="En Tránsito"; c="bg-secondary"
        elif abs(p_ld-p_dlv)>0.1: e="Diferencia"; c="bg-warning text-dark"
        else: e="Por Cerrar"; c="bg-info"
        
        lista_pendientes.append({
            'remision': rem.remision, 'fecha': rem.fecha, 'dias': dias,
            'empresa': rem.empresa.nombre if rem.empresa else '', 
            'cliente': rem.cliente.nombre if rem.cliente else '',
            'unidad': rem.unidad.internal_id if rem.unidad else '', 
            'peso_origen': p_ld, 'peso_destino': p_dlv,
            'estado_txt': e, 'badge_cls': c
        })
    lista_pendientes.sort(key=lambda x: x['dias'], reverse=True)

    # =======================================================
    # 8. KPIS & CONTEXTO FINAL (Usamos qs_sin_duplicados)
    # =======================================================
    # Actualizamos los KPIs generales para que coincidan con la gráfica y tabla
    kpis_year = qs_sin_duplicados.filter(fecha__gte=start_of_year).aggregate(
        total_carga=Coalesce(Sum('detalles__peso_ld'), 0.0, output_field=FloatField()),
        total_descarga=Coalesce(Sum('detalles__peso_dlv'), 0.0, output_field=FloatField())
    )

    origenes_list = Lugar.objects.filter(tipo__in=['ORIGEN', 'AMBOS']).order_by('nombre')
    destinos_list = Lugar.objects.filter(tipo__in=['DESTINO', 'AMBOS']).order_by('nombre')

    context = {
        'kpi_carga': round(kpis_year['total_carga'], 2), 
        'kpi_descarga': round(kpis_year['total_descarga'], 2),
        'kpi_merma_ton': round(kpis_year['total_carga'] - kpis_year['total_descarga'], 2),
        
        # Gráficas
        'chart_labels': json.dumps(chart_labels), 
        'chart_carga': json.dumps(chart_carga), 
        'chart_descarga': json.dumps(chart_descarga),
        
        # Materiales
        'mat_labels': json.dumps(mat_labels),
        'mat_carga_data': json.dumps(mat_carga_data),
        'mat_descarga_data': json.dumps(mat_descarga_data),
        'lista_materiales': lista_materiales,
        'materiales_detalle_json': json.dumps(materiales_detalle_map),

        # Filtros y Tablas
        'origenes_list': origenes_list, 'destinos_list': destinos_list,
        'filtro_origen_sel': int(filtro_origen_id) if filtro_origen_id else None,
        'filtro_destino_sel': int(filtro_destino_id) if filtro_destino_id else None,
        'ranking_operadores': ranking_operadores,
        'pendientes_carga_total': resumen_pend['total_carga'], 
        'pendientes_descarga_total': resumen_pend['total_descarga'],
        'lista_pendientes': lista_pendientes,
    }
    
    if context['kpi_carga'] > 0:
        context['kpi_merma_perc'] = round((context['kpi_merma_ton'] / context['kpi_carga']) * 100, 2)
    else:
        context['kpi_merma_perc'] = 0

    return render(request, 'ternium/dashboard_remisiones.html', context)


from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from .forms import CustomLoginForm  # <--- CORREGIDO

class CustomLoginView(LoginView):
    form_class = CustomLoginForm    # <--- CORREGIDO
    template_name = 'registration/login.html'

    def form_valid(self, form):
        # Lógica de "Recordar sesión"
        remember_me = form.cleaned_data.get('remember_me')
        if not remember_me:
            self.request.session.set_expiry(0)
        else:
            self.request.session.modified = True
        
        return super().form_valid(form)
    
    
@login_required
@require_POST
def cancelar_remision(request, pk):
    """
    Cancela una remisión, revierte el movimiento de inventario 
    y evita que aparezca en el Dashboard.
    """
    remision = get_object_or_404(Remision, pk=pk)
    
    # Validaciones de seguridad
    if remision.status == 'AUDITADO':
        messages.error(request, 'No se puede cancelar una remisión que ya fue auditada.')
        return redirect('remision_lista')
        
    if remision.status == 'CANCELADO':
        messages.warning(request, 'Esta remisión ya estaba cancelada.')
        return redirect('remision_lista')

    try:
        with transaction.atomic():
            # 1. Revertir el inventario (Devolver el material al origen/destino)
            # Esto es crucial para que los stocks cuadren.
            _update_inventory_from_remision(remision, revert=True)
            
            # 2. Cambiar estatus
            remision.status = 'CANCELADO'
            
            # 3. Opcional: Agregar nota automática en descripción
            usuario = request.user.username
            fecha = timezone.now().strftime("%d/%m/%Y %H:%M")
            remision.descripcion += f" [CANCELADA por {usuario} el {fecha}]"
            
            remision.save()
            
        messages.success(request, f'La remisión {remision.remision} ha sido CANCELADA y el inventario revertido.')
        
    except Exception as e:
        messages.error(request, f'Error al cancelar: {e}')
        
    return redirect('remision_lista')

@xframe_options_exempt  # <--- AGREGA ESTA LÍNEA AQUÍ
@login_required
def detalle_remision(request, pk):
    remision = get_object_or_404(Remision, pk=pk)
    return render(request, 'ternium/detalle_remision.html', {'remision': remision})


from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.styles import Alignment, PatternFill, Font
from openpyxl.utils import get_column_letter
import datetime

@login_required
def export_catalogo_excel(request, model_name):
    """
    Exporta a Excel cualquier catálogo simple basándose en el nombre del modelo.
    """
    # 1. Configuración de Modelos y Columnas
    config = {
        'empresa': {
            'model': Empresa,
            'headers': ['ID', 'Nombre', 'Prefijo', 'Contacto', 'Teléfono', 'Email'],
            'fields': ['id', 'nombre', 'prefijo', 'contacto_principal', 'telefono', 'email']
        },
        'lugar': {
            'model': Lugar,
            'headers': ['ID', 'Nombre', 'Tipo', 'Es Patio', 'RFC', 'Razón Social', 'Dirección Completa'],
            'fields': ['id', 'nombre', 'tipo', 'es_patio', 'rfc', 'razon_social', 'direccion_completa'] # direccion_completa es un método
        },
        'lineatransporte': {
            'model': LineaTransporte,
            'headers': ['ID', 'Nombre', 'Empresas Asociadas'],
            'fields': ['id', 'nombre', 'empresas_str'] # Calculado
        },
        'operador': {
            'model': Operador,
            'headers': ['ID', 'Nombre'],
            'fields': ['id', 'nombre']
        },
        'material': {
            'model': Material,
            'headers': ['ID', 'Nombre', 'Clave SAT', 'Unidad SAT'],
            'fields': ['id', 'nombre', 'clave_sat', 'clave_unidad_sat']
        },
        'unidad': {
            'model': Unidad,
            'headers': ['ID Interno', 'Placas', 'Marca/Modelo', 'Tipo', 'Estatus', 'Dueño'],
            'fields': ['internal_id', 'license_plate', 'make_model', 'asset_type', 'operational_status', 'ownership']
        },
        'contenedor': {
            'model': Contenedor,
            'headers': ['ID/Nombre', 'Placas'],
            'fields': ['nombre', 'placas']
        }
    }

    conf = config.get(model_name.lower())
    if not conf:
        messages.error(request, "Modelo no válido para exportación.")
        return redirect('home')

    # 2. Obtener Queryset (Filtrado por Empresa si aplica)
    model = conf['model']
    queryset = model.objects.all()
    
    # Filtro por empresa (si viene en la URL)
    empresa_id = request.GET.get('empresa')
    if empresa_id and hasattr(model, 'empresas'):
        queryset = queryset.filter(empresas__id=empresa_id)
    
    # Filtro de búsqueda general (q)
    query = request.GET.get('q')
    if query:
        if hasattr(model, 'search_fields'):
            q_objects = Q()
            for field in model.search_fields:
                q_objects |= Q(**{f'{field}__icontains': query})
            queryset = queryset.filter(q_objects).distinct()
        elif hasattr(model, 'nombre'):
             queryset = queryset.filter(nombre__icontains=query)

    # 3. Crear Excel
    wb = Workbook()
    ws = wb.active
    ws.title = f"Catálogo {model._meta.verbose_name_plural}"
    
    # Escribir encabezados
    ws.append(conf['headers'])

    # Escribir datos
    for obj in queryset:
        row = []
        for field in conf['fields']:
            # Lógica especial para campos calculados o ManyToMany
            if field == 'empresas_str':
                val = ", ".join([e.nombre for e in obj.empresas.all()])
            elif field == 'direccion_completa' and hasattr(obj, 'direccion_completa'):
                val = obj.direccion_completa()
            else:
                val = getattr(obj, field, '')
                if val is None: val = ""
            row.append(str(val))
        ws.append(row)

    # 4. Formato de Tabla
    last_col = get_column_letter(len(conf['headers']))
    last_row = ws.max_row
    if last_row > 1:
        tab = Table(displayName=f"Tabla{model_name}", ref=f"A1:{last_col}{last_row}")
        style = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
        tab.tableStyleInfo = style
        ws.add_table(tab)
        
        # Ajustar ancho de columnas
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except: pass
            ws.column_dimensions[column].width = (max_length + 2)

    # 5. Respuesta
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Catalogo_{model_name}_{datetime.date.today()}.xlsx"'
    wb.save(response)
    return response