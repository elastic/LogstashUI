#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Django management command to unload test SNMP data

Usage:
    python manage.py unload_test_snmp_data
    python manage.py unload_test_snmp_data --confirm
"""

from django.core.management.base import BaseCommand
from SNMP.models import Network, Device


class Command(BaseCommand):
    help = 'Remove all test SNMP data (networks and devices)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt and delete immediately',
        )

    def handle(self, *args, **options):
        # Count existing test data (only test_ prefixed items)
        test_devices = Device.objects.filter(name__startswith='test_')
        test_networks = Network.objects.filter(name__startswith='test_')
        
        test_device_count = test_devices.count()
        test_network_count = test_networks.count()
        
        if test_device_count == 0 and test_network_count == 0:
            self.stdout.write(self.style.WARNING('No test data to delete - no test_ prefixed items found'))
            return
        
        # Show what will be deleted
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.WARNING('WARNING: This will delete TEST SNMP data'))
        self.stdout.write('='*60)
        self.stdout.write(f'Test networks to delete: {test_network_count}')
        self.stdout.write(f'Test devices to delete:  {test_device_count}')
        self.stdout.write('='*60)
        self.stdout.write(self.style.SUCCESS('(Your real data will NOT be affected)'))
        self.stdout.write('='*60 + '\n')
        
        # Confirm deletion unless --confirm flag is used
        if not options['confirm']:
            confirmation = input('Are you sure you want to delete all test SNMP data? Type "yes" to confirm: ')
            if confirmation.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Deletion cancelled'))
                return
        
        # Delete test devices and networks
        self.stdout.write('\nDeleting test SNMP data...')
        
        # Delete devices first (foreign key constraint)
        self.stdout.write('  Deleting test devices...')
        test_devices.delete()
        self.stdout.write(self.style.SUCCESS(f'  [OK] Deleted {test_device_count} test devices'))
        
        # Delete networks
        self.stdout.write('  Deleting test networks...')
        test_networks.delete()
        self.stdout.write(self.style.SUCCESS(f'  [OK] Deleted {test_network_count} test networks'))
        
        # Print summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('TEST DATA UNLOAD COMPLETE'))
        self.stdout.write('='*60)
        self.stdout.write(f'Test networks deleted:  {test_network_count}')
        self.stdout.write(f'Test devices deleted:   {test_device_count}')
        self.stdout.write('='*60)
