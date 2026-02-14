#!/bin/bash
set -e

echo "=========================================="
echo "  Starting LogstashAgent (StashPilot)"
echo "=========================================="

# Start Logstash in the background
echo "Starting Logstash with pipelines.yml..."
/usr/share/logstash/bin/logstash --path.settings /etc/logstash &
LOGSTASH_PID=$!

# Wait a moment for Logstash to initialize
sleep 5

# Start FastAPI sidecar
echo "Starting FastAPI sidecar on port 9500..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port 9500 &
FASTAPI_PID=$!

echo "=========================================="
echo "  LogstashAgent is ready!"
echo "  - Logstash API: http://localhost:9600"
echo "  - Logstash HTTP Input: http://localhost:9449"
echo "  - Simulation HTTP Input: http://localhost:8082"
echo "  - FastAPI Sidecar: http://localhost:9500"
echo "=========================================="

# Wait for both processes
wait $LOGSTASH_PID $FASTAPI_PID
