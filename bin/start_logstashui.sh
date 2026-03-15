#!/bin/bash
# LogstashUI Startup Script
# Detects mode from logstashui.example.yml and starts accordingly
# - Host mode: Starts native Python agent on Linux, then containers (without agent container)
# - Embedded mode: Starts all containers including agent
#
# Usage:
#   ./start_logstashui.sh          - Start with existing images
#   ./start_logstashui.sh --rebuild - Rebuild images before starting
#   ./start_logstashui.sh --update  - Pull latest code and images, then start

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

echo "Using Docker Compose command: $DOCKER_COMPOSE"
echo ""

# Parse command line arguments
REBUILD_FLAG=""
UPDATE_MODE=0
if [ "$1" == "--rebuild" ]; then
    REBUILD_FLAG="--build"
fi
if [ "$1" == "--update" ]; then
    UPDATE_MODE=1
fi

echo "========================================"
echo "LogstashUI Startup"
echo "========================================"
echo ""
# Handle update mode
if [ $UPDATE_MODE -eq 1 ]; then
    echo "========================================"
    echo "UPDATE MODE"
    echo "========================================"
    echo "Pulling latest code from git..."
    echo ""
    
    git pull
    if [ $? -ne 0 ]; then
        echo "WARNING: Git pull failed. Continuing with existing code..."
        echo ""
    else
        echo "Git pull successful!"
        echo ""
    fi
    
    echo "Stopping containers..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    "$SCRIPT_DIR/stop_logstashui.sh" >/dev/null 2>&1 || true
    
    echo ""
    echo "Pulling latest Docker images..."
    $DOCKER_COMPOSE pull
    if [ $? -ne 0 ]; then
        echo "WARNING: Failed to pull some images. Continuing..."
        echo ""
    else
        echo "Images pulled successfully!"
        echo ""
    fi
else
    echo "Ensuring clean state - stopping any existing services..."
    echo ""
    
    # Call stop script first to ensure clean state
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    "$SCRIPT_DIR/stop_logstashui.sh" || true
fi

echo ""
echo "========================================"
echo "Starting LogstashUI"
echo "========================================"
echo ""

# Change to the repository root directory (parent of bin)
cd "$SCRIPT_DIR/.."

# Debug: Show current directory
echo "Current directory: $(pwd)"
echo ""

# Ensure logstashui.yml exists (required for Docker volume mount)
# If it doesn't exist, create a symlink to logstashui.example.yml
if [ ! -f "logstashui.yml" ]; then
    if [ -f "logstashui.example.yml" ]; then
        echo "Creating logstashui.yml symlink to logstashui.example.yml"
        ln -s logstashui.example.yml logstashui.yml
    else
        echo "ERROR: logstashui.example.yml not found!"
        echo "Current directory: $(pwd)"
        exit 1
    fi
fi

# Check for config file (logstashui.yml first, fallback to logstashui.example.yml)
if [ -f "logstashui.yml" ]; then
    CONFIG_FILE="logstashui.yml"
elif [ -f "logstashui.example.yml" ]; then
    CONFIG_FILE="logstashui.example.yml"
else
    echo "ERROR: No config file found!"
    echo "Expected logstashui.yml or logstashui.example.yml in project root."
    echo "Current directory: $(pwd)"
    echo ""
    echo "Directory contents:"
    ls -la
    exit 1
fi

echo "Using config file: $CONFIG_FILE"
echo ""

# Parse the simulation mode from config file (under simulation.mode)
MODE=$(grep -m 1 "^\s*mode:" "$CONFIG_FILE" | sed 's/.*mode:\s*\([a-z]*\).*/\1/' | tr -d '[:space:]')

# Default to embedded if parsing fails
if [ -z "$MODE" ]; then
    MODE="embedded"
fi

echo "Detected mode: $MODE"
echo ""

