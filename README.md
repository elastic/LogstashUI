# LogstashUI

A web-based UI for managing and monitoring Logstash pipelines.

> ⚠️ **Alpha Release** - This project is in active development. Features may change and bugs are expected.

## Features

- **Pipeline Management** - View and manage Logstash pipeline configurations (Centralized pipeline management required, for now)
- **Real-time Monitoring** - Monitor pipeline metrics and performance
- **Connection Manager** - Manage multiple Logstash instances in one UI
- **Log Viewing** - View and filter Logstash logs

## Requirements

### For Local Development

- Python 3.10+
- Node.js & npm (for Tailwind CSS)
- Elasticsearch

**OR** just use Docker Compose (see Quick Start below)


## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/Codyjackson0321/LogstashUI.git
````

### 2. Start the docker compose
```bash
docker compose up
```

### 3. Navigate to https://{server_ip} and create your initial user
<img width="729" height="887" alt="image" src="https://github.com/user-attachments/assets/c19c6dfb-ce8c-427b-be40-c9cfeaf6ab50" />




## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/Codyjackson0321/LogstashUI/issues/new).

## License

Copyright 2024–2025 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
