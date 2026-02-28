"""
Django management command to load test SNMP data

Usage:
    python manage.py load_snmp_data
"""

from django.core.management.base import BaseCommand
import random
import ipaddress
from SNMP.models import Network, Device, Credential, Profile
from PipelineManager.models import Connection


class Command(BaseCommand):
    help = 'Load test data into SNMP database (300 networks, 10,000 devices)'

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
        self.stdout.write(self.style.SUCCESS('Starting data load...'))
        
        # Delete all existing devices and networks
        self.stdout.write('\nDeleting existing data...')
        device_count = Device.objects.count()
        network_count = Network.objects.count()
        
        Device.objects.all().delete()
        Network.objects.all().delete()
        
        self.stdout.write(self.style.WARNING(f'Deleted {device_count} devices and {network_count} networks'))
        
        # Get existing credentials and profiles
        credentials = list(Credential.objects.all())
        profiles = list(Profile.objects.all())
        
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
        
        if not profiles:
            self.stdout.write(self.style.WARNING(
                'WARNING: No profiles found. Devices will be created without profiles.'
            ))
        
        self.stdout.write(f'Found {len(credentials)} credentials and {len(profiles)} profiles')
        self.stdout.write(f'Using connection: {homelab_connection.name}')
        
        # Create 300 networks
        self.stdout.write('\nCreating 300 networks...')
        networks = []
        network_names = set()
        
        for i in range(300):
            while True:
                name = f"Network_{random.choice(['Corp', 'Branch', 'DC', 'Remote', 'Site', 'Office'])}_{i+1:03d}"
                if name not in network_names:
                    network_names.add(name)
                    break
            
            network_range = self.generate_random_network()
            credential = random.choice(credentials) if random.random() > 0.5 else None
            
            network = Network.objects.create(
                name=name,
                network_range=network_range,
                connection=homelab_connection,
                logstash_name='logcollector1',
                discovery_enabled=random.choice([True, False]),
                traps_enabled=random.choice([True, False]),
                credential=credential
            )
            networks.append(network)
            
            if (i + 1) % 50 == 0:
                self.stdout.write(f'  Created {i + 1} networks...')
        
        self.stdout.write(self.style.SUCCESS(f'[OK] Created {len(networks)} networks'))
        
        # Create 10,000 devices
        self.stdout.write('\nCreating 10,000 devices...')
        device_names = set()
        devices_created = 0
        
        device_types = ['Switch', 'Router', 'Firewall', 'Server', 'AP', 'Printer', 'Camera', 'Sensor']
        locations = ['Floor1', 'Floor2', 'Floor3', 'Basement', 'Roof', 'Closet', 'Rack', 'Lab']
        
        for i in range(10000):
            while True:
                device_type = random.choice(device_types)
                location = random.choice(locations)
                number = random.randint(1, 999)
                name = f"{device_type}_{location}_{number:03d}"
                if name not in device_names:
                    device_names.add(name)
                    break
            
            network = random.choice(networks)
            ip_address = self.generate_random_ip(network.network_range)
            credential = random.choice(credentials)
            port = random.choice([161, 161, 161, 162, 10161])
            retries = random.randint(1, 5)
            timeout = random.choice([1000, 2000, 3000, 5000])
            
            device = Device.objects.create(
                name=name,
                ip_address=ip_address,
                port=port,
                retries=retries,
                timeout=timeout,
                credential=credential,
                network=network
            )
            
            if profiles:
                num_profiles = random.randint(1, min(3, len(profiles)))
                selected_profiles = random.sample(profiles, num_profiles)
                device.profiles.set(selected_profiles)
            
            devices_created += 1
            
            if (i + 1) % 1000 == 0:
                self.stdout.write(f'  Created {i + 1} devices...')
        
        self.stdout.write(self.style.SUCCESS(f'[OK] Created {devices_created} devices'))
        
        # Print summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('DATA LOAD COMPLETE'))
        self.stdout.write('='*60)
        self.stdout.write(f'Networks created:  {len(networks)}')
        self.stdout.write(f'Devices created:   {devices_created}')
        self.stdout.write(f'Using credentials: {len(credentials)}')
        self.stdout.write(f'Using profiles:    {len(profiles)}')
        self.stdout.write('='*60)
