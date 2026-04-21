# ternium/middleware.py

from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.conf import settings

class ProfileCompletionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Si el usuario no está logueado, dejar pasar (el login_required lo detendrá después)
        if not request.user.is_authenticated:
            return self.get_response(request)

        # 2. Definir rutas exentas (para evitar bucles infinitos)
        # Debemos permitir entrar al perfil (para editar), salir (logout) y archivos estáticos
        path = request.path
        
        try:
            url_perfil = reverse('perfil')
            url_logout = reverse('logout')
        except:
            # Si las URLs no están cargadas aún
            return self.get_response(request)

        rutas_exentas = [
            url_perfil,
            url_logout,
            '/admin/',
            settings.STATIC_URL,
            settings.MEDIA_URL,
        ]

        # Si la ruta actual empieza con alguna de las exentas, dejar pasar
        if any(path.startswith(exenta) for exenta in rutas_exentas):
            return self.get_response(request)

        # 3. Verificar datos del usuario
        user = request.user
        # Obtenemos el perfil de forma segura
        profile = getattr(user, 'ternium_profile', None)

        # Lista de campos faltantes
        faltantes = []
        
        if not user.first_name or not user.first_name.strip():
            faltantes.append("Nombre")
        if not user.last_name or not user.last_name.strip():
            faltantes.append("Apellidos")
        if not user.email or not user.email.strip():
            faltantes.append("Correo Electrónico")
        
        # Verificamos teléfono en el perfil extendido
        if not profile or not profile.telefono or not profile.telefono.strip():
            faltantes.append("Teléfono")

        # 4. Si hay faltantes, redirigir y avisar
        if faltantes:
            # Usamos el framework de mensajes de Django para la alerta
            mensaje = f"⚠️ Acción Requerida: Para continuar navegando, debes completar los siguientes datos en tu perfil: {', '.join(faltantes)}."
            
            # Evitamos spamear mensajes si el usuario recarga la página
            storage = messages.get_messages(request)
            if not any(m.message == mensaje for m in storage):
                messages.warning(request, mensaje, extra_tags='danger')
            
            return redirect('perfil')

        return self.get_response(request)