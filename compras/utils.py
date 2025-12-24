# compras/utils.py
import json
from twilio.rest import Client
from django.conf import settings

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