from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.Home, name='home'),
    path('Monitoring/', views.Monitoring, name='monitoring'),
    path('health/', views.health_check, name='health_check')
]