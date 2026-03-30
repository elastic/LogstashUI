#!/bin/bash
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

# Check for config file (logstashui.yml first, fallback to logstashui.example.yml)
if [ -f "logstashui.yml" ]; then
    CONFIG_FILE="logstashui.yml"
elif [ -f "logstashui.example.yml" ]; then
    CONFIG_FILE="logstashui.example.yml"
else
    echo "ERROR: No config file found!"
    echo "Expected logstashui.yml or logstashui.example.yml in project root."
    exit 1
fi

# Detect mode from config file
echo "Detecting simulation mode from $CONFIG_FILE"
MODE=$(grep -m 1 "^\s*mode:" "$CONFIG_FILE" | sed 's/.*mode:\s*\([a-z]*\).*/\1/' | tr -d '[:space:]')

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
    
    # Kill Logstash process (managed by the agent)
    # Port 9600 is Logstash API, port 9449 is HTTP input
    echo "Stopping Logstash process"
    LOGSTASH_PIDS=$(lsof -ti:9600,9449 2>/dev/null || true)
    if [ -n "$LOGSTASH_PIDS" ]; then
        echo "Killing Logstash processes: $LOGSTASH_PIDS"
        kill $LOGSTASH_PIDS 2>/dev/null || true
        sleep 2
        # Force kill if still running
        if lsof -ti:9600,9449 2>/dev/null; then
            kill -9 $LOGSTASH_PIDS 2>/dev/null || true
        fi
    fi
    
    echo "LogstashAgent and Logstash stopped"
    
    echo ""
    echo "Stopping Docker containers (UI + Nginx)"
    $DOCKER_COMPOSE down --remove-orphans
    
    # Force remove agent container if it exists
    echo "Removing any stray agent containers"
    docker rm -f logstashui-logstashagent-1 2>/dev/null || true
    
else
    echo "========================================"
    echo "EMBEDDED MODE SHUTDOWN"
    echo "========================================"
    echo "Stopping all containers"
    
    # Force remove logstashagent container first (prevents stale network references)
    docker rm -f logstashui-logstashagent-1 2>/dev/null || true
    
    $DOCKER_COMPOSE down --remove-orphans
fi

echo ""
echo "========================================"
echo "LogstashUI Stopped Successfully"
echo "========================================"
echo ""
