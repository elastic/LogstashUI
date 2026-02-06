from django.shortcuts import render
from .models import Credential, Network, Device, Profile
from PipelineManager.forms import ConnectionForm
import os
import json
from django.conf import settings

# Create your views here.
def Networks(request):
    networks = Network.objects.select_related('connection').all()
    form = ConnectionForm()
    return render(request, 'Networks.html', {'networks': networks, 'form': form})

def Devices(request):
    devices = Device.objects.all().select_related('credential', 'network')
    return render(request, 'Devices.html', {'devices': devices})

def Profiles(request):
    # Load official profiles from JSON files
    official_profiles = []
    official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
    
    if os.path.exists(official_profiles_dir):
        for filename in os.listdir(official_profiles_dir):
            if filename.endswith('.json'):
                profile_name = filename[:-5]  # Remove .json extension
                # Convert filename to display name (e.g., cisco_ios -> Cisco Ios)
                display_name = profile_name.replace('_', ' ').title()
                official_profiles.append({
                    'name': profile_name,
                    'display_name': display_name,
                    'is_official': True
                })
    
    # Load user profiles from database (exclude placeholders)
    user_profiles = []
    for profile in Profile.objects.all():
        # Skip placeholder profiles (those with is_official_placeholder flag)
        if profile.profile_data.get('is_official_placeholder'):
            continue
        user_profiles.append({
            'name': profile.name,
            'display_name': profile.name.replace('_', ' ').title(),
            'is_official': False
        })
    
    # Combine and sort profiles
    all_profiles = official_profiles + user_profiles
    all_profiles.sort(key=lambda x: x['display_name'])
    
    return render(request, 'Profiles.html', {'profiles': all_profiles})

def Credentials(request):
    credentials = Credential.objects.all()
    return render(request, 'Credentials.html', {'credentials': credentials})