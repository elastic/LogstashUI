from django.urls import path, include
from . import views
from . import snmp_views

urlpatterns = [
    path('TestConnectivity', views.TestConnectivity, name='TestConnectivity'),

    path("GetConnections/", views.GetConnections, name="GetConnections"),
    path("AddConnection", views.AddConnection, name="AddConnection"),
    path("DeleteConnection/<int:connection_id>/", views.DeleteConnection, name="DeleteConnection"),
    path("GetPipelines/<int:connection_id>/", views.GetPipelines, name="GetPipelines"),


    path("GetCurrentPipelineCode/", views.GetCurrentPipelineCode, name="GetCurrentPipelineCode"),
    path("GetDiff/", views.GetDiff, name="GetDiff"),
    path("SavePipeline/", views.SavePipeline, name="SavePipeline"),
    # path("SimulatePipeline/", views.SimulatePipeline, name="SimulatePipeline"),

    path("UpdatePipelineSettings/", views.UpdatePipelineSettings, name="UpdatePipelineSettings"),
    path("CreatePipeline/", views.CreatePipeline, name="CreatePipeline"),
    path("DeletePipeline/", views.DeletePipeline, name="DeletePipeline"),
    path("ClonePipeline/", views.ClonePipeline, name="ClonePipeline"),
    path("GetPipeline/", views.GetPipeline, name="GetPipeline"),
    
    # Metrics endpoints
    path("GetNodeMetrics", views.GetNodeMetrics, name="GetNodeMetrics"),
    path("GetPipelineMetrics", views.GetPipelineMetrics, name="GetPipelineMetrics"),
    path("GetLogs", views.GetLogs, name="GetLogs"),
    path("GetPipelineHealthReport", views.GetPipelineHealthReport, name="GetPipelineHealthReport"),
    
    # SNMP Credential endpoints
    path("SNMP/GetCredentials/", snmp_views.GetCredentials, name="GetSNMPCredentials"),
    path("SNMP/AddCredential/", snmp_views.AddCredential, name="AddSNMPCredential"),
    path("SNMP/UpdateCredential/<int:credential_id>/", snmp_views.UpdateCredential, name="UpdateSNMPCredential"),
    path("SNMP/GetCredential/<int:credential_id>/", snmp_views.GetCredential, name="GetSNMPCredential"),
    path("SNMP/DeleteCredential/<int:credential_id>/", snmp_views.DeleteCredential, name="DeleteSNMPCredential"),
    
    # SNMP Network endpoints
    path("SNMP/GetNetworks/", snmp_views.GetNetworks, name="GetSNMPNetworks"),
    path("SNMP/AddNetwork/", snmp_views.AddNetwork, name="AddSNMPNetwork"),
    path("SNMP/UpdateNetwork/<int:network_id>/", snmp_views.UpdateNetwork, name="UpdateSNMPNetwork"),
    path("SNMP/GetNetwork/<int:network_id>/", snmp_views.GetNetwork, name="GetSNMPNetwork"),
    path("SNMP/DeleteNetwork/<int:network_id>/", snmp_views.DeleteNetwork, name="DeleteSNMPNetwork"),
    path("SNMP/GetNetworkPipelineName/<int:network_id>/", snmp_views.GetNetworkPipelineName, name="GetNetworkPipelineName"),
    path("SNMP/GetCommitDiff/", snmp_views.GetCommitDiff, name="GetCommitDiff"),
    path("SNMP/GenerateCommitConfiguration/", snmp_views.GenerateCommitConfiguration, name="CommitConfiguration"),
    path("SNMP/CommitConfiguration/", snmp_views.CommitConfiguration, name="CommitConfiguration"),
    
    # SNMP Device endpoints
    path("SNMP/GetDevices/", snmp_views.GetDevices, name="GetSNMPDevices"),
    path("SNMP/AddDevice/", snmp_views.AddDevice, name="AddSNMPDevice"),
    path("SNMP/UpdateDevice/<int:device_id>/", snmp_views.UpdateDevice, name="UpdateSNMPDevice"),
    path("SNMP/GetDevice/<int:device_id>/", snmp_views.GetDevice, name="GetSNMPDevice"),
    path("SNMP/DeleteDevice/<int:device_id>/", snmp_views.DeleteDevice, name="DeleteSNMPDevice"),
    path("SNMP/GetDevicesStatus/", snmp_views.GetDevicesStatus, name="GetDevicesStatus"),
    path("SNMP/GetDeviceVisualization/<int:device_id>/", snmp_views.GetDeviceVisualization, name="GetDeviceVisualization"),
    
    # SNMP Profile endpoints
    path("SNMP/GetAllProfiles/", snmp_views.GetAllProfiles, name="GetAllProfiles"),
    path("SNMP/GetOfficialProfile/<str:profile_name>/", snmp_views.GetOfficialProfile, name="GetOfficialProfile"),
    path("SNMP/GetProfile/<str:profile_name>/", snmp_views.GetProfile, name="GetSNMPProfile"),
    path("SNMP/AddProfile/", snmp_views.AddProfile, name="AddSNMPProfile"),
    path("SNMP/UpdateProfile/<str:profile_name>/", snmp_views.UpdateProfile, name="UpdateSNMPProfile"),
    path("SNMP/DeleteProfile/<str:profile_name>/", snmp_views.DeleteProfile, name="DeleteSNMPProfile"),
]