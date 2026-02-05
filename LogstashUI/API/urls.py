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
    
    # SNMP Device endpoints
    path("SNMP/GetDevices/", snmp_views.GetDevices, name="GetSNMPDevices"),
    path("SNMP/AddDevice/", snmp_views.AddDevice, name="AddSNMPDevice"),
    path("SNMP/UpdateDevice/<int:device_id>/", snmp_views.UpdateDevice, name="UpdateSNMPDevice"),
    path("SNMP/GetDevice/<int:device_id>/", snmp_views.GetDevice, name="GetSNMPDevice"),
    path("SNMP/DeleteDevice/<int:device_id>/", snmp_views.DeleteDevice, name="DeleteSNMPDevice"),
]