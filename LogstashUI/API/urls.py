from django.urls import path, include
from . import views

urlpatterns = [
    path('TestConnectivity', views.TestConnectivity, name='TestConnectivity'),

    path("AddConnection", views.AddConnection, name="AddConnection"),
    path("DeleteConnection/<int:connection_id>/", views.DeleteConnection, name="DeleteConnection"),
    path("GetPipelines/<int:connection_id>/", views.GetPipelines, name="GetPipelines"),


    path("GetLogstashCode", views.GetLogstashCode, name="GetLogstashCode"),
    path("GetDiff/", views.GetDiff, name="GetDiff"),
    path("SavePipeline/", views.SavePipeline, name="SavePipeline"),
    path("SimulatePipeline/", views.SimulatePipeline, name="SimulatePipeline"),
    path("UpdatePipelineSettings/", views.UpdatePipelineSettings, name="UpdatePipelineSettings")
]