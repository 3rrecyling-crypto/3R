# compras/utils.py
import json
from twilio.rest import Client
from django.conf import settings
import json


def enviar_whatsapp_solicitud(solicitud, dominio_web="https://3recycling.com.mx"):
    try:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            return False

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # 1. Calcular el Total ($$)
        total = 0
        for detalle in solicitud.detalles.all():
            cant = detalle.cantidad or 0
            precio = detalle.precio_unitario or 0
            total += cant * precio

        # 2. Generar el Link al PDF
        link_pdf = f"{dominio_web}/compras/solicitudes/{solicitud.pk}/pdf/"

        # 3. Construir el resumen (Texto plano para evitar errores de plantilla)
        # Formato: Empresa - Proveedor - Total - Link
        resumen = (
            f"{solicitud.empresa.nombre} - Prov: {solicitud.proveedor.razon_social} "
            f"- Total: ${total:,.2f} - "
            f"PDF: {link_pdf}"
        )

        # Variables para la plantilla {{1}} y {{2}}
        variables = {
            "1": solicitud.folio,
            "2": resumen 
        }

        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=settings.TWILIO_WHATSAPP_TO_APPROVER,
            content_sid=settings.TWILIO_CONTENT_SID,
            content_variables=json.dumps(variables)
        )
        
        print(f"Mensaje enviado SID: {message.sid}")
        return True

    except Exception as e:
        print(f"Error enviando WhatsApp: {e}")
        return False
    
    
