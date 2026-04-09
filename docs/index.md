---
layout: default
title: Home
description: A modern web-based interface for managing and monitoring your Logstash instances and pipelines
---

<div style="text-align: center; margin-bottom: 4rem; padding-top: 2rem;">
    <div style="display: flex; align-items: center; justify-content: center; gap: 1rem; margin-bottom: 1rem;">
        <div style="position: relative; width: 4rem; height: 4rem;">
            <div style="position: absolute; inset: 0; background: rgba(168, 85, 247, 0.15); border-radius: 9999px; filter: blur(1rem);"></div>
            <img src="{{ '/images/LogstashIcon.png' | relative_url }}" alt="Logstash UI" style="width: 100%; height: 100%; object-fit: contain; position: relative; z-index: 10;">
        </div>
        <h1 style="font-size: 3rem; font-weight: bold; color: white; margin: 0;">LogstashUI</h1>
    </div>
    <p style="font-size: 1.25rem; color: #d1d5db; max-width: 48rem; margin: 0 auto 2rem;">
        A modern web-based interface for managing and monitoring your Logstash instances and pipelines
    </p>
    <div style="display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem;">
        <a href="#getting-started" style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; background: #9333ea; color: white; border-radius: 0.5rem; font-weight: 500; text-decoration: none;">Get Started</a>
        <a href="https://github.com/elastic/LogstashUI" target="_blank" rel="noopener noreferrer" style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; background: #374151; color: white; border-radius: 0.5rem; font-weight: 500; text-decoration: none;">View on GitHub</a>
    </div>
</div>

<div id="getting-started"></div>

## Getting Started

LogstashUI provides an intuitive interface for managing Logstash pipelines, monitoring performance, and configuring SNMP devices. Get up and running in minutes with our streamlined installation process.

**Quick install with Docker:**

```bash
docker pull elastic/logstashui:latest
docker run -p 8000:8000 elastic/logstashui:latest
```

Visit `http://localhost:8000` to access the interface.

---

## Features

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin: 2rem 0;">
    <div style="background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; padding: 1.5rem;">
        <h3 style="color: #60a5fa; margin-top: 0;">Pipeline Management</h3>
        <p>Create, edit, and manage Logstash pipelines with an intuitive visual editor and text-based configuration options.</p>
    </div>
    <div style="background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; padding: 1.5rem;">
        <h3 style="color: #4ade80; margin-top: 0;">Real-time Monitoring</h3>
        <p>Monitor pipeline metrics, performance, and health in real-time across all your Logstash instances.</p>
    </div>
    <div style="background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; padding: 1.5rem;">
        <h3 style="color: #c084fc; margin-top: 0;">SNMP Integration</h3>
        <p>Configure SNMP devices, profiles, and credentials for comprehensive network monitoring.</p>
    </div>
    <div style="background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; padding: 1.5rem;">
        <h3 style="color: #facc15; margin-top: 0;">Grok Debugger</h3>
        <p>Test and debug Grok patterns with an integrated debugger to ensure your log parsing works correctly.</p>
    </div>
</div>

---

<div id="installation"></div>

## Installation

### Prerequisites

- Docker and Docker Compose (recommended)
- Python 3.9+ (for manual installation)
- Elasticsearch cluster (for centralized pipeline management)
- Logstash 8.x+ instances

### Docker Installation (Recommended)

```bash
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
docker-compose up -d
```

The application will be available at `http://localhost:8000`

### Manual Installation

```bash
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Access the application at `http://localhost:8000`

---

<div id="configuration"></div>

## Configuration

### Environment Variables

Configure LogstashUI using environment variables or a `.env` file:

```bash
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/logstashui

# Security
SECRET_KEY=your-secret-key-here
DEBUG=False

# Elasticsearch Connection
ELASTICSEARCH_HOST=https://localhost:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=changeme
```

### Adding Connections

LogstashUI supports two types of connections:

- **Elasticsearch (Centralized Management):** Manage pipelines stored in Elasticsearch
- **Logstash Agent:** Direct connection to Logstash instances with agent-based management

Navigate to **Connection Manager** in the UI to add and configure your connections.

---

<div id="contributing"></div>

## Contributing

We welcome contributions from the community! Whether it's bug fixes, new features, or documentation improvements, your help makes LogstashUI better for everyone.

### How to Contribute

1. Fork the repository on GitHub
2. Create a new branch for your feature or bugfix
3. Make your changes and commit with clear messages
4. Push to your fork and submit a pull request
5. Wait for review and address any feedback

<div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
    <a href="https://github.com/elastic/LogstashUI" target="_blank" rel="noopener noreferrer" style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; background: #374151; color: white; border-radius: 0.5rem; font-weight: 500; text-decoration: none;">View Repository</a>
    <a href="https://github.com/elastic/LogstashUI/issues/new?template=issue.md" target="_blank" rel="noopener noreferrer" style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; background: #9333ea; color: white; border-radius: 0.5rem; font-weight: 500; text-decoration: none;">Report an Issue</a>
</div>

---

## Resources

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; margin: 2rem 0;">
    <a href="https://github.com/elastic/LogstashUI" target="_blank" rel="noopener noreferrer" style="display: flex; align-items: center; gap: 1rem; padding: 1rem; background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; text-decoration: none; color: inherit;">
        <div style="flex: 1;">
            <div style="color: white; font-weight: 600;">GitHub Repository</div>
            <div style="color: #9ca3af; font-size: 0.875rem;">Source code and issue tracking</div>
        </div>
    </a>
    <a href="https://www.elastic.co/guide/en/logstash/current/index.html" target="_blank" rel="noopener noreferrer" style="display: flex; align-items: center; gap: 1rem; padding: 1rem; background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; text-decoration: none; color: inherit;">
        <div style="flex: 1;">
            <div style="color: white; font-weight: 600;">Logstash Documentation</div>
            <div style="color: #9ca3af; font-size: 0.875rem;">Official Elastic documentation</div>
        </div>
    </a>
    <a href="https://discuss.elastic.co/c/logstash/14" target="_blank" rel="noopener noreferrer" style="display: flex; align-items: center; gap: 1rem; padding: 1rem; background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; text-decoration: none; color: inherit;">
        <div style="flex: 1;">
            <div style="color: white; font-weight: 600;">Community Forums</div>
            <div style="color: #9ca3af; font-size: 0.875rem;">Get help from the community</div>
        </div>
    </a>
    <a href="https://github.com/elastic/LogstashUI/issues/new?template=issue.md" target="_blank" rel="noopener noreferrer" style="display: flex; align-items: center; gap: 1rem; padding: 1rem; background: rgba(31, 41, 55, 0.5); border: 1px solid #374151; border-radius: 0.5rem; text-decoration: none; color: inherit;">
        <div style="flex: 1;">
            <div style="color: white; font-weight: 600;">Report an Issue</div>
            <div style="color: #9ca3af; font-size: 0.875rem;">Found a bug? Let us know</div>
        </div>
    </a>
</div>

---

<div style="text-align: center; padding: 2rem 0; border-top: 1px solid #374151; margin-top: 4rem;">
    <p style="color: #9ca3af; font-size: 0.875rem;">
        Copyright © Elasticsearch B.V. Licensed under the Elastic License.
    </p>
    <p style="color: #6b7280; font-size: 0.75rem; margin-top: 0.5rem;">
        LogstashUI is an open-source project maintained by the Elastic community.
    </p>
</div>
