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

    # 2. Módulos Específicos (IMPORTANTE: Estos van PRIMERO)
    path('bancos/', include('flujo_bancos.urls')), # <--- Bancos ahora tiene prioridad
    path('compras/', include('compras.urls')),   
    path('chat/', include('chat.urls')),
    path('cuentas-por-pagar/', include('cuentas_por_pagar.urls')),

    # 3. Autenticación
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

    # 4. Ruta General / Bienvenida (IMPORTANTE: Esta va al FINAL)
    # Al estar al final, solo capturará lo que no haya coincidido con las anteriores.
    path('', include('ternium.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)