# SNMP Quickstart Guide

Quick start device setup using [centralized pipeline management](https://www.elastic.co/docs/reference/logstash/logstash-centralized-pipeline-management).

## Step 1: Add a Device

Click the **"Add Device"** button in the SNMP Devices page and fill out the form with your device information. You will be prompted to setup a credential, network, or connection if you haven't set those up yet.

### Required Information

- **Device Name**: A descriptive name for your device (e.g., "Core Switch 1")
- **IP Address/Hostname**: The IP address or hostname of the SNMP device
- **Credential**: SNMP credentials (v2c or v3) for authentication
- **Network**: The network this device belongs to
- **Device Template** (optional): A template that defines what metrics to collect

## Step 2: Get Your Pipeline Name

When you've added your device, navigate back to the Devices page and click on the text in the **Network** column to copy your pipeline name. 

!!! info "Important"
    Every network has its own unique pipeline name. This allows you to organize devices into logical groups and manage them with separate Logstash instances if needed.

## Step 3: Configure Logstash

In your `logstash.yml` file, add the pipeline name you copied in Step 2 to the **xpack.management.pipeline.id** list in your configuration file:

```yaml
xpack.management.enabled: true
xpack.management.elasticsearch.hosts: ["https://your-elasticsearch:9200"]
xpack.management.elasticsearch.username: "elastic"
xpack.management.elasticsearch.password: "your-password"
xpack.management.pipeline.id: ["snmp_network_production", "snmp_network_staging"]
```

Then restart Logstash:

```bash
sudo systemctl restart logstash
```

!!! tip
    You can add one or many pipeline names to a single instance of Logstash. You must have the pipeline added to your config for the devices to be monitored.

## Next Steps

Once Logstash is configured and running:

1. **Deploy Changes**: Click the "Deploy Changes" button to push your configuration to Elasticsearch
2. **Monitor Data**: Navigate to Kibana to view your SNMP metrics
3. **Add More Devices**: Repeat the process to add additional devices to your network

## Logstash Agent (Coming Soon)

Instructions for deploying Logstash Agent for distributed monitoring will be available soon.
