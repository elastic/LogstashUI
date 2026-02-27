from django.urls import path
from . import views

urlpatterns = [
    path("GrokDebugger/", views.GrokDebugger, name="GrokDebugger"),
    path("GrokDebugger/simulate/", views.simulate_grok, name="simulate_grok"),
    path("GrokDebugger/patterns/", views.get_grok_patterns, name="get_grok_patterns"),
]