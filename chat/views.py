# chat/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Conversation, Message
from django.db.models import Count, Prefetch
from django.http import JsonResponse  # <--- ¡ESTA LÍNEA FALTABA!

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
    
    # --- BLOQUE PARA MARCAR COMO LEÍDO ---
    # Cuando entras al chat, marcamos como leídos los mensajes que NO son tuyos
    conversation.messages.filter(is_read=False).exclude(author=request.user).update(is_read=True)
    # -------------------------------------------

    # CAMBIO IMPORTANTE: Usamos 'chat_messages' en lugar de 'messages'
    # para evitar conflictos con las alertas de Django (messages framework)
    chat_messages = conversation.messages.select_related('author').all()
    
    other_participant = next((p for p in conversation.participants.all() if p.id != request.user.id), None)
    
    context = {
        'conversation': conversation,
        'chat_messages': chat_messages,  # <--- Esta es la clave para que se vea bien
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

@login_required
def get_mensajes_no_leidos(request):
    """
    API que cuenta cuántos mensajes no leídos tiene el usuario en total.
    """
    try:
        user = request.user
        # Lógica: Contar mensajes donde:
        # 1. El mensaje pertenece a una conversación donde estoy (conversation__participants)
        # 2. El mensaje NO lo escribí yo (exclude author)
        # 3. El mensaje no ha sido leído (is_read=False)
        
        count = Message.objects.filter(
            conversation__participants=user,
            is_read=False
        ).exclude(
            author=user
        ).count()
        
        return JsonResponse({'count': count})
    except Exception as e:
        print(f"Error contando mensajes: {e}")
        return JsonResponse({'count': 0})