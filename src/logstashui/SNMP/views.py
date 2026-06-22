#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse

from .models import Credential, Network, Device, Profile, DeviceTemplate
from PipelineManager.forms import ConnectionForm
from .overview import get_discovered_devices_count, get_template_data_categories, get_high_resource_usage

import os
import json


# Create your views here.
def Networks(request):
    networks = Network.objects.select_related('connection').all()
    form = ConnectionForm()
    return render(request, 'Networks.html', {'networks': networks, 'form': form})

def Devices(request):
    devices = Device.objects.all().select_related('credential', 'network', 'device_template')
    templates = DeviceTemplate.objects.all().order_by('-official', 'name')
    credentials = Credential.objects.all().order_by('name')
    form = ConnectionForm()
    return render(request, 'Devices.html', {'devices': devices, 'templates': templates, 'credentials': credentials, 'form': form})

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
                
                official_key = profile_data.get('official_key')
                if not official_key:
                    print(f"Warning: official profile {filename} has no official_key — skipping")
                    continue
                
                # 1. Already migrated — find by official_key (fast path, rename-safe)
                try:
                    profile = Profile.objects.get(official_key=official_key)
                except Profile.DoesNotExist:
                    # 2. Upgrade path — old record exists by name but has no official_key yet
                    try:
                        profile = Profile.objects.get(name=profile_name, official_key__isnull=True)
                        profile.official_key = official_key
                        print(f"Backfilled official_key for existing profile '{profile_name}'")
                    except Profile.DoesNotExist:
                        # 3. Genuinely new record
                        profile = Profile(official_key=official_key, name=profile_name)
                
                # Update all mutable fields and save
                profile.name = profile_name
                profile.description = profile_data.get('description', '')
                profile.vendor = profile_data.get('vendor', '')
                profile.product = profile_data.get('product', '')
                if not isinstance(profile.profile_data, dict) or not profile.profile_data.get('is_official_placeholder'):
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
                
                official_key = template_data.get('official_key')
                if not official_key:
                    print(f"Warning: official template {filename} has no official_key — skipping")
                    continue
                
                display_name = template_data.get('name', template_name)
                
                # 1. Already migrated — find by official_key (fast path, rename-safe)
                try:
                    template = DeviceTemplate.objects.get(official_key=official_key)
                except DeviceTemplate.DoesNotExist:
                    # 2. Upgrade path — old record exists by name but has no official_key yet
                    try:
                        template = DeviceTemplate.objects.get(name=display_name, official_key__isnull=True)
                        template.official_key = official_key
                        print(f"Backfilled official_key for existing template '{display_name}'")
                    except DeviceTemplate.DoesNotExist:
                        # 3. Genuinely new record
                        template = DeviceTemplate(official_key=official_key, name=display_name)
                
                # Update all mutable fields and save
                template.name = display_name
                template.description = template_data.get('description', '')
                template.vendor = template_data.get('vendor', '')
                template.model = template_data.get('model', '')
                template.product = template_data.get('product', '')
                template.type = template_data.get('type', '')
                template.matching_rules = template_data.get('matching_rules', [])
                template.official = True
                template.save()
                
                # Sync profiles — look up by official_key first (rename-proof),
                # with fallbacks for profiles that haven't been migrated yet or are user-created
                profile_names = template_data.get('profiles', [])
                if profile_names:
                    template.profiles.clear()
                    profiles_added = 0
                    for profile_name in profile_names:
                        profile = None
                        # Try official_key (already migrated official profile)
                        try:
                            profile = Profile.objects.get(official_key=profile_name)
                        except Profile.DoesNotExist:
                            pass
                        # Try name with .json extension (un-migrated official profile)
                        if profile is None:
                            try:
                                profile = Profile.objects.get(name=f"{profile_name}.json")
                            except Profile.DoesNotExist:
                                pass
                        # Try bare name (user-created custom profile)
                        if profile is None:
                            try:
                                profile = Profile.objects.get(name=profile_name)
                            except Profile.DoesNotExist:
                                pass
                        
                        if profile is not None:
                            template.profiles.add(profile)
                            profiles_added += 1
                        else:
                            print(f"Warning: Profile '{profile_name}' not found for template '{template.name}'")
                    print(f"Synced template '{template.name}': {profiles_added}/{len(profile_names)} profiles linked")
                
            except Exception as e:
                print(f"Error syncing official template {filename}: {e}")
                continue

def DeviceTemplates(request):
    from django.db.models import Count
    
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
    from django.db.models import Count
    credentials = Credential.objects.annotate(device_count=Count('devices')).order_by('name')
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
        
        # Get template data coverage
        template_coverage_result = get_template_data_categories()

        # Get high resource usage
        high_usage_result = get_high_resource_usage()
        
        # Combine errors from all queries
        all_errors = []
        if discovered_result.get('errors'):
            all_errors.extend(discovered_result.get('errors'))
        if template_coverage_result.get('errors'):
            all_errors.extend(template_coverage_result.get('errors'))
        if high_usage_result.get('errors'):
            all_errors.extend(high_usage_result.get('errors'))
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'total_devices': total_devices,
                'discovered_devices': discovered_result.get('count', 0)
            },
            'data_quality': {
                'templates': template_coverage_result.get('templates', [])
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



