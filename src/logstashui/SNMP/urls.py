#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import path
from . import views
from . import snmp_crud
from . import network_map

urlpatterns = [
    path("Overview/", views.Overview, name="SNMPOverview"),
    path("Networks/", views.Networks, name="Networks"),
    path("Devices/", views.Devices, name="Devices"),
    path("DeviceTemplates/", views.DeviceTemplates, name="DeviceTemplates"),
    path("Profiles/", views.Profiles, name="Profiles"),
    path("Credentials/", views.Credentials, name="Credentials"),
    
    # Overview API endpoints
    path("GetOverviewMetrics/", views.GetOverviewMetrics, name="GetOverviewMetrics"),
    
    # Network Map API endpoints
    path("GetNetworkMapData/", network_map.get_network_map_data, name="GetNetworkMapData"),

    # SNMP Credential endpoints
    path("GetCredentials/", snmp_crud.GetCredentials, name="GetSNMPCredentials"),
    path("AddCredential/", snmp_crud.AddCredential, name="AddSNMPCredential"),
    path("UpdateCredential/<int:credential_id>/", snmp_crud.UpdateCredential, name="UpdateSNMPCredential"),
    path("GetCredential/<int:credential_id>/", snmp_crud.GetCredential, name="GetSNMPCredential"),
    path("DeleteCredential/<int:credential_id>/", snmp_crud.DeleteCredential, name="DeleteSNMPCredential"),

    # SNMP Network endpoints
    path("GetNetworks/", snmp_crud.GetNetworks, name="GetSNMPNetworks"),
    path("AddNetwork/", snmp_crud.AddNetwork, name="AddSNMPNetwork"),
    path("UpdateNetwork/<int:network_id>/", snmp_crud.UpdateNetwork, name="UpdateSNMPNetwork"),
    path("GetNetwork/<int:network_id>/", snmp_crud.GetNetwork, name="GetSNMPNetwork"),
    path("DeleteNetwork/<int:network_id>/", snmp_crud.DeleteNetwork, name="DeleteSNMPNetwork"),
    path("GetNetworkPipelineName/<int:network_id>/", snmp_crud.GetNetworkPipelineName,
         name="GetNetworkPipelineName"),

    # SNMP Deploy endpoints
    path("GetDeployDiff/", snmp_crud.GetDeployDiff, name="GetDeployDiff"),
    path("GenerateDeployConfiguration/", snmp_crud.GenerateDeployConfiguration, name="DeployConfiguration"),
    path("DeployConfiguration/", snmp_crud.DeployConfiguration, name="DeployConfiguration"),

    # SNMP Device endpoints
    path("GetDevices/", snmp_crud.GetDevices, name="GetSNMPDevices"),
    path("AddDevice/", snmp_crud.AddDevice, name="AddSNMPDevice"),
    path("UpdateDevice/<int:device_id>/", snmp_crud.UpdateDevice, name="UpdateSNMPDevice"),
    path("GetDevice/<int:device_id>/", snmp_crud.GetDevice, name="GetSNMPDevice"),
    path("DeleteDevice/<int:device_id>/", snmp_crud.DeleteDevice, name="DeleteSNMPDevice"),
    path("GetDevicesStatus/", snmp_crud.GetDevicesStatus, name="GetDevicesStatus"),
    path("GetDeviceVisualization/<int:device_id>/", snmp_crud.GetDeviceVisualization,
         name="GetDeviceVisualization"),
    path("DiscoveredDevices/", snmp_crud.GetDiscoveredDevices, name="GetDiscoveredDevices"),

    # SNMP Profile endpoints
    path("GetAllProfiles/", snmp_crud.GetAllProfiles, name="GetAllProfiles"),
    path("GetOfficialProfile/<str:profile_name>/", snmp_crud.GetOfficialProfile, name="GetOfficialProfile"),
    path("GetProfile/<str:profile_name>/", snmp_crud.GetProfile, name="GetSNMPProfile"),
    path("AddProfile/", snmp_crud.AddProfile, name="AddSNMPProfile"),
    path("UpdateProfile/<str:profile_name>/", snmp_crud.UpdateProfile, name="UpdateSNMPProfile"),
    path("DeleteProfile/<str:profile_name>/", snmp_crud.DeleteProfile, name="DeleteSNMPProfile"),

    # SNMP Device Template endpoints
    path("GetDeviceTemplates/", snmp_crud.GetDeviceTemplates, name="GetDeviceTemplates"),
    path("GetOfficialDeviceTemplate/<str:template_name>/", snmp_crud.GetOfficialDeviceTemplate, name="GetOfficialDeviceTemplate"),
    path("GetDeviceTemplate/<str:template_id>/", snmp_crud.GetDeviceTemplate, name="GetDeviceTemplate"),
    path("AddDeviceTemplate/", snmp_crud.AddDeviceTemplate, name="AddDeviceTemplate"),
    path("UpdateDeviceTemplate/<int:template_id>/", snmp_crud.UpdateDeviceTemplate, name="UpdateDeviceTemplate"),
    path("DeleteDeviceTemplate/<int:template_id>/", snmp_crud.DeleteDeviceTemplate, name="DeleteDeviceTemplate"),

]