from django.urls import path

from . import views

urlpatterns = [
    path('', views.tickets, name='api_tickets'),
    path('<int:pk>/', views.ticket_detalle, name='api_ticket_detalle'),
    path('<int:pk>/comentarios/', views.ticket_comentar, name='api_ticket_comentar'),
    path('<int:pk>/actualizar/', views.ticket_actualizar, name='api_ticket_actualizar'),
]
