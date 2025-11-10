"""
URL configuration for your project.
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from ternium.forms import CustomLoginForm # 1. IMPORTA EL NUEVO FORMULARIO
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    # Ruta para el panel de administración de Django
    path('admin/', admin.site.urls),
    path('compras/', include('compras.urls')),   
    path('chat/', include('chat.urls')), # Make sure this line exists
    path('', include('ternium.urls')),
    path('cuentas-por-pagar/', include('cuentas_por_pagar.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        authentication_form=CustomLoginForm  # <-- Añade esta línea
    ), name='login'),

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

