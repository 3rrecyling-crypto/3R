
# chat/apps.py

from django.apps import AppConfig

class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'
    
# en apps.py
def ready(self):
    import tu_app.signals
