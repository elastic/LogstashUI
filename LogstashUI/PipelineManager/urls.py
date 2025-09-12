from django.urls import path
from . import views


urlpatterns = [
    path('Pipelines/', views.PipelineManager, name='pipelines'),
    path('Logstash/', views.Logstash, name='logstash'),
    path("Pipelines/Editor/", views.PipelineEditor, name="PipelineEditor")
]