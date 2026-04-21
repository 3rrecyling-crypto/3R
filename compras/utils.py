# compras/utils.py

import json
from twilio.rest import Client
from django.conf import settings
from django.urls import reverse
from django.core.signing import TimestampSigner

def get_public_pdf_url(solicitud):
    """
    Genera una URL firmada (token) para ver el PDF sin login.
    """
    signer = TimestampSigner()
    # Firmamos el ID de la solicitud para crear un token único
    signed_pk = signer.sign(solicitud.id)
    
    # Creamos la ruta relativa que definiste en urls.py
    path = reverse('solicitud_pdf_public', kwargs={'signed_pk': signed_pk})
    
    # Concatenamos con el dominio base (definido en settings.py)
    # Si no está definido, usa localhost por defecto para evitar errores, pero en prod debe ser tu dominio real.
    domain = getattr(settings, 'DOMAIN_URL', 'http://127.0.0.1:8000') 
    
    # Aseguramos que no haya doble barra //
    return f"{domain.rstrip('/')}{path}"
def enviar_whatsapp_solicitud(solicitud):
    try:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            return False

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        total = sum((d.cantidad or 0) * (d.precio_unitario or 0) for d in solicitud.detalles.all())
        pdf_link = get_public_pdf_url(solicitud)

        # --- CORRECCIÓN: USAR ESPACIO EN LUGAR DE \n ---
        # Twilio prohíbe saltos de línea en variables. Usamos ". " para separar.
        resumen = (
            f"{solicitud.empresa.nombre} | {solicitud.proveedor.razon_social} | "
            f"${total:,.2f}. 📄 Ver PDF: {pdf_link}"
        )

        # Aseguramos que todo sea string y sin caracteres prohibidos
        variables = {
            "1": str(solicitud.folio),
            "2": str(resumen) 
        }

        print(f"DEBUG - Enviando variables: {json.dumps(variables)}") # Para ver en logs si falla

        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=settings.TWILIO_WHATSAPP_TO_APPROVER,
            content_sid=settings.TWILIO_CONTENT_SID,
            content_variables=json.dumps(variables)
        )
        
        print(f"✅ WhatsApp enviado. SID: {message.sid}")
        return True

    except Exception as e:
        print(f"❌ Error enviando WhatsApp: {e}")
        return False