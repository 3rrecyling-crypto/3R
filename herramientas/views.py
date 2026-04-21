# herramientas/views.py
from django.shortcuts import render
from django.http import HttpResponse
from .forms import UnirPDFForm, FotosToPDFForm, QuitarFondoForm
from pypdf import PdfWriter, PdfReader
from PIL import Image, ImageOps 
import io
import json
from rembg import remove

def index(request):
    return render(request, 'herramientas/index.html')

def unir_pdf(request):
    if request.method == 'POST':
        form = UnirPDFForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist('archivos')
            merger = PdfWriter()
            for pdf in files:
                merger.append(pdf)
            buffer = io.BytesIO()
            merger.write(buffer)
            buffer.seek(0)
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="unido.pdf"'
            return response
    else:
        form = UnirPDFForm()
    return render(request, 'herramientas/herramienta_base.html', {
        'form': form, 'title': 'Unir PDFs', 'btn_text': 'Fusionar'
    })

def fotos_a_pdf(request):
    if request.method == 'POST':
        # 1. Obtenemos los archivos (el orden lo define el JS del frontend)
        files = request.FILES.getlist('imagenes')
        
        # 2. Obtenemos la lista de rotaciones
        rotaciones_json = request.POST.get('rotaciones_list', '[]')
        try:
            rotaciones = json.loads(rotaciones_json)
        except json.JSONDecodeError:
            rotaciones = []

        # 3. Obtenemos el nombre personalizado
        custom_name = request.POST.get('nombre_archivo', '').strip()
        if not custom_name:
            custom_name = "mi_documento"
        if not custom_name.lower().endswith('.pdf'):
            custom_name += ".pdf"

        if not files:
            return HttpResponse("No se subieron archivos")

        image_list = []
        first_image = None

        # Procesamos cada imagen junto con su ángulo de rotación
        for idx, (f, angle) in enumerate(zip(files, rotaciones + [0]*len(files))):
            try:
                img = Image.open(f)
                
                # IMPORTANTE: Corregir orientación EXIF (para fotos de celular)
                img = ImageOps.exif_transpose(img) 
                
                img = img.convert('RGB')
                
                # Aplicar la rotación manual del usuario
                if angle != 0:
                    img = img.rotate(-int(angle), expand=True)

                if idx == 0:
                    first_image = img
                else:
                    image_list.append(img)
            except Exception as e:
                print(f"Error procesando imagen: {str(e)}")
                continue

        if first_image:
            buffer = io.BytesIO()
            first_image.save(buffer, save_all=True, append_images=image_list, format='PDF')
            buffer.seek(0)

            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{custom_name}"'
            return response
    
    else:
        form = FotosToPDFForm()

    # Renderizamos el template específico (Manteniendo el título de Modo Turbo si lo prefieres)
    return render(request, 'herramientas/fotos_pdf_tool.html', {
        'form': form, 
        'title': 'Convertir Fotos a PDF (Modo Turbo)', 
        'btn_text': 'Generar PDF'
    })

def quitar_fondo(request):
    if request.method == 'POST':
        form = QuitarFondoForm(request.POST, request.FILES)
        if form.is_valid():
            img_file = request.FILES['imagen']
            input_image = Image.open(img_file)
            # Requiere: from rembg import remove (Asegúrate de importarlo si usas esta vista)
            output_image = remove(input_image) 
            buffer = io.BytesIO()
            output_image.save(buffer, format="PNG")
            buffer.seek(0)
            response = HttpResponse(buffer, content_type='image/png')
            response['Content-Disposition'] = 'attachment; filename="sin_fondo.png"'
            return response
    else:
        form = QuitarFondoForm()
    return render(request, 'herramientas/herramienta_base.html', {
        'form': form, 'title': 'Quitar Fondo de Imagen', 'btn_text': 'Procesar'
    })
    
def unir_pdf_pro(request):
    if request.method == 'POST':
        # 1. Obtener archivos
        files = request.FILES.getlist('archivos_pdf')
        
        # 2. Obtener el mapa de páginas: Ej: [{"file_index": 0, "page_num": 2}, {"file_index": 1, "page_num": 0}]
        page_map_json = request.POST.get('page_map', '[]')
        
        # 3. Nombre personalizado
        custom_name = request.POST.get('nombre_archivo', '').strip()
        if not custom_name:
            custom_name = "documento_fusionado"
        if not custom_name.lower().endswith('.pdf'):
            custom_name += ".pdf"

        try:
            page_map = json.loads(page_map_json)
        except json.JSONDecodeError:
            return HttpResponse("Error en los datos de ordenamiento", status=400)

        if not files or not page_map:
            return HttpResponse("No hay archivos o páginas para procesar")

        # 4. Procesamiento
        merger = PdfWriter()
        
        # Para optimizar, abrimos todos los PDFs una vez y los guardamos en una lista
        readers = []
        for f in files:
            try:
                readers.append(PdfReader(f))
            except Exception as e:
                # AQUÍ ESTÁ EL ARREGLO: Imprimimos el error real en la consola
                print(f"Error al leer el archivo {f.name}: {str(e)}")
                readers.append(None)

        # 5. Reconstruir el PDF final basado en el mapa
        for item in page_map:
            f_idx = int(item['file_index'])
            p_num = int(item['page_num'])

            # Validaciones de seguridad
            if 0 <= f_idx < len(readers) and readers[f_idx] is not None:
                reader = readers[f_idx]
                if 0 <= p_num < len(reader.pages):
                    merger.add_page(reader.pages[p_num])

        # 6. Generar respuesta
        buffer = io.BytesIO()
        merger.write(buffer)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{custom_name}"'
        return response

    return render(request, 'herramientas/unir_pdf_tool.html', {
        'title': 'Organizador Avanzado de PDFs',
        'btn_text': 'Fusionar PDFs'
    })