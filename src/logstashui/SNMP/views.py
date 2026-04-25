#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse

from .models import Credential, Network, Device, Profile, DeviceTemplate
from PipelineManager.forms import ConnectionForm
from .overview import get_discovered_devices_count, get_device_data_quality, get_high_resource_usage

import os
import json


# Create your views here.
def Networks(request):
    networks = Network.objects.select_related('connection').all()
    form = ConnectionForm()
    return render(request, 'Networks.html', {'networks': networks, 'form': form})

def Devices(request):
    # Sync official profiles first (needed for device templates)
    sync_official_profiles()
    # Sync official device templates to database
    sync_official_device_templates()
    
    devices = Device.objects.all().select_related('credential', 'network')
    return render(request, 'Devices.html', {'devices': devices})

def sync_official_profiles():
    """Sync official profiles from JSON files to database as placeholders"""
    official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
    
    if not os.path.exists(official_profiles_dir):
        return
    
    for filename in os.listdir(official_profiles_dir):
        if filename.endswith('.json'):
            profile_name = filename  # Keep .json extension for database storage
            
            try:
                profile_path = os.path.join(official_profiles_dir, filename)
                with open(profile_path, 'r') as f:
                    profile_data = json.load(f)
                
                # Get or create the profile in database as a placeholder
                profile, created = Profile.objects.get_or_create(
                    name=profile_name,
                    defaults={
                        'description': profile_data.get('description', ''),
                        'vendor': profile_data.get('vendor', ''),
                        'product': profile_data.get('product', ''),
                        'profile_data': {'is_official_placeholder': True}
                    }
                )
                
                # Update if it already exists (in case JSON was modified)
                if not created:
                    profile.description = profile_data.get('description', '')
                    profile.vendor = profile_data.get('vendor', '')
                    profile.product = profile_data.get('product', '')
                    # Ensure it's marked as a placeholder
                    if not profile.profile_data.get('is_official_placeholder'):
                        profile.profile_data = {'is_official_placeholder': True}
                    profile.save()
                
            except Exception as e:
                print(f"Error syncing official profile {filename}: {e}")
                continue


def sync_official_device_templates():
    """Sync official device templates from JSON files to database"""
    official_templates_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_device_templates')
    
    if not os.path.exists(official_templates_dir):
        return
    
    for filename in os.listdir(official_templates_dir):
        if filename.endswith('.json'):
            template_name = filename[:-5]  # Remove .json extension
            
            try:
                template_path = os.path.join(official_templates_dir, filename)
                with open(template_path, 'r') as f:
                    template_data = json.load(f)
                
                # Get or create the template in database
                template, created = DeviceTemplate.objects.get_or_create(
                    name=template_data.get('name', template_name),
                    defaults={
                        'description': template_data.get('description', ''),
                        'vendor': template_data.get('vendor', ''),
                        'model': template_data.get('model', ''),
                        'product': template_data.get('product', ''),
                        'matching_rules': template_data.get('matching_rules', []),
                        'official': True
                    }
                )
                
                # Update if it already exists (in case JSON was modified)
                if not created:
                    template.description = template_data.get('description', '')
                    template.vendor = template_data.get('vendor', '')
                    template.model = template_data.get('model', '')
                    template.product = template_data.get('product', '')
                    template.matching_rules = template_data.get('matching_rules', [])
                    template.official = True
                    template.save()
                
                # Sync profiles
                profile_names = template_data.get('profiles', [])
                if profile_names:
                    template.profiles.clear()
                    profiles_added = 0
                    for profile_name in profile_names:
                        try:
                            # Official profiles are stored with .json extension in the database
                            stored_name = f"{profile_name}.json"
                            profile = Profile.objects.get(name=stored_name)
                            template.profiles.add(profile)
                            profiles_added += 1
                        except Profile.DoesNotExist:
                            # Try without .json extension (for custom profiles)
                            try:
                                profile = Profile.objects.get(name=profile_name)
                                template.profiles.add(profile)
                                profiles_added += 1
                            except Profile.DoesNotExist:
                                print(f"Warning: Profile '{profile_name}' (or '{stored_name}') not found in database for template '{template.name}'")
                    print(f"Synced template '{template.name}': {profiles_added}/{len(profile_names)} profiles linked")
                
            except Exception as e:
                print(f"Error syncing official template {filename}: {e}")
                continue

