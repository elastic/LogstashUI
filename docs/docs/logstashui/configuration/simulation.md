# Simulation

LogstashUI provides the ability to simulate pipelines using a real Logstash node.



# Runtime Settings
Settings controlled via `logstashui.yml`
## Modes

```yaml
simulation.mode: "embedded" # (embedded | host)
```

- ### Embedded
  Embedded mode runs the Logstash node inside of the container. 
  - **Pros**: Fast to set up and get going. No additional setup
  - **Cons**: Error prone and inconsistent

- ### Host
  Host mode requires the host where LogstashUI is running to have Logstash already installed.
  - **Pros**: Way more consistent and reliable. Highly recommended for people who are doing many simulations and rapid development.
  - **Cons**: Requires you to install Logstash
  - **IMPORTANT**: In this mode, Logstash is fully managed by LogstashAgent. Logstash should not be started, and your configuration files will be modified.

## Host Settings
```yaml
  host:
    logstash_binary: /usr/share/logstash/bin/logstash
    logstash_settings: /etc/logstash/
```

---

## Related Documentation

- **[Host Mode Setup](/docs/docs/logstashui/configuration/host_mode.md)** - Complete guide to setting up host mode
- **[logstashui.yml](/docs/docs/logstashui/configuration/logstashui.yml.md)** - Full configuration reference
- **[Configuration Overview](/docs/docs/logstashui/configuration/index.md)** - Return to configuration index