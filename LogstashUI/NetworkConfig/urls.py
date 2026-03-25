from django.urls import path
from . import views
from . import netconfig_crud

urlpatterns = [
    # Page views
    path('Devices/', views.Devices, name='NCDevices'),
    path('Credentials/', views.Credentials, name='NCCredentials'),
    path('Profiles/', views.Profiles, name='NCProfiles'),

    # Credential CRUD
    path('GetCredentials/', netconfig_crud.GetCredentials, name='GetNCCredentials'),
    path('GetCredential/<int:credential_id>/', netconfig_crud.GetCredential, name='GetNCCredential'),
    path('AddCredential/', netconfig_crud.AddCredential, name='AddNCCredential'),
    path('UpdateCredential/<int:credential_id>/', netconfig_crud.UpdateCredential, name='UpdateNCCredential'),
    path('DeleteCredential/<int:credential_id>/', netconfig_crud.DeleteCredential, name='DeleteNCCredential'),

    # Device CRUD
    path('GetDevices/', netconfig_crud.GetDevices, name='GetNCDevices'),
    path('GetDevice/<int:device_id>/', netconfig_crud.GetDevice, name='GetNCDevice'),
    path('AddDevice/', netconfig_crud.AddDevice, name='AddNCDevice'),
    path('UpdateDevice/<int:device_id>/', netconfig_crud.UpdateDevice, name='UpdateNCDevice'),
    path('DeleteDevice/<int:device_id>/', netconfig_crud.DeleteDevice, name='DeleteNCDevice'),
    path('TestDevice/<int:device_id>/', netconfig_crud.TestDeviceConnection, name='TestNCDevice'),

    # Profile CRUD
    path('GetProfiles/', netconfig_crud.GetProfiles, name='GetNCProfiles'),
    path('GetProfile/<str:profile_name>/', netconfig_crud.GetProfile, name='GetNCProfile'),
    path('AddProfile/', netconfig_crud.AddProfile, name='AddNCProfile'),
    path('UpdateProfile/<str:profile_name>/', netconfig_crud.UpdateProfile, name='UpdateNCProfile'),
    path('DeleteProfile/<str:profile_name>/', netconfig_crud.DeleteProfile, name='DeleteNCProfile'),
]
