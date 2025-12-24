# compras/utils.py
import json
from twilio.rest import Client
from django.conf import settings
import json


def enviar_whatsapp_solicitud(solicitud):
    """
    Envía una notificación de WhatsApp usando Twilio Content API.
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # Mapeamos las variables de tu plantilla {{1}} y {{2}}
        # Ejemplo: {{1}} = Folio, {{2}} = Solicitante
        variables = {
            "1": solicitud.folio,
            "2": f"{solicitud.solicitante.first_name} {solicitud.solicitante.last_name}"
        }

        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=settings.TWILIO_WHATSAPP_TO_APPROVER, # Número del aprobador
            content_sid=settings.TWILIO_CONTENT_SID, # Tu plantilla HX...
            content_variables=json.dumps(variables)
        )
        
        print(f"Mensaje enviado SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Error enviando WhatsApp: {e}")
        return False
    
    
def enviar_whatsapp_solicitud(solicitud, dominio_web="https://threer-recycling.onrender.com"):
    """
    Envía un mensaje detallado.
    dominio_web: Se usa para crear el link al archivo.
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # 1. Construir el detalle de los artículos
        detalles_texto = ""
        for det in solicitud.detalles.all():
            detalles_texto += f"- {det.cantidad} {det.articulo.unidad_medida} x {det.articulo.nombre} (${det.precio_unitario})\n"

        # 2. Link al archivo (si existe)
        link_archivo = "Sin archivo adjunto"
        if solicitud.cotizacion:
            link_archivo = f"{dominio_web}{solicitud.cotizacion.url}"

        # 3. Construir el mensaje completo
        # Usamos emojis y saltos de línea (\n)
        mensaje_cuerpo = (
            f"*Operación:* {solicitud.empresa.nombre}\n"
            f"*Origen:* {solicitud.lugar.nombre}\n"
            f"*Proveedor:* {solicitud.proveedor.razon_social}\n"
            f"*Prioridad:* {solicitud.prioridad}\n"
            f"*Motivo:* {solicitud.motivo}\n\n"
            f"*Artículos:*\n{detalles_texto}\n"
            f"*Cotización:* {link_archivo}\n\n"
            f"responde *APROBAR {solicitud.folio}* para confirmar."
        )

        # Mapeo de variables (Asegúrate que tu plantilla soporte texto largo en la variable 2)
        variables = {
            "1": solicitud.folio,     # Para el encabezado
            "2": mensaje_cuerpo       # Para el cuerpo del mensaje
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