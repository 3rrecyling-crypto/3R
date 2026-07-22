"""
Exporta el lienzo (recibido como PNG) a un PDF de una página del tamaño del diseño.
Usa reportlab (ya instalado).
"""
import base64
import io


def png_a_pdf_base64(png_data_url: str, w: float, h: float) -> str:
    """
    Convierte un PNG (data URL) en un PDF de una página de w×h puntos.
    Devuelve el PDF como base64 (sin encabezado data:).
    """
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdfcanvas

    if "," in (png_data_url or ""):
        png_data_url = png_data_url.split(",", 1)[1]
    png_bytes = base64.b64decode(png_data_url)
    img = ImageReader(io.BytesIO(png_bytes))

    # Tamaño de página en puntos (1px ≈ 1pt). Acotado para evitar PDFs absurdos.
    W = max(16.0, min(float(w or 800), 14400.0))
    H = max(16.0, min(float(h or 600), 14400.0))

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(W, H))
    c.drawImage(img, 0, 0, width=W, height=H, preserveAspectRatio=False, mask="auto")
    c.showPage()
    c.save()
    return base64.b64encode(buf.getvalue()).decode("utf-8")
