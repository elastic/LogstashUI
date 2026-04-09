---
layout: default
title: Build Guide
description: Instructions for building and running LogstashUI
---

# Building and Running LogstashUI

There are a few different ways to run this project.

--- 

## Using Docker Compose

Use this mode when you want to run LogstashUI with an embedded LogstashAgent for simulation features.

```bash
docker compose up -d
```

This will start:
- LogstashUI web application
- LogstashAgent (for pipeline simulation)

--- 

## Running Locally (For Development)

### Prerequisites

- Python 3.11+
- Django dependencies
- LogstashAgent running separately (see LogstashAgent/docs/build.md)

### Running LogstashUI

#### Linux
```bash
cd src/logstashui
LOGSTASH_CONFIG=../logstashui.example.yml python manage.py runserver 0.0.0.0:8080
```

#### Windows
```bash
cd src/logstashui
$env:LOGSTASH_CONFIG="../logstashui.example.yml"
python manage.py runserver 0.0.0.0:8080
```

### Running LogstashAgent

LogstashAgent is now a separate project. See `LogstashAgent/docs/build.md` for build and run instructions.

