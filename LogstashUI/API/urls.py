from django.urls import path, include
from . import views

urlpatterns = [
    path('TestConnectivity', views.TestConnectivity, name='TestConnectivity'),

    path("AddConnection", views.AddConnection, name="AddConnection"),
    path("DeleteConnection/<int:connection_id>/", views.DeleteConnection, name="DeleteConnection"),
    path("GetPipelines/<int:connection_id>/", views.GetPipelines, name="GetPipelines"),


    path("GetCurrentPipelineCode/", views.GetCurrentPipelineCode, name="GetCurrentPipelineCode"),
    path("GetDiff/", views.GetDiff, name="GetDiff"),
    path("SavePipeline/", views.SavePipeline, name="SavePipeline"),
    path("SimulatePipeline/", views.SimulatePipeline, name="SimulatePipeline"),

    path("UpdatePipelineSettings/", views.UpdatePipelineSettings, name="UpdatePipelineSettings"),
    path("CreatePipeline/", views.CreatePipeline, name="CreatePipeline"),
    path("DeletePipeline/", views.DeletePipeline, name="DeletePipeline"),
    path("GetPipeline/", views.GetPipeline, name="GetPipeline"),
    
    # Metrics endpoints
    path("GetNodeMetrics", views.GetNodeMetrics, name="GetNodeMetrics"),
    path("GetPipelineMetrics", views.GetPipelineMetrics, name="GetPipelineMetrics"),
    path("GetLogs", views.GetLogs, name="GetLogs")
]