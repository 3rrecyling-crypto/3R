"""
Generación de códigos QR y de barras como SVG (vectorial, nítido para impresión).
Reutiliza las librerías ya instaladas: qrcode y python-barcode.
"""
import io
import re


def generar_codigo_svg(tipo: str, valor: str, formato: str = "code128") -> dict:
    """
    Devuelve { "svg": "<svg…>", "w": <px>, "h": <px> } para insertar en el canvas.
    tipo: "qr" | "barcode". formato (solo barcode): code128, ean13, code39, …
    """
    tipo = (tipo or "qr").strip().lower()
    valor = (valor or "").strip()
    if not valor:
        raise ValueError("El valor del código no puede estar vacío.")
    if len(valor) > 1000:
        raise ValueError("El valor es demasiado largo (máx 1000 caracteres).")

    if tipo == "qr":
        import qrcode
        import qrcode.image.svg
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(valor)
        qr.make(fit=True)
        img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        return {"svg": buf.getvalue().decode("utf-8"), "w": 300, "h": 300}

    # Código de barras
    import barcode
    from barcode.writer import SVGWriter
    formato = (formato or "code128").strip().lower()
    if formato not in set(barcode.PROVIDED_BARCODES):
        formato = "code128"
    try:
        bc = barcode.get(formato, valor, writer=SVGWriter())
    except Exception as e:
        raise ValueError(f"Valor inválido para el formato {formato}: {e}")
    buf = io.BytesIO()
    bc.write(buf, options={"module_height": 12.0, "font_size": 8, "quiet_zone": 2})
    svg = buf.getvalue().decode("utf-8")
    # Relación de aspecto desde el tamaño del SVG (mm) → px razonables.
    m = re.search(r'width="([\d.]+)mm"\s+height="([\d.]+)mm"', svg)
    if m:
        wmm, hmm = float(m.group(1)), float(m.group(2))
        w = 320
        h = max(50, round(320 * hmm / max(wmm, 1)))
    else:
        w, h = 320, 120
    return {"svg": svg, "w": w, "h": h}
