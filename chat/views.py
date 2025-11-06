# chat/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Conversation, Message
from django.db.models import Count, Prefetch

@login_required
def user_list(request):
    """
    Muestra una lista de usuarios, precargando sus perfiles de chat y ternium
    para un rendimiento óptimo.
    """
    users = User.objects.exclude(id=request.user.id).select_related(
        'chat_profile', 'ternium_profile'
    )
    return render(request, 'chat/user_list.html', {'users': users})


@login_required
def conversation_list(request):
    """ Muestra la lista de conversaciones del usuario. """
    conversations = Conversation.objects.filter(
        participants=request.user
    ).prefetch_related(
        # Precargamos ambos perfiles para todos los participantes
        Prefetch('participants', queryset=User.objects.select_related('chat_profile', 'ternium_profile'))
    )

    for conv in conversations:
        other_participant = next((p for p in conv.participants.all() if p.id != request.user.id), None)
        conv.other_user = other_participant

    context = {'conversations': conversations}
    return render(request, 'chat/conversation_list.html', context)


@login_required
def start_conversation(request, user_id):
    """ Inicia o encuentra una conversación existente con un usuario. """
    other_user = get_object_or_404(User, id=user_id)

    conversation = Conversation.objects.annotate(
        num_participants=Count('participants')
    ).filter(
        num_participants=2,
        participants=request.user
    ).filter(
        participants=other_user
    ).first()

    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, other_user)
        
    return redirect('chat_detail', conversation_id=conversation.id)


@login_required
def chat_detail(request, conversation_id):
    """ Muestra el detalle de una conversación específica. """
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related('participants__chat_profile', 'participants__ternium_profile'),
        id=conversation_id, 
        participants=request.user
    )
    
    messages = conversation.messages.select_related('author').all()
    other_participant = next((p for p in conversation.participants.all() if p.id != request.user.id), None)
    
    context = {
        'conversation': conversation,
        'messages': messages,
        'other_participant': other_participant,
    }
    return render(request, 'chat/chat_detail.html', context)

# --- NUEVA VISTA AÑADIDA ---
@login_required
def user_profile_detail(request, user_id):
    """
    Muestra la página de perfil de un usuario específico.
    """
    profile_user = get_object_or_404(
        User.objects.select_related('chat_profile', 'ternium_profile'), 
        id=user_id
    )
    context = {
        'profile_user': profile_user
    }
    return render(request, 'chat/user_profile_detail.html', context)