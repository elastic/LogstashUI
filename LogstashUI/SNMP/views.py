from django.shortcuts import render
from .models import Credential, Network, Device
from PipelineManager.forms import ConnectionForm

# Create your views here.
def Networks(request):
    networks = Network.objects.all()
    form = ConnectionForm()
    return render(request, 'Networks.html', {'networks': networks, 'form': form})

def Devices(request):
    devices = Device.objects.all().select_related('credential', 'network')
    return render(request, 'Devices.html', {'devices': devices})

def Profiles(request):
    return render(request, 'Profiles.html')

def Credentials(request):
    credentials = Credential.objects.all()
    return render(request, 'Credentials.html', {'credentials': credentials})