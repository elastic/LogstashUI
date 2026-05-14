#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import path
from . import agent_api, simulation, manager_views, editor_views, policies_crud, agent_policies, connections_crud, \
    pipelines_crud

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

    path("GetConnections/", connections_crud.GetConnections, name="GetConnections"),
    path("AddConnection", connections_crud.AddConnection, name="AddConnection"),
    path("DeleteConnection/<int:connection_id>/", connections_crud.DeleteConnection, name="DeleteConnection"),
    path("UpgradeAgent/<int:connection_id>/", connections_crud.UpgradeAgent, name="UpgradeAgent"),
    path("ChangeConnectionPolicy/", connections_crud.change_connection_policy, name="ChangeConnectionPolicy"),
    path("RestartLogstash/", connections_crud.restart_logstash, name="RestartLogstash"),
    path("GetPipelines/<int:connection_id>/", connections_crud.GetPipelines, name="GetPipelines"),
    path("GetPolicyPipelines/", connections_crud.GetPolicyPipelines, name="GetPolicyPipelines"),
    
    path("GetPolicies/", policies_crud.get_policies, name="GetPolicies"),
    path("AddPolicy/", policies_crud.add_policy, name="AddPolicy"),
    path("UpdatePolicy/", policies_crud.update_policy, name="UpdatePolicy"),
    path("DeletePolicy/", policies_crud.delete_policy, name="DeletePolicy"),
    path("ClonePolicy/", policies_crud.clone_policy, name="ClonePolicy"),
    path("GetEnrollmentTokens/", policies_crud.get_enrollment_tokens, name="GetEnrollmentTokens"),
    path("AddEnrollmentToken/", policies_crud.add_enrollment_token, name="AddEnrollmentToken"),
    path("DeleteEnrollmentToken/", policies_crud.delete_enrollment_token, name="DeleteEnrollmentToken"),

    path("GetPolicyDiff/", agent_policies.get_policy_diff, name="GetPolicyDiff"),
    path("GetPolicyAgentCount/", agent_policies.get_policy_agent_count, name="GetPolicyAgentCount"),
    path("GetPolicyChangeCount/", agent_policies.get_policy_change_count, name="GetPolicyChangeCount"),
    path("DeployPolicy/", agent_policies.deploy_policy, name="DeployPolicy"),
    path("GenerateEnrollmentToken/", agent_policies.generate_enrollment_token, name="GenerateEnrollmentToken"),

    path("Enroll/", agent_api.enroll, name="Enroll"),
    path("CheckIn/", agent_api.check_in, name="CheckIn"),
    path("GetConfigChanges/", agent_api.get_config_changes, name="GetConfigChanges"),
    
    path("GetKeystoreEntries/", agent_policies.get_keystore_entries, name="GetKeystoreEntries"),
    path("CreateKeystoreEntry/", agent_policies.create_keystore_entry, name="CreateKeystoreEntry"),
    path("UpdateKeystoreEntry/", agent_policies.update_keystore_entry, name="UpdateKeystoreEntry"),
    path("DeleteKeystoreEntry/", agent_policies.delete_keystore_entry, name="DeleteKeystoreEntry"),
    path("SetKeystorePassword/", agent_policies.set_keystore_password, name="SetKeystorePassword"),
    path("GetPolicyNodes/", agent_policies.get_policy_nodes, name="GetPolicyNodes"),

    path("GetCurrentPipelineCode/", editor_views.GetCurrentPipelineCode, name="GetCurrentPipelineCode"),
    path("GetDiff/", editor_views.GetDiff, name="GetDiff"),
    path("SavePipeline/", editor_views.SavePipeline, name="SavePipeline"),
    path("ComponentsToConfig/", editor_views.ComponentsToConfig, name="ComponentsToConfig"),
    path("ConfigToComponents/", editor_views.ConfigToComponents, name="ConfigToComponents"),

    path("UpdatePipelineSettings/", pipelines_crud.UpdatePipelineSettings, name="UpdatePipelineSettings"),
    path("CreatePipeline/", pipelines_crud.CreatePipeline, name="CreatePipeline"),
    path("DeletePipeline/", pipelines_crud.DeletePipeline, name="DeletePipeline"),
    path("ClonePipeline/", pipelines_crud.ClonePipeline, name="ClonePipeline"),
    path("RenamePipeline/", pipelines_crud.RenamePipeline, name="RenamePipeline"),
    path("UpdatePipelineDescription/", pipelines_crud.UpdatePipelineDescription, name="UpdatePipelineDescription"),
    path("GetPipeline/", pipelines_crud.GetPipeline, name="GetPipeline"),

    # Elasticsearch simulation endpoints
    path("GetElasticsearchConnections/", editor_views.GetElasticsearchConnections, name="GetElasticsearchConnections"),
    path("GetElasticsearchIndices/", editor_views.GetElasticsearchIndices, name="GetElasticsearchIndices"),
    path("GetElasticsearchFields/", editor_views.GetElasticsearchFields, name="GetElasticsearchFields"),
    path("QueryElasticsearchDocuments/", editor_views.QueryElasticsearchDocuments, name="QueryElasticsearchDocuments"),
    
    # Plugin documentation endpoint
    path("GetPluginDocumentation/", editor_views.GetPluginDocumentation, name="GetPluginDocumentation"),

    # Agent inspect modal — fresh data on each open
    path("AgentInspect/<int:connection_id>/", manager_views.get_agent_inspect, name="AgentInspect"),

    # SSE: real-time agent status stream
    path("AgentStatusStream/", manager_views.agent_status_stream, name="AgentStatusStream")

]
