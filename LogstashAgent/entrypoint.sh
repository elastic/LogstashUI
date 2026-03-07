#!/bin/bash
set -e

echo "=========================================="
echo "  Starting LogstashAgent"
echo "=========================================="

# LOGSTASH_URL is set via Dockerfile ENV (default: http://127.0.0.1:8080)
# Can be overridden via docker-compose or docker run -e
echo "Using LOGSTASH_URL: $LOGSTASH_URL"

# Update simulate_end.conf with the correct URL
echo "Updating simulate_end.conf with LOGSTASH_URL..."
sed -i "s|url => \"\${LOGSTASH_URL:http://nginx:8080}/ConnectionManager/StreamSimulate/\"|url => \"${LOGSTASH_URL}/ConnectionManager/StreamSimulate/\"|g" /etc/logstash/config/simulate_end.conf
sed -i "s|url => \"\${LOGSTASH_URL:http://nginx:8080}/ConnectionManager/StreamSimulate/\"|url => \"${LOGSTASH_URL}/ConnectionManager/StreamSimulate/\"|g" /etc/logstash/config/simulate_start.conf

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

# Start Logstash in the background with explicit log4j2 config
echo "Starting Logstash with pipelines.yml and custom logging..."
export LS_JAVA_OPTS="-Dlog4j.configurationFile=/etc/logstash/log4j2.properties"
# Ensure LOGSTASH_URL is available to Logstash process
env LOGSTASH_URL="$LOGSTASH_URL" /usr/share/logstash/bin/logstash --path.settings /etc/logstash &
LOGSTASH_PID=$!

# Wait a moment for Logstash to initialize
sleep 5

# Start FastAPI sidecar
echo "Starting FastAPI sidecar on port 9500..."
cd /app
uvicorn main:app --host 0.0.0.0 --port 9500 &
FASTAPI_PID=$!

echo "=========================================="
echo "  LogstashAgent is ready!"
echo "  - Logstash API: http://localhost:9600"
echo "  - Simulation HTTP Input: http://localhost:9449"
echo "  - FastAPI Sidecar: http://localhost:9500"
echo "=========================================="

# Wait for both processes
wait $LOGSTASH_PID $FASTAPI_PID
