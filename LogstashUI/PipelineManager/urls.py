from django.urls import path
from . import views, simulation


urlpatterns = [

    path("", views.PipelineManager, name="PipelineManager"),
    path("Pipelines/Editor/", views.PipelineEditor, name="PipelineEditor"),

    path("SimulatePipeline/", simulation.SimulatePipeline, name="SimulatePipeline"),
    path("StreamSimulate/", simulation.StreamSimulate, name="StreamSimulate"),
    path("GetSimulationResults/", simulation.GetSimulationResults, name="GetSimulationResults"),
    path("CheckIfPipelineLoaded/", simulation.CheckIfPipelineLoaded, name="CheckIfPipelineLoaded"),
    path("GetRelatedLogs/", simulation.GetRelatedLogs, name="GetRelatedLogs"),
    path("UploadFile/", simulation.UploadFile, name="UploadFile"),
]