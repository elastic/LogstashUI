from django.contrib import admin
from django.urls import path, include
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("GrokDebugger/", views.GrokDebugger, name="GrokDebugger"),
    path("GrokDebugger/simulate/", views.simulate_grok, name="simulate_grok"),
    path("GrokDebugger/patterns/", views.get_grok_patterns, name="get_grok_patterns"),
]