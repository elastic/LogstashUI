from django.shortcuts import render
from .models import Credential, Network

# Create your views here.
def Networks(request):
    networks = Network.objects.all()
    return render(request, 'Networks.html', {'networks': networks})

def Devices(request):
    return render(request, 'Devices.html')

def Profiles(request):
    return render(request, 'Profiles.html')

def Credentials(request):
    credentials = Credential.objects.all()
    return render(request, 'Credentials.html', {'credentials': credentials})