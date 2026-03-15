#!/bin/bash
# ========================================
# LogstashUI Shutdown Script
# ========================================

set -e  # Exit on error

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

# Check if logstashui.example.yml exists
if [ ! -f "logstashui.yml" ]; then
    echo "ERROR: logstashui.yml not found!"
    echo "Please run this script from the bin directory or ensure the file exists."
    exit 1
fi

# Detect mode from logstashui.example.yml
echo "Detecting simulation mode"
MODE=$(grep -m 1 "^\s*mode:" logstashui.example.yml | sed 's/.*mode:\s*\([a-z]*\).*/\1/' | tr -d '[:space:]')

# Default to embedded if parsing fails
if [ -z "$MODE" ]; then
    MODE="embedded"
fi

echo "Detected mode: $MODE"
echo ""

if [ "$MODE" == "host" ]; then
    echo "========================================"
    echo "HOST MODE SHUTDOWN"
    echo "========================================"
    echo "Stopping native LogstashAgent process"
    
    # Kill process using PID file if it exists
    if [ -f "logstashagent.pid" ]; then
        PID=$(cat logstashagent.pid)
        if ps -p $PID > /dev/null 2>&1; then
            echo "Killing LogstashAgent process (PID: $PID)"
            kill $PID 2>/dev/null || true
            # Wait a moment for graceful shutdown
            sleep 2
            # Force kill if still running
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID 2>/dev/null || true
            fi
        fi
        rm -f logstashagent.pid
    fi
    
    # Also kill any Python processes listening on port 9501
    PIDS=$(lsof -ti:9501 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "Killing processes on port 9501: $PIDS"
        kill $PIDS 2>/dev/null || true
        sleep 1
        # Force kill if still running
        kill -9 $PIDS 2>/dev/null || true
    fi
    
    echo "LogstashAgent stopped"
    
    echo ""
    echo "Stopping Docker containers (UI + Nginx)"
    $DOCKER_COMPOSE down
    
    # Force remove agent container if it exists
    echo "Removing any stray agent containers"
    docker rm -f logstashui-logstashagent-1 2>/dev/null || true
    
else
    echo "========================================"
    echo "EMBEDDED MODE SHUTDOWN"
    echo "========================================"
    echo "Stopping all containers"
    $DOCKER_COMPOSE down
fi

echo ""
echo "========================================"
echo "LogstashUI Stopped Successfully"
echo "========================================"
echo ""
