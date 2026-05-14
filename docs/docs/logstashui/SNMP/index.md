# SNMP Monitoring

LogstashUI provides comprehensive SNMP monitoring capabilities, allowing you to collect and visualize metrics from network devices, servers, and other SNMP-enabled equipment.

## Overview

The SNMP module enables you to:

- **Monitor Network Devices**: Collect metrics from switches, routers, firewalls, and other network equipment
- **Track Server Health**: Monitor servers and infrastructure components via SNMP
- **Custom Device Templates**: Define what metrics to collect from different device types
- **Centralized Management**: Manage all your SNMP monitoring from a single interface
- **Auto-Discovery**: Automatically discover SNMP devices on your network

## Getting Started

New to SNMP monitoring with LogstashUI? Start here:

- **[Quickstart Guide](Quickstart.md)**: Get up and running in minutes with centralized pipeline management

## Key Concepts

### Devices
Individual network devices or servers you want to monitor via SNMP. Each device has an IP address, credentials, and optionally a device template.

### Networks
Logical groupings of devices. Each network has its own unique Logstash pipeline, allowing you to organize devices and manage them with separate Logstash instances.

### Credentials
SNMP authentication credentials (v2c community strings or v3 security settings) used to query devices.

### Device Templates
Define which SNMP metrics to collect from devices. Templates can include:

- Vendor and model information
- Matching rules for auto-assignment
- Associated profiles that define the actual SNMP queries

### Profiles
Define the actual SNMP OIDs and metrics to collect. Profiles specify:

- GET operations for scalar values
- TABLE operations for tabular data
- Column mappings and transformations

## Deployment Modes

### Centralized Pipeline Management

Use Elasticsearch's centralized pipeline management to deploy and manage SNMP pipelines. This is the recommended approach for most deployments.

[Learn more in the Quickstart Guide](Quickstart.md)

### Logstash Agent (Coming Soon)

Deploy Logstash Agent for distributed monitoring with full remote management capabilities.

## Features

- **Visual Device Preview**: See a visual representation of your device's metrics before deployment
- **Auto-Discovery**: Scan network ranges to automatically discover SNMP devices
- **Official Templates**: Pre-built templates for popular devices from Cisco, Dell, HPE, and more
- **Custom Profiles**: Create your own SNMP profiles for specialized equipment
- **Change Management**: Review and deploy configuration changes with built-in diff viewer
- **Real-time Monitoring**: View device status and metrics in real-time

## Next Steps

- [Quickstart Guide](Quickstart.md) - Get started with SNMP monitoring
- Explore official device templates
- Create custom profiles for your equipment
- Set up auto-discovery for your networks