if [ "$MODE" == "host" ]; then
    echo "========================================"
    echo "HOST MODE DETECTED"
    echo "========================================"
    echo "Starting LogstashAgent natively on Linux"
    echo "This allows the agent to control your host Logstash instance."
    echo ""
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        echo "ERROR: Python3 not found in PATH!"
        echo "Please install Python 3.9+ and ensure it's in your PATH."
        exit 1
    fi
    
    # Setup virtual environment for LogstashAgent
    if [ ! -d "LogstashAgent/.venv" ]; then
        echo "Creating virtual environment in LogstashAgent/.venv"
        python3 -m venv LogstashAgent/.venv
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to create virtual environment!"
            echo "Please ensure python3-venv is installed (apt-get install python3-venv)"
            exit 1
        fi
    fi
    
    echo "Activating virtual environment"
    source LogstashAgent/.venv/bin/activate
    
    # Install/update Python dependencies for LogstashAgent
    echo "Installing Python dependencies for LogstashAgent"
    pip install -r LogstashAgent/requirements.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install dependencies!"
        echo "Please check that Python and pip are working correctly."
        deactivate
        exit 1
    fi
    echo "Dependencies installed successfully"
    
    echo ""
    echo "Preparing LogstashAgent configuration"
    # Copy logstash_agent config from logstashui.example.yml to LogstashAgent/logstashagent.yml
    python3 bin/sync_config.py
    if [ $? -ne 0 ]; then
        echo "WARNING: Could not update agent config automatically"
        echo "Please ensure LogstashAgent/logstashagent.yml has correct paths"
    fi
    
    echo "Starting LogstashAgent on port 9501 (localhost only)"
    cd LogstashAgent
    # Start in background using nohup - bind to 127.0.0.1 for security
    # Run uvicorn in the activated virtual environment context
    nohup .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 9501 > ../logstashagent.log 2>&1 &
    AGENT_PID=$!
    echo $AGENT_PID > ../logstashagent.pid
    cd ..
    
    # Deactivate virtual environment (agent is running in background)
    deactivate
    
    echo "LogstashAgent started with PID: $AGENT_PID"
    echo "Waiting 5 seconds for agent to initialize"
    sleep 5
    
    echo ""
    echo "========================================"
    echo "Starting Docker containers (UI + Nginx only)"
    echo "========================================"
    echo "Note: LogstashAgent container will NOT start (running natively instead)"
    echo "Note: Native agent runs on port 9501, nginx proxies from 9500 to 9501"
    echo ""
    
    # Ensure agent container is stopped in host mode
    echo "Stopping any existing containers"
    $DOCKER_COMPOSE stop logstashagent 2>/dev/null || true
    $DOCKER_COMPOSE rm -f logstashagent 2>/dev/null || true
    
    # Start only logstashui and nginx in detached mode
    # Nginx will detect host mode and proxy to host.docker.internal:9501
    if [ -n "$REBUILD_FLAG" ]; then
        $DOCKER_COMPOSE up -d $REBUILD_FLAG logstashui nginx
    else
        $DOCKER_COMPOSE up -d logstashui nginx
    fi
    
else
    echo "========================================"
    echo "EMBEDDED MODE DETECTED"
    echo "========================================"
    echo "Starting all containers including embedded LogstashAgent"
    echo "Logstash will run inside the agent container."
    echo ""
    
    # Force remove any existing logstashagent container to prevent stale network references
    docker rm -f logstashui-logstashagent-1 2>/dev/null || true
    
    # Start all containers in detached mode with embedded profile
    # Retry once if network failure occurs
    if [ -n "$REBUILD_FLAG" ]; then
        $DOCKER_COMPOSE --profile embedded up -d $REBUILD_FLAG || {
            echo "Startup failed, cleaning up and retrying..."
            docker rm -f logstashui-logstashagent-1 2>/dev/null || true
            $DOCKER_COMPOSE down --remove-orphans
            sleep 1
            $DOCKER_COMPOSE --profile embedded up -d $REBUILD_FLAG
        }
    else
        $DOCKER_COMPOSE --profile embedded up -d || {
            echo "Startup failed, cleaning up and retrying..."
            docker rm -f logstashui-logstashagent-1 2>/dev/null || true
            $DOCKER_COMPOSE down --remove-orphans
            sleep 1
            $DOCKER_COMPOSE --profile embedded up -d
        }
    fi
fi

echo ""
echo "========================================"
echo "LogstashUI Started Successfully"
echo "========================================"
echo ""
echo "Containers are running in the background."
echo "To stop LogstashUI, run: ./stop_logstashui.sh"
echo ""
echo "Access LogstashUI at: https://your_ip_or_hostname_here"
echo ""
