"""
Sync LogstashAgent config from logstashui.yml to LogstashAgent/logstashagent.yml
"""
import yaml
import sys

try:
    # Read main config
    with open('logstashui.yml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Extract agent config
    agent_config = config.get('simulation', {}).get('logstash_agent', {})
    agent_config['simulation_mode'] = 'host'
    
    # Write to agent config file
    with open('LogstashAgent/logstashagent.yml', 'w') as f:
        yaml.dump(agent_config, f)
    
    print("Config synced successfully")
    sys.exit(0)
except Exception as e:
    print(f"Warning: Could not sync config: {e}")
    sys.exit(1)
