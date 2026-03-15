#!/bin/bash
set -e

echo "=========================================="
echo "  Starting LogstashAgent"
echo "=========================================="

# LOGSTASH_URL is set via Dockerfile ENV (default: http://127.0.0.1:8080)
# Can be overridden via docker-compose or docker run -e
# Logstash will use ${LOGSTASH_URL:default} syntax in config files for environment variable substitution
echo "LOGSTASH_URL: $LOGSTASH_URL"

# Ensure log directory exists and has proper permissions
echo "Setting up log directory..."
mkdir -p /var/log/logstash
chmod 755 /var/log/logstash

# Verify log4j2.properties exists
if [ -f /etc/logstash/log4j2.properties ]; then
    echo "+ log4j2.properties found at /etc/logstash/log4j2.properties"
else
    echo "- WARNING: log4j2.properties not found!"
fi

# LogstashAgent will start and supervise Logstash via Python
echo "Starting FastAPI sidecar (which will supervise Logstash)..."
echo "=========================================="
echo "  LogstashAgent starting..."
echo "  - Logstash will be supervised by FastAPI"
echo "  - Logstash API: http://localhost:9600"
echo "  - Simulation HTTP Input: http://localhost:9449"
echo "  - FastAPI Sidecar: http://localhost:9500"
echo "=========================================="

cd /app
exec uvicorn main:app --host 127.0.0.1 --port 9500
