#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Django management command to sync official SNMP profiles and device templates.
This command is designed to run safely during application startup.

Usage:
    python manage.py sync_snmp_official_data [--cleanup]

Options:
    --cleanup    Remove unused official profiles and templates (safe - only removes if not in use)
"""

from django.core.management.base import BaseCommand
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync official SNMP profiles and device templates from JSON files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Remove unused official profiles and templates',
        )

    def handle(self, *args, **options):
        """
        Main command handler - runs sync operations in a safe, non-blocking way
        """
        cleanup = options.get('cleanup', False)
        
        try:
            self.stdout.write(self.style.NOTICE('Starting SNMP official data sync...'))
            
            # Step 1: Sync official profiles (must happen first - templates depend on profiles)
            self.stdout.write('Syncing official profiles...')
            profiles_synced = self._sync_official_profiles()
            self.stdout.write(self.style.SUCCESS(f'✓ Synced {profiles_synced} official profiles'))
            
            # Step 2: Sync official device templates
            self.stdout.write('Syncing official device templates...')
            templates_synced = self._sync_official_device_templates()
            self.stdout.write(self.style.SUCCESS(f'✓ Synced {templates_synced} official device templates'))
            
            # Step 3: Cleanup unused official data (if requested)
            if cleanup:
                self.stdout.write('Cleaning up unused official data...')
                profiles_removed, templates_removed = self._cleanup_unused_official_data()
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Removed {profiles_removed} unused profiles and {templates_removed} unused templates'
                ))
            
            self.stdout.write(self.style.SUCCESS('\n✓ SNMP official data sync completed successfully'))
            return 0
            
        except Exception as e:
            # Log error but don't crash - startup should continue
            logger.error(f'Error during SNMP official data sync: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'✗ Error: {str(e)}'))
            self.stdout.write(self.style.WARNING('⚠ Continuing startup despite sync error'))
            return 1

    def _sync_official_profiles(self):
        """
        Sync official profiles from JSON files to database
        Returns number of profiles synced
        """
        from SNMP.views import sync_official_profiles
        
        try:
            # Call the existing sync function
            sync_official_profiles()
            
            # Count synced profiles (those marked as official placeholders)
            from SNMP.models import Profile
            count = Profile.objects.filter(
                profile_data__has_key='is_official_placeholder'
            ).count()
            
            return count
            
        except Exception as e:
            logger.error(f'Error syncing official profiles: {str(e)}', exc_info=True)
            raise

    def _sync_official_device_templates(self):
        """
        Sync official device templates from JSON files to database
        Returns number of templates synced
        """
        from SNMP.views import sync_official_device_templates
        
        try:
            # Call the existing sync function
            sync_official_device_templates()
            
            # Count synced templates (those marked as official)
            from SNMP.models import DeviceTemplate
            count = DeviceTemplate.objects.filter(official=True).count()
            
            return count
            
        except Exception as e:
            logger.error(f'Error syncing official device templates: {str(e)}', exc_info=True)
            raise

    @transaction.atomic
    def _cleanup_unused_official_data(self):
        """
        Safely remove unused official profiles and templates
        
        Rules:
        - Only remove official profiles that are NOT linked to any device template
        - Only remove official device templates that are NOT assigned to any device
        - Uses database transaction for safety
        
        Returns:
            tuple: (profiles_removed, templates_removed)
        """
        from SNMP.models import Profile, DeviceTemplate
        
        profiles_removed = 0
        templates_removed = 0
        
        try:
            # Find unused official profiles
            # Official profiles have 'is_official_placeholder' in profile_data
            official_profiles = Profile.objects.filter(
                profile_data__has_key='is_official_placeholder'
            )
            
            for profile in official_profiles:
                # Check if profile is used by any device template
                if not profile.device_templates.exists():
                    profile.delete()
                    profiles_removed += 1
            
            # Find unused official device templates
            official_templates = DeviceTemplate.objects.filter(official=True)
            
            for template in official_templates:
                # Check if template is assigned to any device
                if not template.devices.exists():
                    template.delete()
                    templates_removed += 1
            
            return profiles_removed, templates_removed
            
        except Exception as e:
            logger.error(f'Error during cleanup: {str(e)}', exc_info=True)
            # Re-raise to trigger transaction rollback
            raise
