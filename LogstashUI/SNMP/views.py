from django.shortcuts import render
from .models import Credential

# Create your views here.
def Networks(request):
    return render(request, 'SNMP/Networks.html')

def Devices(request):
    return render(request, 'SNMP/Devices.html')

def Profiles(request):
    return render(request, 'SNMP/Profiles.html')

def Credentials(request):
    credentials = Credential.objects.all()
    return render(request, 'Credentials.html', {'credentials': credentials})