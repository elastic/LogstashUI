"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

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

    path('TestConnectivity', views.TestConnectivity, name='TestConnectivity'),

    path("GetConnections/", views.GetConnections, name="GetConnections"),
    path("AddConnection", views.AddConnection, name="AddConnection"),
    path("DeleteConnection/<int:connection_id>/", views.DeleteConnection, name="DeleteConnection"),
    path("GetPipelines/<int:connection_id>/", views.GetPipelines, name="GetPipelines"),

    path("GetCurrentPipelineCode/", views.GetCurrentPipelineCode, name="GetCurrentPipelineCode"),
    path("GetDiff/", views.GetDiff, name="GetDiff"),
    path("SavePipeline/", views.SavePipeline, name="SavePipeline"),
    path("ComponentsToConfig/", views.ComponentsToConfig, name="ComponentsToConfig"),
    path("ConfigToComponents/", views.ConfigToComponents, name="ConfigToComponents"),

    path("UpdatePipelineSettings/", views.UpdatePipelineSettings, name="UpdatePipelineSettings"),
    path("CreatePipeline/", views.CreatePipeline, name="CreatePipeline"),
    path("DeletePipeline/", views.DeletePipeline, name="DeletePipeline"),
    path("ClonePipeline/", views.ClonePipeline, name="ClonePipeline"),
    path("GetPipeline/", views.GetPipeline, name="GetPipeline"),

    # Elasticsearch simulation endpoints
    path("GetElasticsearchConnections/", views.GetElasticsearchConnections, name="GetElasticsearchConnections"),
    path("GetElasticsearchIndices/", views.GetElasticsearchIndices, name="GetElasticsearchIndices"),
    path("GetElasticsearchFields/", views.GetElasticsearchFields, name="GetElasticsearchFields"),
    path("QueryElasticsearchDocuments/", views.QueryElasticsearchDocuments, name="QueryElasticsearchDocuments"),
    
    # Plugin documentation endpoint
    path("GetPluginDocumentation/", views.GetPluginDocumentation, name="GetPluginDocumentation")

]