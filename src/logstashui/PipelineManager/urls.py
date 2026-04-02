#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import path
from . import simulation, manager_views, editor_views


urlpatterns = [

    path("", manager_views.PipelineManager, name="PipelineManager"),
    path("Pipelines/Editor/", editor_views.PipelineEditor, name="PipelineEditor"),
    path("AgentPolicies/", manager_views.AgentPolicies, name="AgentPolicies"),

    path("SimulatePipeline/", simulation.SimulatePipeline, name="SimulatePipeline"),
    path("StreamSimulate/", simulation.StreamSimulate, name="StreamSimulate"),
    path("GetSimulationResults/", simulation.GetSimulationResults, name="GetSimulationResults"),
    path("CheckIfPipelineLoaded/", simulation.CheckIfPipelineLoaded, name="CheckIfPipelineLoaded"),
    path("GetRelatedLogs/", simulation.GetRelatedLogs, name="GetRelatedLogs"),
    path("UploadFile/", simulation.UploadFile, name="UploadFile"),
    path("GetSimulationNodeStatus/", simulation.GetSimulationNodeStatus, name="GetSimulationNodeStatus"),
    path("GetSimulationNodeHealth/", simulation.GetSimulationNodeHealth, name="GetSimulationNodeHealth"),
    path("ValidateLogstashConfig/", simulation.ValidateLogstashConfig, name="ValidateLogstashConfig"),

    path('TestConnectivity', manager_views.TestConnectivity, name='TestConnectivity'),

    path("GetConnections/", manager_views.GetConnections, name="GetConnections"),
    path("AddConnection", manager_views.AddConnection, name="AddConnection"),
    path("DeleteConnection/<int:connection_id>/", manager_views.DeleteConnection, name="DeleteConnection"),
    path("GetPipelines/<int:connection_id>/", manager_views.GetPipelines, name="GetPipelines"),
    path("GetPolicyPipelines/", manager_views.GetPolicyPipelines, name="GetPolicyPipelines"),
    
    path("GetPolicies/", manager_views.get_policies, name="GetPolicies"),
    path("AddPolicy/", manager_views.add_policy, name="AddPolicy"),
    path("UpdatePolicy/", manager_views.update_policy, name="UpdatePolicy"),
    path("DeletePolicy/", manager_views.delete_policy, name="DeletePolicy"),
    path("GetPolicyDiff/", manager_views.get_policy_diff, name="GetPolicyDiff"),
    path("GetPolicyAgentCount/", manager_views.get_policy_agent_count, name="GetPolicyAgentCount"),
    path("DeployPolicy/", manager_views.deploy_policy, name="DeployPolicy"),
    path("GenerateEnrollmentToken/", manager_views.generate_enrollment_token, name="GenerateEnrollmentToken"),
    path("GetEnrollmentTokens/", manager_views.get_enrollment_tokens, name="GetEnrollmentTokens"),
    path("AddEnrollmentToken/", manager_views.add_enrollment_token, name="AddEnrollmentToken"),
    path("DeleteEnrollmentToken/", manager_views.delete_enrollment_token, name="DeleteEnrollmentToken"),
    path("Enroll/", manager_views.enroll, name="Enroll"),
    path("CheckIn/", manager_views.check_in, name="CheckIn"),
    path("GetConfigChanges/", manager_views.get_config_changes, name="GetConfigChanges"),
    
    path("GetKeystoreEntries/", manager_views.get_keystore_entries, name="GetKeystoreEntries"),
    path("CreateKeystoreEntry/", manager_views.create_keystore_entry, name="CreateKeystoreEntry"),
    path("UpdateKeystoreEntry/", manager_views.update_keystore_entry, name="UpdateKeystoreEntry"),
    path("DeleteKeystoreEntry/", manager_views.delete_keystore_entry, name="DeleteKeystoreEntry"),
    path("SetKeystorePassword/", manager_views.set_keystore_password, name="SetKeystorePassword"),

    path("GetCurrentPipelineCode/", editor_views.GetCurrentPipelineCode, name="GetCurrentPipelineCode"),
    path("GetDiff/", editor_views.GetDiff, name="GetDiff"),
    path("SavePipeline/", editor_views.SavePipeline, name="SavePipeline"),
    path("ComponentsToConfig/", editor_views.ComponentsToConfig, name="ComponentsToConfig"),
    path("ConfigToComponents/", editor_views.ConfigToComponents, name="ConfigToComponents"),

    path("UpdatePipelineSettings/", manager_views.UpdatePipelineSettings, name="UpdatePipelineSettings"),
    path("CreatePipeline/", manager_views.CreatePipeline, name="CreatePipeline"),
    path("DeletePipeline/", manager_views.DeletePipeline, name="DeletePipeline"),
    path("ClonePipeline/", manager_views.ClonePipeline, name="ClonePipeline"),
    path("RenamePipeline/", manager_views.RenamePipeline, name="RenamePipeline"),
    path("UpdatePipelineDescription/", manager_views.UpdatePipelineDescription, name="UpdatePipelineDescription"),
    path("GetPipeline/", manager_views.GetPipeline, name="GetPipeline"),

    # Elasticsearch simulation endpoints
    path("GetElasticsearchConnections/", editor_views.GetElasticsearchConnections, name="GetElasticsearchConnections"),
    path("GetElasticsearchIndices/", editor_views.GetElasticsearchIndices, name="GetElasticsearchIndices"),
    path("GetElasticsearchFields/", editor_views.GetElasticsearchFields, name="GetElasticsearchFields"),
    path("QueryElasticsearchDocuments/", editor_views.QueryElasticsearchDocuments, name="QueryElasticsearchDocuments"),
    
    # Plugin documentation endpoint
    path("GetPluginDocumentation/", editor_views.GetPluginDocumentation, name="GetPluginDocumentation")

]