# LogstashUI

A web-based UI for managing and monitoring Logstash pipelines.

> ⚠️ **Alpha Release** - This project is in active development. Features may change and bugs are expected.

## Features

- **Pipeline Management** - View and manage Logstash pipeline configurations (Centralized pipeline management required, for now)
- **Real-time Monitoring** - Monitor pipeline metrics and performance
- **Connection Manager** - Manage multiple Logstash instances in one UI
- **Log Viewing** - View and filter Logstash logs

## Requirements

- Python 3.10+
- Node.js & npm (for Tailwind CSS)
- Elasticsearch (for metrics via Elastic Agent)

## Quick Start

### 1. Clone the Repository

```bash
````


## For development
### 1. Clone the Repository

```bash
git clone https://github.com/Codyjackson0321/LogstashUI.git
cd LogstashUI
```

### 2. Create Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Migrations

```bash
cd LogstashUI
python manage.py migrate
python manage.py tailwind build
```

### 5. Start the Server

```bash
python manage.py runserver 0.0.0.0:8000
```

Visit `http://localhost:8000` in your browser.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | (hardcoded - change for production) |
| `DEBUG` | Enable debug mode | `True` |
| `ALLOWED_HOSTS` | Allowed hostnames | `*` |

### Connecting to Logstash

1. Log in to LogstashUI
2. Navigate to **Connection Manager**
3. Add your Elasticsearch connection details
4. LogstashUI will discover Logstash instances via Elastic Agent metrics


### Running in Debug Mode

Set `DEBUG = True` in `LogstashUI/LogstashUI/settings.py` for:
- Auto-reload on code changes
- Detailed error pages
- Browser reload integration

### Tailwind CSS

This project uses Django-Tailwind. To compile CSS changes:

```bash
python manage.py tailwind build
```

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/Codyjackson0321/LogstashUI/issues/new).

## License

Copyright 2024–2025 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
