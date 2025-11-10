# chat/models.py

import os
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone

# --- MODELOS DE LA APP CHAT ---

class Profile(models.Model):
    # This is the correct format: a tuple of tuples.
    STATUS_CHOICES = (
        ('online', 'En línea'),
        ('offline', 'Desconectado'),
        ('away', 'Ausente'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='chat_profile')
    
    # --- ¡SOLUCIÓN AL ERROR ORIGINAL! ---
    # Al poner null=True y blank=True, permites que la base de datos
    # cree el registro con este campo vacío, evitando el IntegrityError.
<<<<<<< HEAD
    last_seen = models.DateTimeField(default=timezone.now, null=False, blank=False)
=======
    last_seen = models.DateTimeField(null=True, blank=True)
>>>>>>> 400f8621cdea2163e4302d5550344851c937f99b
    
    # The 'status' field uses the correctly formatted choices.
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='offline'
    )

    def __str__(self):
        return self.user.username
        
class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_last_message(self):
        """ Devuelve el mensaje más reciente de esta conversación. """
        return self.messages.order_by('-timestamp').first()

    def __str__(self):
        return f"Conversación {self.id}"

    class Meta:
        ordering = ['-updated_at']

def get_chat_upload_path(instance, filename):
    """ 
    Genera una ruta única para los archivos del chat en S3. 
    NOTA: Tu modelo 'Message' usa un CharField, no un FileField,
    por lo que esta función no se está usando actualmente.
    """
    return os.path.join('chat_files', str(instance.conversation.id), filename)

class Message(models.Model):
    MESSAGE_TYPE_CHOICES = (
        ('text', 'Texto'),
        ('image', 'Imagen'),
        ('video', 'Video'),
        ('file', 'Archivo'),
    )
    
    conversation = models.ForeignKey('Conversation', on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='authored_messages')
    content = models.TextField(blank=True)
    
    # Estos campos son correctos para una lógica de subida de archivos pre-firmada
    file = models.CharField(max_length=500, blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default='text')
    file_type = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    @property
    def clean_filename(self):
        if self.file:
            return os.path.basename(self.file)
        return ''
        
    @property
    def file_url(self):
        if self.file:
            # Ahora 'settings' está definido y puede ser usado aquí
            return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{settings.AWS_MEDIA_LOCATION}/{self.file}"
        return None

    def __str__(self):
        return f'{self.author.username}: {self.content[:30] if self.content else "Archivo adjunto"}'

    class Meta:
        ordering = ['timestamp']
        
# -----------------------------------------------------------------
# --- SEÑALES (SIGNALS) ---
# Movimos las señales al final para asegurar que todos los modelos
# estén definidos antes de ser usados.
# -----------------------------------------------------------------

# Importamos el Perfil de Ternium.
# ¡IMPORTANTE! Esto asume que 'ternium.models' NO importa 'chat.models'
# en la parte superior, o causará una importación circular.
try:
    from ternium.models import Profile as TerniumProfile
except (ImportError, ModuleNotFoundError):
    # Manejo de error por si 'ternium.models' aún no existe o tiene problemas
    print("Advertencia: No se pudo importar TerniumProfile. La creación de perfiles de Ternium puede fallar.")
    TerniumProfile = None

@receiver(post_save, sender=User)
def create_user_profiles(sender, instance, created, **kwargs):
    """
    Crea AMBOS perfiles (Chat y Ternium) cuando un User es creado.
    """
    if created:
        # Crea el ChatProfile (usando el modelo 'Profile' definido ARRIBA en ESTE archivo)
        Profile.objects.get_or_create(user=instance)
        
        # Crea el TerniumProfile (importado de ternium.models)
        if TerniumProfile:
            TerniumProfile.objects.get_or_create(user=instance)
            
@receiver(post_save, sender=User)
def save_user_profiles(sender, instance, **kwargs):
    """
    Guarda los perfiles asociados cuando el User se guarda.
    """
    if hasattr(instance, 'ternium_profile') and TerniumProfile:
        instance.ternium_profile.save()
        
    if hasattr(instance, 'chat_profile'):
        instance.chat_profile.save()