# chat/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # La ruta principal del chat ahora apunta a la lista de conversaciones (bandeja de entrada)
    path('', views.conversation_list, name='conversation_list'),

    # Ruta para ver todos los usuarios e iniciar un nuevo chat
    path('users/', views.user_list, name='user_list'),

    # Ruta funcional para crear o encontrar una conversación con otro usuario
    path('start/<int:user_id>/', views.start_conversation, name='start_conversation'),
    path('profile/<int:user_id>/', views.user_profile_detail, name='user_profile_detail'),

    # Ruta para ver los mensajes de una conversación específica
    path('<int:conversation_id>/', views.chat_detail, name='chat_detail'),
]