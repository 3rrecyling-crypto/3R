"""
URL configuration for your project.
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from ternium.forms import CustomLoginForm
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # 1. Administración
    path('admin/', admin.site.urls),

    # 2. Módulos Específicos
    path('bancos/', include('flujo_bancos.urls')),
    path('compras/', include('compras.urls')),   
    path('chat/', include('chat.urls')),
    path('cuentas-por-pagar/', include('cuentas_por_pagar.urls')),
    path('diesel/', include('cargas_diesel.urls')),

    # 3. Facturación (CORRECCIÓN AQUÍ)
    # Le ponemos el prefijo 'facturacion/' para que NO ocupe la raíz del sitio.
    path('facturacion/', include('facturacion.urls')), 

    # 4. Autenticación
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        authentication_form=CustomLoginForm
    ), name='login'),
    
    path('reset_password/', 
         auth_views.PasswordResetView.as_view(template_name="registration/password_reset.html"), 
         name='password_reset'),
    path('reset_password_sent/', 
         auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"), 
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"), 
         name='password_reset_confirm'),
    path('reset_password_complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"), 
         name='password_reset_complete'),

    # 5. Otros Módulos
    path('herramientas/', include('herramientas.urls')),
    path('rh/', include('RH.urls')),

    # 6. API REST v1 (Next.js / React)
    path('api/v1/', include('api.urls')),

    # Módulos portados desde SANBENITO (mismos prefijos que consume el frontend)
    path('api/diagramas/', include('diagramas.urls')),
    path('api/ia-studio/', include('ia_studio.urls')),
    path('api/yard-sketch/', include('yard_sketch.urls')),
    path('api/transferencias/', include('transferencias.urls')),
    path('api/simulador/', include('simulador.urls')),
    path('api/mensajeria/', include('mensajeria.urls')),  # Chat interno + videollamadas

    # 6. Ruta General / Bienvenida (IMPORTANTE: Esta va al FINAL)
    # Al entrar a "midominio.com/", Django probará todas las de arriba.
    # Como ninguna coincidirá con la cadena vacía (porque facturacion ahora tiene prefijo),
    # llegará hasta aquí y mostrará la Bienvenida de 'ternium.urls'.
    path('', include('ternium.urls')),
]

# Configuración para archivos media en modo DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)