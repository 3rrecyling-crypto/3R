import json
from twilio.rest import Client
from django.conf import settings

def enviar_whatsapp_solicitud(solicitud):
    try:
        # Validación de seguridad
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            return False

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # 1. Calcular Total de forma segura
        total = sum((d.cantidad or 0) * (d.precio_unitario or 0) for d in solicitud.detalles.all())

        # 2. Resumen CORTO (Sin URL, dejamos que el botón haga el trabajo)
        # Esto asegura que no excedas el límite de caracteres de la variable
        resumen = f"{solicitud.empresa.nombre} - Prov: {solicitud.proveedor.razon_social} - Total: ${total:,.2f}"

        variables = {
            "1": str(solicitud.folio),  # Variable {{1}}
            "2": resumen                # Variable {{2}}
        }

        # 3. Enviar
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