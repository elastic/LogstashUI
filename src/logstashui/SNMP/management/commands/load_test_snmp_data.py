#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Django management command to load test SNMP data

Usage:
    python manage.py load_test_snmp_data [--networks N] [--devices N] [--confirm]
    
Examples:
    python manage.py load_test_snmp_data --networks 10 --devices 100
    python manage.py load_test_snmp_data --networks 500 --devices 20000 --confirm
"""

from django.core.management.base import BaseCommand
import random
import ipaddress
from SNMP.models import Network, Device, Credential, DeviceTemplate
from PipelineManager.models import Connection


class Command(BaseCommand):
    help = 'Load test data into SNMP database (default: 300 networks, 10,000 devices)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt and load immediately',
        )
        parser.add_argument(
            '--networks',
            type=int,
            default=300,
            help='Number of test networks to create (default: 300)',
        )
        parser.add_argument(
            '--devices',
            type=int,
            default=10000,
            help='Number of test devices to create (default: 10000)',
        )

    def generate_random_network(self):
        """Generate a random private network in CIDR notation"""
        ranges = [
            (10, 0, 0, 0, 8),
            (172, 16, 0, 0, 12),
            (192, 168, 0, 0, 16),
        ]
        
        range_choice = random.choice(ranges)
        
        if range_choice[0] == 10:
            second = random.randint(0, 255)
            third = random.randint(0, 255)
            prefix = random.choice([16, 24])
            return f"10.{second}.{third}.0/{prefix}"
        
        elif range_choice[0] == 172:
            second = random.randint(16, 31)
            third = random.randint(0, 255)
            prefix = random.choice([16, 24])
            return f"172.{second}.{third}.0/{prefix}"
        
        else:
            third = random.randint(0, 255)
            return f"192.168.{third}.0/24"

    def generate_random_ip(self, network_cidr):
        """Generate a random IP address within a network"""
        network = ipaddress.ip_network(network_cidr, strict=False)
        hosts = list(network.hosts())
        if hosts:
            return str(random.choice(hosts))
        return str(network.network_address)

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting test data load...'))
        
        # Check existing test data (only delete test_ prefixed items)
        test_devices = Device.objects.filter(name__startswith='test_')
        test_networks = Network.objects.filter(name__startswith='test_')
        
        test_device_count = test_devices.count()
        test_network_count = test_networks.count()
        
        if test_device_count > 0 or test_network_count > 0:
            # Show what will be deleted
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.WARNING('WARNING: This will delete existing TEST data'))
            self.stdout.write('='*60)
            self.stdout.write(f'Test networks to delete: {test_network_count}')
            self.stdout.write(f'Test devices to delete:  {test_device_count}')
            self.stdout.write('='*60)
            self.stdout.write(self.style.SUCCESS('(Your real data will NOT be affected)'))
            self.stdout.write('='*60 + '\n')
            
            # Confirm deletion unless --confirm flag is used
            if not options['confirm']:
                confirmation = input('Delete existing test data and load new test data? Type "yes" to confirm: ')
                if confirmation.lower() != 'yes':
                    self.stdout.write(self.style.ERROR('Data load cancelled'))
                    return
        
        # Delete only test devices and networks
        if test_device_count > 0 or test_network_count > 0:
            self.stdout.write('\nDeleting existing test data...')
            test_devices.delete()
            test_networks.delete()
            self.stdout.write(self.style.WARNING(f'Deleted {test_device_count} test devices and {test_network_count} test networks'))
        
        # Get existing credentials and device templates
        credentials = list(Credential.objects.all())
        device_templates = list(DeviceTemplate.objects.all())
        
        # Get Homelab connection
        try:
            homelab_connection = Connection.objects.get(name='Homelab')
        except Connection.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                'ERROR: Homelab connection not found. Please create a connection named "Homelab" first.'
            ))
            return
        
        if not credentials:
            self.stdout.write(self.style.ERROR(
                'ERROR: No credentials found. Please create at least one credential first.'
            ))
            return
        
        if not device_templates:
            self.stdout.write(self.style.WARNING(
                'WARNING: No device templates found. All devices will be created without templates.'
            ))
        
        num_networks = options['networks']
        num_devices = options['devices']
        
        self.stdout.write(f'Found {len(credentials)} credentials and {len(device_templates)} device templates')
        self.stdout.write(f'Using connection: {homelab_connection.name}')
        self.stdout.write(f'Will create {num_networks} networks and {num_devices} devices')
        
        # Create networks
        self.stdout.write(f'\nCreating {num_networks} networks...')
        networks = []
        network_names = set()
        
        for i in range(num_networks):
            while True:
                name = f"test_Network_{random.choice(['Corp', 'Branch', 'DC', 'Remote', 'Site', 'Office'])}_{i+1:03d}"
                if name not in network_names:
                    network_names.add(name)
                    break
            
            network_range = self.generate_random_network()
            credential = random.choice(credentials) if random.random() > 0.5 else None
            
            network = Network.objects.create(
                name=name,
                network_range=network_range,
                connection=homelab_connection,
                discovery_enabled=random.choice([True, False]),
                traps_enabled=random.choice([True, False]),
                credential=credential
            )
            networks.append(network)
            
            if (i + 1) % 50 == 0:
                self.stdout.write(f'  Created {i + 1} networks...')
        
        self.stdout.write(self.style.SUCCESS(f'[OK] Created {len(networks)} networks'))
        
        # Create devices
        self.stdout.write(f'\nCreating {num_devices} devices...')
        device_names = set()
        devices_created = 0
        
        device_types = ['Switch', 'Router', 'Firewall', 'Server', 'AP', 'Printer', 'Camera', 'Sensor']
        locations = ['Floor1', 'Floor2', 'Floor3', 'Basement', 'Roof', 'Closet', 'Rack', 'Lab']
        
        for i in range(num_devices):
            while True:
                device_type = random.choice(device_types)
                location = random.choice(locations)
                number = random.randint(1, 999)
                name = f"test_{device_type}_{location}_{number:03d}"
                if name not in device_names:
                    device_names.add(name)
                    break
            
            network = random.choice(networks)
            ip_address = self.generate_random_ip(network.network_range)
            credential = random.choice(credentials)
            port = random.choice([161, 161, 161, 162, 10161])
            retries = random.randint(1, 5)
            timeout = random.choice([1000, 2000, 3000, 5000])
            
            # Assign random device template if available
            device_template = random.choice(device_templates) if device_templates else None
            
            device = Device.objects.create(
                name=name,
                ip_address=ip_address,
                port=port,
                retries=retries,
                timeout=timeout,
                credential=credential,
                network=network,
                device_template=device_template
            )
            
            devices_created += 1
            
            if (i + 1) % 1000 == 0:
                self.stdout.write(f'  Created {i + 1} devices...')
        
        self.stdout.write(self.style.SUCCESS(f'[OK] Created {devices_created} devices'))
        
        # Count devices per template
        devices_with_templates = Device.objects.filter(
            name__startswith='test_',
            device_template__isnull=False
        ).count()
        
        # Print summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('DATA LOAD COMPLETE'))
        self.stdout.write('='*60)
        self.stdout.write(f'Networks created:        {len(networks)}')
        self.stdout.write(f'Devices created:         {devices_created}')
        if device_templates:
            self.stdout.write(f'  With templates:        {devices_with_templates}')
            self.stdout.write(f'  Without templates:     {devices_created - devices_with_templates}')
        self.stdout.write(f'Using credentials:       {len(credentials)}')
        self.stdout.write(f'Available templates:     {len(device_templates)}')
        self.stdout.write('='*60)
