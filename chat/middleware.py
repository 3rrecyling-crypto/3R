# chat/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Conversation, Message
from django.db.models import Q
from django.db.models import Count
from .models import Profile
from django.utils import timezone


@login_required
def user_list(request):
    """Muestra una lista de todos los usuarios para iniciar una conversación."""
    users = User.objects.exclude(id=request.user.id)
    return render(request, 'chat/user_list.html', {'users': users})

@login_required
def conversation_list(request):
    # This view is already correct from the previous step
    conversations = Conversation.objects.filter(participants=request.user).prefetch_related('participants')
    for conv in conversations:
        other_participant = conv.participants.exclude(id=request.user.id).first()
        conv.other_user = other_participant
    context = {'conversations': conversations}
    return render(request, 'chat/conversation_list.html', context)

# --- ADD THIS NEW VIEW ---

def start_conversation(request, user_id):
    """
    Busca o crea una conversación entre el usuario actual y el usuario seleccionado,
    y redirige a la sala de chat.
    """
    other_user = get_object_or_404(User, id=user_id)
    
    # Busca si ya existe una conversación entre estos dos usuarios
    conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=other_user
    )
    
    if conversation.exists():
        # Si ya existe, usa esa conversación
        conversation = conversation.first()
    else:
        # Si no, crea una nueva
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, other_user)
        
    return redirect('chat_detail', conversation_id=conversation.id)


@login_required
def chat_detail(request, conversation_id):
    # Obtenemos la conversación y nos aseguramos de que el usuario participe en ella
    conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
    
    # ¡ESTA ES LA LÍNEA CLAVE! Obtenemos todos los mensajes de la conversación
    messages = conversation.messages.select_related('author').all()
    
    # Obtenemos al otro participante para mostrar su nombre
    other_participant = conversation.participants.exclude(id=request.user.id).first()
    
    context = {
        'conversation': conversation,
        'messages': messages,  # Pasamos el historial de mensajes a la plantilla
        'other_participant': other_participant,
    }
    return render(request, 'chat/chat_detail.html', context)
