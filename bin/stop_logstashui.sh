#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# ========================================
# logstashui Shutdown Script
# ========================================

# Note: We don't use 'set -e' here because we want to attempt all cleanup steps
# even if some fail (e.g., containers already stopped)

# Detect docker-compose command (hyphen vs space)
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo "ERROR: Neither 'docker-compose' nor 'docker compose' found!"
    echo "Please install Docker Compose."
    exit 1
fi

echo ""
echo "========================================"
echo "LogstashUI Shutdown"
echo "========================================"
echo ""

# Change to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "Stopping native LogstashAgent if a pid file or :9501 listener exists"
if [ -f "logstashagent.pid" ]; then
    PID=$(cat logstashagent.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Killing LogstashAgent process (PID: $PID)"
        kill $PID 2>/dev/null || true
        sleep 2
        if ps -p $PID > /dev/null 2>&1; then
            kill -9 $PID 2>/dev/null || true
        fi
    fi
    rm -f logstashagent.pid
fi

PIDS=$(lsof -ti:9501 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo "Killing processes on port 9501: $PIDS"
    kill $PIDS 2>/dev/null || true
    sleep 1
    kill -9 $PIDS 2>/dev/null || true
fi

echo "Stopping Docker containers"
docker rm -f logstashui-logstashagent-1 2>/dev/null || true
cd docker
$DOCKER_COMPOSE --profile embedded down --remove-orphans
cd ..

echo ""
echo "========================================"
echo "LogstashUI Stopped Successfully"
echo "========================================"
echo ""
