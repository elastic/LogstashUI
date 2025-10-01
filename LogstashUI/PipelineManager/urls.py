from django.urls import path
from . import views


urlpatterns = [

    path("", views.PipelineManager, name="PipelineManager"),
    path("Pipelines/Editor/", views.PipelineEditor, name="PipelineEditor")
]