def DeviceTemplates(request):
    from django.db.models import Count
    
    # Sync official profiles first (needed for device templates)
    sync_official_profiles()
    # Sync official device templates from JSON to database
    sync_official_device_templates()
    
    # Load all device templates from database (includes synced official templates)
    device_templates = []
    for template in DeviceTemplate.objects.annotate(device_count=Count('devices')).prefetch_related('profiles').order_by('-official', 'name'):
        # Create a friendly display name from the template name
        display_name = template.name.replace('_', ' ').title()
        
        # Count the number of profiles associated with this template
        profile_count = template.profiles.count()
        
        device_templates.append({
            'name': template.name,
            'display_name': display_name,
            'official': template.official,
            'description': template.description,
            'vendor': template.vendor,
            'model': template.model,
            'product': template.product,
            'device_count': template.device_count,
            'profile_count': profile_count,
            'id': template.id
        })
    
    # Load official profiles from JSON files (for Profiles tab)
    official_profiles = []
    official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
    
    if os.path.exists(official_profiles_dir):
        for filename in os.listdir(official_profiles_dir):
            if filename.endswith('.json'):
                profile_name = filename[:-5]  # Remove .json extension
                # Convert filename to display name (e.g., cisco_ios -> Cisco Ios)
                display_name = profile_name.replace('_', ' ').title()
                
                # Load the JSON file to get description, vendor, and product
                profile_path = os.path.join(official_profiles_dir, filename)
                description = ''
                vendor = ''
                product = ''
                try:
                    with open(profile_path, 'r') as f:
                        profile_data = json.load(f)
                        description = profile_data.get('description', '')
                        vendor = profile_data.get('vendor', '')
                        product = profile_data.get('product', '')
                except Exception:
                    profile_data = {}  # If we can't load the file, just use empty dict
                
                # Count how many device templates use this profile
                template_count = DeviceTemplate.objects.filter(profiles__name=profile_name).count()
                
                official_profiles.append({
                    'name': profile_name,
                    'display_name': display_name,
                    'is_official': True,
                    'description': description,
                    'vendor': vendor,
                    'product': product,
                    'profile_data': json.dumps(profile_data),
                    'template_count': template_count
                })
    
    # Load user profiles from database (exclude placeholders)
    user_profiles = []
    for profile in Profile.objects.all():
        # Skip placeholder profiles (those with is_official_placeholder flag)
        if profile.profile_data.get('is_official_placeholder'):
            continue
        
        # Count how many device templates use this profile
        template_count = DeviceTemplate.objects.filter(profiles__id=profile.id).count()
        
        user_profiles.append({
            'name': profile.name,
            'display_name': profile.name.replace('_', ' ').title(),
            'is_official': False,
            'description': profile.description,
            'vendor': profile.vendor,
            'product': profile.product,
            'profile_data': json.dumps(profile.profile_data),
            'template_count': template_count
        })
    
    # Combine and sort profiles alphabetically
    all_profiles = official_profiles + user_profiles
    all_profiles.sort(key=lambda x: x['display_name'])
    
    return render(request, 'DeviceTemplates.html', {
        'device_templates': device_templates,
        'profiles': all_profiles
    })

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
                
                # Load the JSON file to get description and vendor
                profile_path = os.path.join(official_profiles_dir, filename)
                description = ''
                vendor = ''
                try:
                    with open(profile_path, 'r') as f:
                        profile_data = json.load(f)
                        description = profile_data.get('description', '')
                        vendor = profile_data.get('vendor', '')
                except Exception:
                    pass  # If we can't load the file, just use empty values
                
                official_profiles.append({
                    'name': profile_name,
                    'display_name': display_name,
                    'is_official': True,
                    'description': description,
                    'vendor': vendor
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
            'vendor': profile.vendor
        })
    
    # Combine and sort profiles alphabetically
    all_profiles = official_profiles + user_profiles
    all_profiles.sort(key=lambda x: x['display_name'])
    
    return render(request, 'Profiles.html', {'profiles': all_profiles})

def Credentials(request):
    credentials = Credential.objects.all()
    return render(request, 'Credentials.html', {'credentials': credentials})

def Overview(request):
    """SNMP Overview page with metrics and statistics"""
    return render(request, 'Overview.html')

def GetOverviewMetrics(request):
    """API endpoint to get overview metrics"""
    try:
        # Get total devices from database
        total_devices = Device.objects.count()
        
        # Get discovered devices count from Elasticsearch
        discovered_result = get_discovered_devices_count()
        
        # Get device data quality
        data_quality_result = get_device_data_quality()
        
        # Get high resource usage
        high_usage_result = get_high_resource_usage()
        
        # Combine errors from all queries
        all_errors = []
        if discovered_result.get('errors'):
            all_errors.extend(discovered_result.get('errors'))
        if data_quality_result.get('errors'):
            all_errors.extend(data_quality_result.get('errors'))
        if high_usage_result.get('errors'):
            all_errors.extend(high_usage_result.get('errors'))
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'total_devices': total_devices,
                'discovered_devices': discovered_result.get('count', 0)
            },
            'data_quality': {
                'devices': data_quality_result.get('devices', [])
            },
            'high_usage': {
                'high_cpu': high_usage_result.get('high_cpu', []),
                'high_memory': high_usage_result.get('high_memory', [])
            },
            'errors': all_errors if all_errors else None
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def suggest_device_template(device_info):
    """
    Suggest device templates based on matching rules against device information.
    
    Args:
        device_info (str): Device identification string (e.g., sysDescr or sysObject)
    
    Returns:
        list: List of DeviceTemplate IDs ranked by match quality:
              - First: Templates where ALL matching rules match
              - Second: Templates where SOME matching rules match
              - Templates with null/empty matching_rules are excluded
    """
    if not device_info:
        return []
    
    device_info_lower = device_info.lower()
    
    # Get all device templates with matching rules
    templates = DeviceTemplate.objects.exclude(matching_rules__isnull=True).exclude(matching_rules=[])
    
    all_matches = []  # Templates where ALL rules match
    partial_matches = []  # Templates where SOME rules match
    
    for template in templates:
        if not template.matching_rules:
            continue
        
        # Check how many rules match
        matching_count = 0
        total_rules = len(template.matching_rules)
        
        for rule in template.matching_rules:
            if rule.lower() in device_info_lower:
                matching_count += 1
        
        # Categorize based on match quality
        if matching_count == total_rules and total_rules > 0:
            # All rules matched
            all_matches.append(template.id)
        elif matching_count > 0:
            # Some rules matched - sort by match percentage
            partial_matches.append((template.id, matching_count / total_rules))
    
    # Sort partial matches by match percentage (descending)
    partial_matches.sort(key=lambda x: x[1], reverse=True)
    partial_match_ids = [template_id for template_id, _ in partial_matches]
    
    # Return all matches first, then partial matches
    return all_matches + partial_match_ids



