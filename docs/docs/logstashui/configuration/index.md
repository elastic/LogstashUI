# Configuration

LogstashUI is configured through the `logstashui.yml` file in the project root. This section covers the main configuration options and setup guides.

---

## Configuration Files

### **[logstashui.yml](logstashui.yml.md)**

The main configuration file for LogstashUI. Controls authentication, simulation mode, and Logstash agent settings.

**Key settings:**
- Authentication (`no_auth`)
- Simulation mode (embedded vs host)
- Logstash agent paths and configuration

**📖 [View full logstashui.yml documentation →](logstashui.yml.md)**

---

## Simulation Configuration

### **[Simulation Modes](simulation.md)**

LogstashUI supports two simulation modes for testing pipelines:

- **Embedded Mode** - Runs Logstash in a Docker container (simple setup, slower performance)
- **Host Mode** - Runs Logstash natively on your host machine (requires setup, high performance)

**📖 [View simulation configuration guide →](simulation.md)**

---

### **[Host Mode Setup](host_mode.md)**

Complete guide for setting up host mode for high-performance pipeline simulations.

**Covers:**
- Prerequisites and system requirements
- Logstash installation (Windows & Linux)
- Configuration and startup
- Troubleshooting common issues

**📖 [View host mode setup guide →](host_mode.md)**

---

## Quick Links

- **[Getting Started](../../getting_started.md)** - Initial setup and first steps
- **[LogstashUI Overview](../index.md)** - Feature overview and introduction
