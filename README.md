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

### 4. Navigate to the Connection Manager
<img width="939" height="475" alt="image" src="https://github.com/user-attachments/assets/7b093ee3-1148-4208-80db-e6f5722b37d3" />

### 5. Add a connection
![addconnection](https://github.com/user-attachments/assets/0ab9330d-c9fe-434d-a322-6524d1bc4098)

### 6. Start managing pipelines!
<img width="1596" height="888" alt="image" src="https://github.com/user-attachments/assets/7ac83f23-3f36-4a3f-bec1-2aa4867e1a11" />

### 7. [Optional] Add monitoring to your connections:
Use [this guide](https://www.elastic.co/docs/reference/logstash/monitoring-with-elastic-agent) to set up the Elastic Agent's Logstash integration. As long as the data is being indexed to one of your existing Elasticsearch connections, you'll see metrics and logs like this!
<img width="1570" height="876" alt="image" src="https://github.com/user-attachments/assets/01f402ca-0a88-4eb0-a8b3-b6fba15fcba5" />



## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/Codyjackson0321/LogstashUI/issues/new).

## License

Copyright 2024–2025 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
