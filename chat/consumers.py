# chat/consumers.py

import json
import base64
import boto3
import io
from django.conf import settings
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

# NOTA: Los modelos de Django ya no se importan aquí para evitar el error de inicialización.
# Se importarán dentro de las funciones que los necesiten.

class ChatConsumer(AsyncWebsocketConsumer):
    """
    Gestiona las conexiones WebSocket para las conversaciones de chat.
    Utiliza un método manual con boto3 para subir archivos a S3.
    """
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.conversation_group_name = f'chat_{self.conversation_id}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        is_participant = await self.is_user_participant(self.user, self.conversation_id)
        if not is_participant:
            await self.close()
            return
        
        await self.channel_layer.group_add(self.conversation_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.conversation_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Recibe mensajes del WebSocket y los procesa según su tipo ('message' o 'typing').
        """
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'typing':
            # Notifica a los demás que el usuario está escribiendo
            await self.channel_layer.group_send(
                self.conversation_group_name,
                {
                    'type': 'typing_event',
                    'username': self.user.username,
                    'is_typing': data.get('is_typing', False),
                }
            )
        elif message_type == 'message':
            # Guarda un mensaje nuevo (texto o archivo)
            new_msg = await self.save_message_from_data(data)
            if new_msg is None: # Si la subida del archivo falló, no continúa
                return

            # Prepara y envía los datos del mensaje al grupo
            message_data = {
                'type': 'chat_message',
                'username': self.user.username,
                'timestamp': new_msg.timestamp.strftime('%d %b, %H:%M'),
                'message_type': new_msg.message_type,
                'content': new_msg.content,
                'file_url': new_msg.file_url,
                'file_type': new_msg.file_type,
            }
            await self.channel_layer.group_send(self.conversation_group_name, message_data)

    async def typing_event(self, event):
        """
        Envía el evento de 'está escribiendo' al cliente.
        """
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'username': event['username'],
            'is_typing': event['is_typing'],
        }))

    async def chat_message(self, event):
        """
        Envía un mensaje de chat formateado al cliente.
        """
        await self.send(text_data=json.dumps({
            'type': 'message',
            'username': event['username'],
            'timestamp': event['timestamp'],
            'message_type': event['message_type'],
            'content': event['content'],
            'file_url': event['file_url'],
            'file_type': event['file_type'],
        }))

    @database_sync_to_async
    def is_user_participant(self, user, conversation_id):
        """
        Verifica si el usuario es un participante válido de la conversación.
        """
        from .models import Conversation
        return Conversation.objects.filter(id=conversation_id, participants=user).exists()
    

    @database_sync_to_async
    def save_message_from_data(self, data):
        """
        Guarda un nuevo mensaje en la base de datos. Si el mensaje incluye un
        archivo, lo sube a S3 usando boto3.
        """
        from .models import Conversation, Message

        conversation = Conversation.objects.get(id=self.conversation_id)
        message_content = data.get('message', '')
        file_data = data.get('file_data')
        
        msg = Message(
            conversation=conversation,
            author=self.user,
            content=message_content,
            message_type='text'
        )
        
        if file_data:
            try:
                # Guardamos el nombre original que viene del frontend
                original_filename = data.get('original_filename', 'archivo')
                msg.original_filename = original_filename

                format, file_str = file_data.split(';base64,')
                ext = format.split('/')[-1]
                # Usamos un nombre de archivo seguro para S3
                s3_file_name = f"{timezone.now().timestamp()}.{ext}"
                s3_path = f"chat_files/{self.conversation_id}/{s3_file_name}"

                decoded_file = base64.b64decode(file_str)
                file_buffer = io.BytesIO(decoded_file)

                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
                
                s3_client.upload_fileobj(
                    file_buffer,
                    settings.AWS_STORAGE_BUCKET_NAME,
                    f"{settings.AWS_MEDIA_LOCATION}/{s3_path}"
                )
                
                msg.file = s3_path
                msg.file_type = data.get('file_type', 'application/octet-stream')

                if 'image' in msg.file_type: msg.message_type = 'image'
                else: msg.message_type = 'file'

            except Exception as e:
                print(f"Error al subir archivo a S3 manualmente: {e}")
                return None

        msg.save()
        conversation.save()
        
        return msg
    
class PresenceConsumer(AsyncWebsocketConsumer):
    """
    Este consumer maneja las conexiones WebSocket para el estado de presencia global.
    """
    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Nombre del grupo global para notificaciones de presencia
        self.presence_group_name = 'presence_group'
        await self.channel_layer.group_add(self.presence_group_name, self.channel_name)
        await self.accept()

        # Al conectarse, actualiza el estado a 'online' y lo notifica
        await self.update_user_status(status='online')
        # --- AJUSTE CLAVE ---
        # Enviamos la actualización primero al propio usuario que se conecta,
        # para que su UI se actualice inmediatamente.
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'user_id': self.user.id, 'username': self.user.username,
            'status': 'online', 'last_seen': timezone.now().isoformat()
        }))
        # Luego notificamos a todos los demás
        await self.broadcast_status('online')

    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_authenticated:
            # Al desconectarse, actualiza el estado a 'offline' y guarda la última vez visto
            await self.update_user_status(status='offline', update_last_seen=True)
            await self.broadcast_status('offline', timezone.now().isoformat())
            await self.channel_layer.group_discard(self.presence_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Permite al cliente cambiar su estado manualmente (ej. a 'away').
        """
        data = json.loads(text_data)
        status = data.get('status')
        if status in ['online', 'away']:
            await self.update_user_status(status=status)
            await self.broadcast_status(status)

    async def broadcast_status(self, status, last_seen=None):
        """
        Envía el estado actualizado a todos los clientes en el grupo de presencia.
        """
        await self.channel_layer.group_send(
            self.presence_group_name,
            {
                'type': 'presence_update',
                'user_id': self.user.id,
                'username': self.user.username,
                'status': status,
                'last_seen': last_seen
            }
        )

    async def presence_update(self, event):
        """
        Manejador que recibe el evento del grupo y lo envía al cliente a través del WebSocket.
        """
        # Evita enviarse la notificación a sí mismo de nuevo
        if self.scope['user'].id != event['user_id']:
            await self.send(text_data=json.dumps({
                'type': 'presence',
                'user_id': event['user_id'],
                'username': event['username'],
                'status': event['status'],
                'last_seen': event['last_seen']
            }))

    @database_sync_to_async
    def update_user_status(self, status, update_last_seen=False):
        """
        Actualiza el estado y la última vez visto del perfil de usuario en la base de datos.
        Usa get_or_create para evitar errores si el perfil no existe.
        """
        from .models import Profile
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.status = status
        if update_last_seen:
            profile.last_seen = timezone.now()
        profile.save()