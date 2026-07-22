# herramientas/urls.py
from django.urls import path
from . import views

# Si tienes esta línea: app_name = 'herramientas', bórrala por ahora para simplificar
# o tendrás que cambiar el HTML a 'herramientas:unir_pdf'

# herramientas/urls.py
urlpatterns = [
    path('', views.index, name='index_herramientas'),
    # path('unir-pdf/', views.unir_pdf, name='unir_pdf'),  <-- BORRA O COMENTA ESTA LÍNEA
    path('fotos-pdf/', views.fotos_a_pdf, name='fotos_pdf'),
    path('quitar-fondo/', views.quitar_fondo, name='quitar_fondo'),
    path('unir-pdf/', views.unir_pdf_pro, name='unir_pdf'), # <-- ESTA ES LA QUE VALE
    path('licencia-premium/', views.LicenciaPremiumView.as_view(), name='licencia_premium'),
]