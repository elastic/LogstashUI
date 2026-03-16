# Host Mode - High-Performance Pipeline Simulation

## What is Host Mode?

Host mode runs the LogstashAgent **natively** on your host machine instead of inside a Docker container. This provides more rliable pipeline simulations, making it ideal for users who frequently test and iterate on pipeline configurations.

### Embedded Mode vs Host Mode

| Feature | Embedded Mode                                                                         | Host Mode                      |
|---------|---------------------------------------------------------------------------------------|--------------------------------|
| **Performance** | Error prone with large  pipelines due to container memory allocation                  | Highly reliable                |
| **Setup** | Simple - no dependencies                                                              | Requires Logstash installation |
| **Best For** | Quick start, occasional simulations                                                   | Heavy simulation workloads     |
| **Logstash Required** | ❌ No                                                                                  | ✅ Yes (dedicated instance)     |

> [!WARNING]
> Host mode requires a **dedicated Logstash installation** that is not running any production pipelines. The simulation agent will overwrite configuration files and manage the Logstash process.

---

## Prerequisites

### System Requirements
- **Windows**: Windows 10/11 or Windows Server 2016+
- **Linux**: Ubuntu 20.04+, RHEL 8+, or similar
- **RAM**: 8 GB minimum
- **CPU**: 4 cores minimum

### Software Requirements
1. **[Docker](https://www.docker.com/get-started/)** - For running the LogstashUI and Nginx containers
2. **[Python 3.12+](https://www.python.org/downloads/)** - For running the native LogstashAgent
3. **[Logstash 8.x, 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash)** - Dedicated instance for simulation (must not be running)

---

## Installation

### Step 1: Install Logstash

Download and install Logstash on your host machine:

#### Windows
1. Download Logstash from [elastic.co/downloads/logstash](https://www.elastic.co/downloads/logstash)
2. Extract to a location like `C:\logstash-9.3.1\`
3. Note the installation path - you'll need it for configuration

#### Linux
Follow [these instructions](https://www.elastic.co/docs/reference/logstash/installing-logstash)


> [!IMPORTANT]
> Ensure Logstash is **not running** as a service. The LogstashAgent will manage the Logstash process.

```bash
# Stop Logstash service if running
sudo systemctl stop logstash
sudo systemctl disable logstash
```

### Step 2: Install Python

#### Windows
1. Download Python 3.12+ from [python.org](https://www.python.org/downloads/)
2. During installation, check "Add Python to PATH"
3. Verify installation:
   ```cmd
   python --version
   ```
   
```cmd
set PATH=%PATH%;C:\Python312
```
#### Linux
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3.12 python3-pip python3.12-venv

# Verify installation
python3 --version
```

### Step 3: Clone LogstashUI

```bash
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
```

---

## Configuration

Edit `logstashui.yml` in the project root to configure host mode:

### Windows Example

```yaml
simulation:
  mode: host  # Change from 'embedded' to 'host'

  logstash_agent:
    mode: simulation
    
    # Windows paths - adjust to match your Logstash installation
    logstash_binary: C:\logstash-9.3.1\logstash-9.3.1\bin\logstash.bat
    logstash_settings: C:\logstash-9.3.1\logstash-9.3.1\config
    logstash_log_path: C:\logstash-9.3.1\logstash-9.3.1\logs
```

### Linux Example

```yaml
simulation:
  mode: host  # Change from 'embedded' to 'host'

  logstash_agent:
    mode: simulation
    
    # Linux paths - adjust if you installed Logstash in a custom location
    logstash_binary: /usr/share/logstash/bin/logstash
    logstash_settings: /etc/logstash
    logstash_log_path: /var/log/logstash
```

> [!TIP]
> The default Linux paths shown above work for package manager installations (apt/yum). If you extracted Logstash manually, adjust the paths accordingly.

---

## Running Host Mode

Once configured, start LogstashUI using the startup script:

### Windows

```cmd
cd LogstashUI\bin
start_logstashui.bat
```

### Linux

```bash
cd LogstashUI/bin
./start_logstashui.sh
```

### What Happens During Startup

1. **Script detects host mode** from `logstashui.yml`
2. **Python dependencies** are installed automatically
3. **LogstashAgent starts natively** on your host machine (port 9501)
4. **Docker containers start** for LogstashUI (Django) and Nginx
5. **Nginx proxies** simulation requests from port 9500 to the native agent at 9501

### Verify Host Mode is Running

Check that the LogstashAgent is running natively:

#### Windows
```cmd
netstat -ano | findstr :9501
```

#### Linux
```bash
lsof -i :9501
```

You should see the Python process listening on port 9501.

---

## Accessing LogstashUI

Once started, navigate to:

```
https://<your_server_ip_or_hostname>
```

---

## Troubleshooting

### "Logstash binary not found"

**Cause**: The path in `logstashui.yml` doesn't match your Logstash installation.

**Solution**: 
1. Verify your Logstash installation path
2. Update `logstash_binary` in `logstashui.yml` to match
3. Restart LogstashUI

### "Port 9501 already in use"

**Cause**: Another process is using port 9501, or a previous LogstashAgent didn't shut down cleanly.

**Solution**:
```bash
# Windows
netstat -ano | findstr :9501
taskkill /PID <PID> /F

# Linux
lsof -i :9501
kill -9 <PID>
```

### "Permission denied" on Linux

**Cause**: Logstash directories require elevated permissions.

**Solution**: Ensure your user has read/write access to:
- `/etc/logstash/`
- `/var/log/logstash/`

Or run with appropriate permissions:
```bash
sudo chown -R $USER:$USER /etc/logstash /var/log/logstash
```


## Known Limitations
### Timing precision in Host Mode for Windows

When running in Host mode on Windows, plugin execution times are rounded to whole milliseconds (1.000ms, 2.000ms, etc.) due to JRuby's time precision on Windows.

This means that sub-ms plugin execution get rounded to 0.0ms, resulting in timing not displaying at all for plugins with less than 1ms execution.

This still allows us to see the relative performance of plugins, but it does not provide accurate sub-millisecond timing like you get in every mode other than Windows Host mode.

For accurate sub-millisecond timing during development on Windows, use Embedded mode or Host mode on Linux.