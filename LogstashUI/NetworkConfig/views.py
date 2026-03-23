from django.shortcuts import render
from .models import Device, Credential, Profile


def Devices(request):
    devices = Device.objects.select_related('credential', 'profile').all()
    return render(request, 'NetworkConfig/Devices.html', {'devices': devices})


def Credentials(request):
    credentials = Credential.objects.all()
    return render(request, 'NetworkConfig/Credentials.html', {'credentials': credentials})


def Profiles(request):
    profiles = Profile.objects.all()
    return render(request, 'NetworkConfig/Profiles.html', {'profiles': profiles})
