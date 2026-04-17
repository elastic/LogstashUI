"""
Sync logstashagent config from logstashui.yml (or logstashui.example.yml) to LogstashAgent/src/logstashagent/logstashagent.yml
"""
import yaml
import sys
import os
from pathlib import Path

try:
    # Check for logstashui.yml first, fallback to logstashui.example.yml
    if os.path.exists('src/logstashui/logstashui.yml'):
        config_file = 'src/logstashui/logstashui.yml'
    elif os.path.exists('src/logstashui/logstashui.example.yml'):
        config_file = 'src/logstashui/logstashui.example.yml'
    else:
        raise FileNotFoundError("No config file found in src/logstashui/")
    
    # Read main config
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Extract agent config
    agent_config = config.get('simulation', {}).get('logstash_agent', {})
    agent_config['simulation_mode'] = 'host'
    
    # Ensure LogstashAgent directory exists
    agent_config_dir = Path('LogstashAgent/src/logstashagent')
    if not agent_config_dir.exists():
        print(f"Warning: {agent_config_dir} does not exist. Agent may not be cloned yet.")
        sys.exit(1)
    
    # Write to agent config file
    agent_config_path = agent_config_dir / 'config' / 'logstashagent.yml'
    with open(agent_config_path, 'w') as f:
        yaml.dump(agent_config, f)
    
    print(f"Config synced successfully to {agent_config_path}")
    sys.exit(0)
except Exception as e:
    print(f"Warning: Could not sync config: {e}")
    sys.exit(1)
