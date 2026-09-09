#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Sync official SNMP profiles and device templates from bundled JSON.

Treats package JSON as the registry. `--cleanup` deletes unused official rows
whose `official_key` is gone; rows still in use are marked orphaned.

Examples:
    python manage.py sync_snmp_official_data
    python manage.py sync_snmp_official_data --cleanup
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
import json
import logging
import os

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Upsert official profiles and templates from `SNMP/data/` JSON."""
    help = 'Sync official SNMP profiles and device templates from bundled JSON files'

    def add_arguments(self, parser):
        """Add `--cleanup` to delete or orphan stale official rows."""
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help=(
                'Remove stale official records that no longer exist in the bundled registry '
                'and are not in use. Records still in use are marked orphaned instead.'
            ),
        )

    def handle(self, *args, **options):
        """Sync profiles then templates, optionally cleaning stale official rows."""
        cleanup = options.get('cleanup', False)

        try:
            self.stdout.write(self.style.NOTICE('Starting SNMP official data sync...'))

            # Collect the current bundled registry keys BEFORE syncing so we
            # can compare against what is in the DB afterwards.
            registered_profile_keys = self._get_registered_profile_keys()
            registered_template_keys = self._get_registered_template_keys()

            self.stdout.write(
                f'Registry: {len(registered_profile_keys)} profiles, '
                f'{len(registered_template_keys)} device templates'
            )

            # Step 1: Sync official profiles (must happen first — templates depend on profiles)
            self.stdout.write('Syncing official profiles...')
            profiles_synced = self._sync_official_profiles()
            self.stdout.write(self.style.SUCCESS(f'  Synced {profiles_synced} official profiles'))

            # Step 2: Sync official device templates
            self.stdout.write('Syncing official device templates...')
            templates_synced = self._sync_official_device_templates()
            self.stdout.write(self.style.SUCCESS(f'  Synced {templates_synced} official device templates'))

            # Step 3: Cleanup stale official records (only when explicitly requested)
            if cleanup:
                self.stdout.write('Cleaning up stale official data...')
                result = self._cleanup_stale_official_data(
                    registered_profile_keys,
                    registered_template_keys,
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  Profiles  — deleted: {result["profiles_deleted"]}, '
                    f'orphaned: {result["profiles_orphaned"]}'
                ))
                self.stdout.write(self.style.SUCCESS(
                    f'  Templates — deleted: {result["templates_deleted"]}, '
                    f'orphaned: {result["templates_orphaned"]}'
                ))

            self.stdout.write(self.style.SUCCESS('\nSNMP official data sync completed successfully'))

        except Exception as e:
            logger.error(f'Error during SNMP official data sync: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            self.stdout.write(self.style.WARNING('Continuing startup despite sync error'))

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def _get_registered_profile_keys(self):
        """Return `official_key` values from bundled `official_profiles` JSON."""
        keys = set()
        dirpath = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
        if not os.path.exists(dirpath):
            return keys
        for fname in os.listdir(dirpath):
            if not fname.endswith('.json'):
                continue
            try:
                with open(os.path.join(dirpath, fname), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                key = data.get('official_key')
                if key:
                    keys.add(key)
            except Exception as e:
                logger.warning(f'Could not read profile registry file {fname}: {e}')
        return keys

    def _get_registered_template_keys(self):
        """Return `official_key` values from bundled `official_device_templates` JSON."""
        keys = set()
        dirpath = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_device_templates')
        if not os.path.exists(dirpath):
            return keys
        for fname in os.listdir(dirpath):
            if not fname.endswith('.json'):
                continue
            try:
                with open(os.path.join(dirpath, fname), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                key = data.get('official_key')
                if key:
                    keys.add(key)
            except Exception as e:
                logger.warning(f'Could not read template registry file {fname}: {e}')
        return keys

    # ------------------------------------------------------------------
    # Sync helpers (delegate to snmp_crud functions)
    # ------------------------------------------------------------------

    def _sync_official_profiles(self):
        """Sync official profiles and return how many official profile rows exist."""
        from SNMP.snmp_crud import sync_official_profiles
        from SNMP.models import Profile
        try:
            sync_official_profiles()
            return Profile.objects.filter(official_key__isnull=False).count()
        except Exception as e:
            logger.error(f'Error syncing official profiles: {str(e)}', exc_info=True)
            raise

    def _sync_official_device_templates(self):
        """Sync official templates and return how many official template rows exist."""
        from SNMP.snmp_crud import sync_official_device_templates
        from SNMP.models import DeviceTemplate
        try:
            sync_official_device_templates()
            return DeviceTemplate.objects.filter(official=True).count()
        except Exception as e:
            logger.error(f'Error syncing official device templates: {str(e)}', exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @transaction.atomic
    def _cleanup_stale_official_data(self, registered_profile_keys, registered_template_keys):
        """Delete unused official rows missing from the registry; orphan in-use ones.

        A row is stale when its `official_key` is not in the registry (or it is an
        old official placeholder with no key). In-use profiles get
        `profile_data['is_orphaned']=True`; in-use templates are logged, not deleted.

        Args:
            registered_profile_keys: Keys present in bundled profile JSON.
            registered_template_keys: Keys present in bundled template JSON.

        Returns:
            Counts of deleted and orphaned profiles and templates.
        """
        from SNMP.models import Profile, DeviceTemplate

        result = {
            'profiles_deleted': 0,
            'profiles_orphaned': 0,
            'templates_deleted': 0,
            'templates_orphaned': 0,
        }

        # --- Stale official profiles ---
        # Two stale categories (same logic as templates):
        # 1. Has official_key but it's no longer in the bundled registry
        stale_profiles_by_key = set(
            Profile.objects.filter(official_key__isnull=False)
            .exclude(official_key__in=registered_profile_keys)
            .values_list('id', flat=True)
        )
        # 2. Old-style official placeholder (no official_key after sync = no backing JSON)
        stale_profiles_by_flag = set(
            Profile.objects.filter(
                official_key__isnull=True,
                profile_data__has_key='is_official_placeholder'
            ).values_list('id', flat=True)
        )
        stale_profiles = Profile.objects.filter(
            id__in=stale_profiles_by_key | stale_profiles_by_flag
        )

        for profile in stale_profiles:
            if profile.device_templates.exists():
                # Still in use — mark as orphaned rather than deleting
                profile.profile_data = {
                    **profile.profile_data,
                    'is_orphaned': True,
                }
                profile.save(update_fields=['profile_data'])
                result['profiles_orphaned'] += 1
                self.stdout.write(self.style.WARNING(
                    f'  Orphaned (in use): profile "{profile.name}" '
                    f'[official_key={profile.official_key}]'
                ))
            else:
                self.stdout.write(
                    f'  Deleting unused stale profile "{profile.name}" '
                    f'[official_key={profile.official_key}]'
                )
                profile.delete()
                result['profiles_deleted'] += 1

        # --- Stale official device templates ---
        # Two stale categories (combined via ID union to avoid duplicates):
        #
        # 1. Has an official_key but it's no longer in the bundled registry
        #    (template JSON was removed or renamed without a backfill)
        stale_by_key = set(
            DeviceTemplate.objects.filter(official_key__isnull=False)
            .exclude(official_key__in=registered_template_keys)
            .values_list('id', flat=True)
        )
        # 2. Marked official=True but still has no official_key after sync ran
        #    (the sync backfills official_key for any JSON that exists, so NULL
        #    here means the backing JSON is gone)
        stale_by_flag = set(
            DeviceTemplate.objects.filter(official=True, official_key__isnull=True)
            .values_list('id', flat=True)
        )
        stale_templates = DeviceTemplate.objects.filter(id__in=stale_by_key | stale_by_flag)

        for template in stale_templates:
            if template.devices.exists():
                # Still in use — log prominently; do not delete
                result['templates_orphaned'] += 1
                self.stdout.write(self.style.WARNING(
                    f'  Orphaned (in use): template "{template.name}" '
                    f'[official_key={template.official_key}] — '
                    f'{template.devices.count()} device(s) still assigned. '
                    f'Reassign devices before this template can be removed.'
                ))
            else:
                self.stdout.write(
                    f'  Deleting unused stale template "{template.name}" '
                    f'[official_key={template.official_key}]'
                )
                template.delete()
                result['templates_deleted'] += 1

        return result
