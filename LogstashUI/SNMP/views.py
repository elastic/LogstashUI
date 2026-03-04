"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

from django.shortcuts import render
from django.conf import settings

from .models import Credential, Network, Device, Profile
from PipelineManager.forms import ConnectionForm
from Common.elastic_utils import get_elastic_connection

import os
import json


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
                
                # Load the JSON file to get description, type, vendor, and pinned
                profile_path = os.path.join(official_profiles_dir, filename)
                description = ''
                profile_type = ''
                vendor = ''
                pinned = False
                try:
                    with open(profile_path, 'r') as f:
                        profile_data = json.load(f)
                        description = profile_data.get('description', '')
                        profile_type = profile_data.get('type', '')
                        vendor = profile_data.get('vendor', '')
                        pinned = profile_data.get('pinned', False)
                except Exception:
                    pass  # If we can't load the file, just use empty values
                
                official_profiles.append({
                    'name': profile_name,
                    'display_name': display_name,
                    'is_official': True,
                    'description': description,
                    'type': profile_type,
                    'vendor': vendor,
                    'pinned': pinned
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
            'is_official': False,
            'description': profile.description,
            'type': profile.type,
            'vendor': profile.vendor
        })
    
    # Add pinned=False to user profiles
    for profile in user_profiles:
        profile['pinned'] = False
    
    # Combine and sort profiles (pinned first, then alphabetically)
    all_profiles = official_profiles + user_profiles
    all_profiles.sort(key=lambda x: (not x.get('pinned', False), x['display_name']))
    
    return render(request, 'Profiles.html', {'profiles': all_profiles})

def Credentials(request):
    credentials = Credential.objects.all()
    return render(request, 'Credentials.html', {'credentials': credentials})



