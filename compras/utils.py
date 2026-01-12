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
        # Validación de seguridad
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            print("❌ Faltan credenciales de Twilio en settings.")
            return False

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # 1. Calcular Total
        total = sum((d.cantidad or 0) * (d.precio_unitario or 0) for d in solicitud.detalles.all())

        # 2. Generar el enlace del PDF
        pdf_link = get_public_pdf_url(solicitud)

        # 3. Construir el resumen para la variable {{2}}
        # Incluimos el enlace aquí. WhatsApp lo reconocerá y lo hará clicable.
        resumen = (
            f"{solicitud.empresa.nombre} | Prov: {solicitud.proveedor.razon_social}\n"
            f"💰 Total: ${total:,.2f}\n"
            f"📄 Ver PDF: {pdf_link}"
        )

        variables = {
            "1": str(solicitud.folio),  # Variable {{1}}
            "2": resumen                # Variable {{2}}
        }

        # 4. Enviar
        # Asegúrate que el Content SID en Twilio tenga los botones "Aprobar" y "Rechazar" configurados
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