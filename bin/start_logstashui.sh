#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# logstashui Startup Script
# Default: Docker Compose --profile embedded (UI + embedded agent).
# --legacy-host-agent: native agent on :9501 + UI only — not enrolled simulate@N
# Preferred multi-instance sim: enroll a Simulate policy (see host_mode.md)
#
# Usage:
#   ./start_logstashui.sh                    Start with existing images
#   ./start_logstashui.sh --rebuild          Rebuild images from this tree
#   ./start_logstashui.sh --update           Pull latest code and images, then start
#   ./start_logstashui.sh --legacy-host-agent  Legacy local FastAPI agent on :9501

set -e  # Exit on error

# Check for required dependencies
check_dependencies() {
    local missing_deps=()

    # Check for Docker
    if ! command -v docker &> /dev/null; then
        missing_deps+=("docker")
    fi

    # Check for Git
    if ! command -v git &> /dev/null; then
        missing_deps+=("git")
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo "ERROR: Missing required dependencies: ${missing_deps[*]}"
        echo ""
        echo "Please install the following:"
        for dep in "${missing_deps[@]}"; do
            if [ "$dep" == "docker" ]; then
                echo "  - Docker: https://docs.docker.com/engine/install/"
                echo "    (For Debian/Ubuntu: apt-get install docker.io)"
                echo "    (For RHEL/CentOS: yum install docker)"
            elif [ "$dep" == "git" ]; then
                echo "  - Git: apt-get install git | yum install git"
            fi
        done
        exit 1
    fi
}

# Run dependency check
check_dependencies

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

# ---------------------------------------------------------------------------
# Host identity for product UI TLS SANs (containers cannot see Docker host IPs)
# ---------------------------------------------------------------------------
# Iterate a comma-separated list without IFS word-splitting (safe + portable).
# Callback receives one trimmed token per call.
foreach_csv() {
    local csv="$1"
    local fn="$2"
    local token
    while IFS= read -r token; do
        # trim whitespace
        token="${token#"${token%%[![:space:]]*}"}"
        token="${token%"${token##*[![:space:]]}"}"
        [ -n "$token" ] || continue
        "$fn" "$token"
    done <<EOF
$(printf '%s' "$csv" | tr ',' '\n')
EOF
}

# Best-effort PTR for one IP → FQDN (strip trailing dot). Empty if none / NXDOMAIN.
# Prefer dig, then host(1), then python3 — works on Linux + macOS.
reverse_lookup_ip() {
    local ip="$1"
    local name=""
    [ -n "$ip" ] || return 0

    if command -v dig >/dev/null 2>&1; then
        name=$(dig +short -x "$ip" 2>/dev/null | head -1 | sed 's/\.$//')
    fi
    if [ -z "$name" ] && command -v host >/dev/null 2>&1; then
        name=$(host "$ip" 2>/dev/null | awk '/pointer/ {print $NF; exit}' | sed 's/\.$//')
    fi
    if [ -z "$name" ] && command -v python3 >/dev/null 2>&1; then
        # Quote IP via env to avoid shell injection into python -c
        name=$(
            IP_ADDR="$ip" python3 -c "
import os, socket
socket.setdefaulttimeout(1.0)
try:
    print(socket.gethostbyaddr(os.environ['IP_ADDR'])[0].rstrip('.'))
except Exception:
    pass
" 2>/dev/null || true
        )
    fi

    # Keep only multi-label names (real FQDNs), not the IP echoed back or short labels
    if [ -n "$name" ] && [ "$name" != "$ip" ] && [[ "$name" == *.* ]]; then
        printf '%s' "$name"
    fi
}

# Append unique comma-separated token (case-insensitive dedupe for hostnames)
append_unique_csv() {
    local list="$1"
    local token="$2"
    local t lower_token lower_t
    [ -n "$token" ] || { printf '%s' "$list"; return 0; }
    if [ -z "$list" ]; then
        printf '%s' "$token"
        return 0
    fi
    lower_token=$(printf '%s' "$token" | tr '[:upper:]' '[:lower:]')
    while IFS= read -r t; do
        [ -n "$t" ] || continue
        lower_t=$(printf '%s' "$t" | tr '[:upper:]' '[:lower:]')
        if [ "$lower_t" = "$lower_token" ]; then
            printf '%s' "$list"
            return 0
        fi
    done <<EOF
$(printf '%s' "$list" | tr ',' '\n')
EOF
    printf '%s,%s' "$list" "$token"
}

collect_host_tls_env() {
    # Bare hostname from the OS (often short on macOS — prefer PTR FQDNs below)
    local hn
    hn=$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo "")

    # Collect non-loopback IPv4 addresses from the host
    local ips=""
    if command -v ip >/dev/null 2>&1; then
        ips=$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | tr '\n' ',' | sed 's/,$//')
    fi
    if [ -z "$ips" ] && command -v ifconfig >/dev/null 2>&1; then
        # macOS / BSD ifconfig
        ips=$(ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" {print $2}' | tr '\n' ',' | sed 's/,$//')
    fi
    # Optional: IPv6 global (skip link-local fe80:)
    local ips6=""
    if command -v ip >/dev/null 2>&1; then
        ips6=$(ip -6 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -v '^fe80' | tr '\n' ',' | sed 's/,$//')
    fi
    if [ -n "$ips6" ]; then
        if [ -n "$ips" ]; then
            ips="${ips},${ips6}"
        else
            ips="$ips6"
        fi
    fi
    export LOGSTASHUI_HOST_IPS="${LOGSTASHUI_HOST_IPS:-$ips}"

    # Reverse-lookup each host IP for FQDNs (PTR). Prefer those over bare hostname.
    local fqdns=""
    local first_fqdn=""
    _tls_ptr_one() {
        local ip="$1" name
        name=$(reverse_lookup_ip "$ip")
        [ -n "$name" ] || return 0
        fqdns=$(append_unique_csv "$fqdns" "$name")
        if [ -z "$first_fqdn" ]; then
            first_fqdn="$name"
        fi
    }
    if [ -n "${LOGSTASHUI_HOST_IPS:-}" ]; then
        foreach_csv "$LOGSTASHUI_HOST_IPS" _tls_ptr_one
    fi

    # HOST_HOSTNAME: operator override > first PTR FQDN > OS hostname
    if [ -z "${LOGSTASHUI_HOST_HOSTNAME:-}" ]; then
        if [ -n "$first_fqdn" ]; then
            export LOGSTASHUI_HOST_HOSTNAME="$first_fqdn"
        else
            export LOGSTASHUI_HOST_HOSTNAME="$hn"
        fi
    fi

    # Merge into TLS_SANS if operator did not set it:
    # all PTR FQDNs (or bare hostname if none), plus host IPs
    if [ -z "${LOGSTASHUI_TLS_SANS:-}" ]; then
        local merged=""
        if [ -n "$fqdns" ]; then
            merged="$fqdns"
        elif [ -n "$LOGSTASHUI_HOST_HOSTNAME" ]; then
            # No PTR results — fall back to hostname (may be short)
            merged="$LOGSTASHUI_HOST_HOSTNAME"
        fi
        if [ -n "$LOGSTASHUI_HOST_IPS" ]; then
            if [ -n "$merged" ]; then
                merged="${merged},${LOGSTASHUI_HOST_IPS}"
            else
                merged="$LOGSTASHUI_HOST_IPS"
            fi
        fi
        export LOGSTASHUI_TLS_SANS="$merged"
    fi

    # Expand CSRF trusted origins for each host name + IP (browsers hit https://…:8443)
    # Rebuild from a clean base so a prior broken CSRF_TRUSTED_ORIGINS cannot leak in.
    local origins="https://localhost:8443,https://127.0.0.1:8443"
    if [ -n "${CSRF_TRUSTED_ORIGINS:-}" ]; then
        # Keep only already-valid https?://… entries from the operator env
        _tls_keep_origin() {
            local o="$1"
            case "$o" in
                https://*|http://*) origins=$(append_unique_csv "$origins" "$o") ;;
            esac
        }
        foreach_csv "$CSRF_TRUSTED_ORIGINS" _tls_keep_origin
    fi
    _tls_add_origin_host() {
        local h="$1"
        [ -n "$h" ] || return 0
        origins=$(append_unique_csv "$origins" "https://${h}:8443")
    }
    if [ -n "$fqdns" ]; then
        foreach_csv "$fqdns" _tls_add_origin_host
    elif [ -n "$LOGSTASHUI_HOST_HOSTNAME" ]; then
        _tls_add_origin_host "$LOGSTASHUI_HOST_HOSTNAME"
    fi
    if [ -n "$LOGSTASHUI_HOST_IPS" ]; then
        foreach_csv "$LOGSTASHUI_HOST_IPS" _tls_add_origin_host
    fi
    export CSRF_TRUSTED_ORIGINS="$origins"

    echo "Host TLS SAN injection for UI product cert:"
    echo "  LOGSTASHUI_HOST_HOSTNAME=$LOGSTASHUI_HOST_HOSTNAME"
    echo "  LOGSTASHUI_HOST_IPS=$LOGSTASHUI_HOST_IPS"
    echo "  LOGSTASHUI_TLS_SANS=$LOGSTASHUI_TLS_SANS"
    if [ -n "$fqdns" ]; then
        echo "  reverse-DNS FQDNs=$fqdns"
    else
        echo "  reverse-DNS FQDNs=(none — using hostname fallback)"
    fi
    echo ""
}
collect_host_tls_env

# Parse command line arguments
REBUILD_FLAG=""
UPDATE_MODE=0
LEGACY_HOST_AGENT=0
# --rebuild builds from local source (docker-compose.smoke.yml). Plain `up`
# without --rebuild uses Hub images (codyjackson032/*) and does NOT pick up
# uncommitted local TLS/callback changes.
for arg in "$@"; do
    case "$arg" in
        --rebuild) REBUILD_FLAG="--build" ;;
        --update) UPDATE_MODE=1 ;;
        --legacy-host-agent) LEGACY_HOST_AGENT=1 ;;
    esac
done

# Compose file set: smoke override tags local images and enables `build:`.
# Used whenever REBUILD_FLAG is set so --rebuild actually compiles this tree.
compose_cmd() {
    # Usage: compose_cmd [docker compose args...]
    # Always run from $PROJECT_ROOT/docker (caller must cd there).
    if [ -n "$REBUILD_FLAG" ] && [ -f "docker-compose.smoke.yml" ]; then
        $DOCKER_COMPOSE -f docker-compose.yml -f docker-compose.smoke.yml "$@"
    else
        $DOCKER_COMPOSE "$@"
    fi
}

echo "========================================"
echo "LogstashUI Startup"
echo "========================================"
echo ""
# Handle update mode
if [ $UPDATE_MODE -eq 1 ]; then
    echo "========================================"
    echo "UPDATE MODE"
    echo "========================================"
    echo "Switching to main branch..."
    echo ""

    git checkout main
    if [ $? -ne 0 ]; then
        echo "WARNING: Failed to switch to main branch. Continuing anyway..."
        echo ""
    else
        echo "Switched to main branch successfully!"
        echo ""
    fi

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

# Store absolute path to project root
PROJECT_ROOT="$(pwd)"

# Debug: Show current directory
echo "Current directory: $PROJECT_ROOT"
echo ""

# Bind-mount target: <checkout>/logstashui_data → /var/lib/logstashui
ensure_host_data_dir() {
    local dest="$PROJECT_ROOT/logstashui_data"
    mkdir -p "$dest"
    if [ ! -f "$dest/db.sqlite3" ] && [ -f "$PROJECT_ROOT/src/logstashui/data/db.sqlite3" ]; then
        echo "Migrating src/logstashui/data → logstashui_data/"
        cp -a "$PROJECT_ROOT/src/logstashui/data/." "$dest/"
    fi
    if [ ! -f "$dest/db.sqlite3" ]; then
        local vol
        for vol in logstashui_logstashui_data logstashui_data LogstashUI_logstashui_data; do
            if docker volume inspect "$vol" >/dev/null 2>&1; then
                echo "Copying Docker volume $vol → logstashui_data/"
                docker run --rm \
                    -v "$vol":/from \
                    -v "$dest":/to \
                    alpine:3.20 sh -c 'cp -a /from/. /to/' || true
                break
            fi
        done
    fi
    echo "Host data directory: $dest"
    echo ""
}
ensure_host_data_dir

# Linux Docker bind-mounts keep host UIDs; pass ours so the container can write
# ./logstashui_data without chowning it to the image's appuser (10001).
export PUID="${PUID:-$(id -u)}"
export PGID="${PGID:-$(id -g)}"
echo "Bind-mount owner: PUID=$PUID PGID=$PGID"
echo ""

if [ "$LEGACY_HOST_AGENT" -eq 1 ]; then
    MODE="host"
else
    MODE="embedded"
fi

echo "Start path: $MODE"
echo ""

if [ "$MODE" == "host" ]; then
    echo "========================================"
    echo "LEGACY HOST MODE DETECTED"
    echo "========================================"
    echo "Starting a native LogstashAgent (FastAPI + supervisor) on Linux."
    echo ""
    echo "NOTE: This is a LEGACY local sim path (--legacy-host-agent)."
    echo "It is NOT an enrolled mode:simulate / lsagent-simulate@N instance."
    echo "Prefer enrolling a Simulate policy agent for multi-instance sim:"
    echo "  sudo logstash-agent install --enroll <TOKEN> --logstash-ui-url <URL>"
    echo "  sudo systemctl enable --now lsagent-simulate@N"
    echo ""

    # Check if uv is available
    if ! command -v uv &> /dev/null; then
        echo "ERROR: uv not found in PATH!"
        echo "Please install uv from: https://docs.astral.sh/uv/getting-started/installation/"
        echo ""
        echo "Quick install: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    # Clone LogstashAgent if it doesn't exist
    if [ ! -d "$PROJECT_ROOT/LogstashAgent" ]; then
        echo "LogstashAgent directory not found, cloning from GitHub..."
        echo ""
        cd "$PROJECT_ROOT"
        git clone https://github.com/elastic/LogstashAgent.git
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to clone LogstashAgent repository!"
            echo "Please check your internet connection and Git installation."
            exit 1
        fi
        echo "LogstashAgent cloned successfully!"
        echo ""
    else
        echo "LogstashAgent directory found."
        echo ""
    fi

    echo ""
    echo "Preparing LogstashAgent configuration"
    # Copy legacy agent config into LogstashAgent/src/logstashagent/logstashagent.yml
    cd "$PROJECT_ROOT"
    python3 bin/sync_config.py
    if [ $? -ne 0 ]; then
        echo "WARNING: Could not update agent config automatically"
        echo "Please ensure LogstashAgent/src/logstashagent/logstashagent.yml has correct paths"
    fi

    # Install/update Python dependencies for logstashagent using uv
    echo "Installing Python dependencies for LogstashAgent with uv"
    cd "$PROJECT_ROOT/LogstashAgent"
    uv sync
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install dependencies with uv!"
        echo "Please check that uv is working correctly."
        exit 1
    fi
    echo "Dependencies installed successfully"

    echo ""
    echo "Setting Logstash directory ownership for logstash user"
    LOGSTASH_HOME="${LOGSTASH_HOME:-/usr/share/logstash}"
    echo "Logstash home: $LOGSTASH_HOME"

    # Ensure logstash user owns the data directory
    if [ -d "$LOGSTASH_HOME/data" ]; then
        sudo chown -R logstash:logstash "$LOGSTASH_HOME/data"
        echo "Set ownership of $LOGSTASH_HOME/data to logstash:logstash"
    else
        echo "WARNING: $LOGSTASH_HOME/data not found, skipping chown"
    fi

    # Ensure logstash user owns the log directory
    LOGSTASH_LOG_PATH="${LOGSTASH_LOG_PATH:-/var/log/logstash}"
    echo "Logstash log path: $LOGSTASH_LOG_PATH"

    if [ -d "$LOGSTASH_LOG_PATH" ]; then
        sudo chown -R logstash:logstash "$LOGSTASH_LOG_PATH"
        echo "Set ownership of $LOGSTASH_LOG_PATH to logstash:logstash"
    else
        echo "WARNING: $LOGSTASH_LOG_PATH not found, creating it"
        sudo mkdir -p "$LOGSTASH_LOG_PATH"
        sudo chown -R logstash:logstash "$LOGSTASH_LOG_PATH"
        echo "Created and set ownership of $LOGSTASH_LOG_PATH to logstash:logstash"
    fi
    echo ""

    echo "========================================"
    echo "Starting Docker UI first (HTTPS :8443), then legacy native agent"
    echo "========================================"
    echo "Note: LogstashAgent container will NOT start (legacy native agent instead)"
    echo "Note: Native agent HTTPS on port 9501; UI uses LOGSTASH_AGENT_URL=https://host.docker.internal:9501"
    echo ""

    # Ensure agent container is stopped for legacy host path
    echo "Stopping any existing containers"
    cd "$PROJECT_ROOT/docker"
    $DOCKER_COMPOSE stop logstashagent 2>/dev/null || true
    $DOCKER_COMPOSE rm -f logstashagent 2>/dev/null || true

    export LOGSTASH_AGENT_URL="${LOGSTASH_AGENT_URL:-https://host.docker.internal:9501}"
    export LOGSTASHUI_AGENT_CSR_SECRET="${LOGSTASHUI_AGENT_CSR_SECRET:-logstashui-compose-dev}"
    if [ -n "$REBUILD_FLAG" ]; then
        echo "Rebuilding UI image from local source (docker-compose.smoke.yml)..."
        compose_cmd up -d $REBUILD_FLAG logstashui
    else
        compose_cmd up -d logstashui
    fi
    cd "$PROJECT_ROOT"

    echo "Waiting 8 seconds for UI TLS material..."
    sleep 8

    echo "Starting LogstashAgent on port 9501 (HTTPS when cert issued)"
    cd "$PROJECT_ROOT/LogstashAgent"
    export LOGSTASH_UI_URL="${LOGSTASH_UI_URL:-https://localhost:8443}"
    export LOGSTASHUI_AGENT_CSR_SECRET="${LOGSTASHUI_AGENT_CSR_SECRET:-logstashui-compose-dev}"
    # Host-mode legacy uses 9501 so it does not clash with container 9500
    nohup env LOGSTASH_UI_URL="$LOGSTASH_UI_URL" \
        LOGSTASHUI_AGENT_CSR_SECRET="$LOGSTASHUI_AGENT_CSR_SECRET" \
        LOGSTASH_AGENT_PORT=9501 \
        uv run python -m logstashagent.main --mode embedded \
        > "$PROJECT_ROOT/logstashagent.log" 2>&1 &
    AGENT_PID=$!
    echo $AGENT_PID > "$PROJECT_ROOT/logstashagent.pid"
    cd "$PROJECT_ROOT"
    echo "LogstashAgent started with PID: $AGENT_PID"

else
    echo "========================================"
    echo "EMBEDDED MODE DETECTED"
    echo "========================================"
    echo "Starting all containers including embedded LogstashAgent"
    echo "Logstash will run inside the agent container."
    echo ""

    # Force remove any existing logstashagent container to prevent stale network references
    docker rm -f logstashui-logstashagent-1 2>/dev/null || true

    # Change to docker directory for docker-compose commands
    cd "$PROJECT_ROOT/docker"

    if [ -n "$REBUILD_FLAG" ]; then
        echo "Rebuilding UI + embedded agent from local source (docker-compose.smoke.yml)..."
        echo "  (plain 'docker compose --build' without smoke.yml still uses Hub images)"
    fi

    # Start all containers in detached mode with embedded profile
    # Retry once if network failure occurs
    if [ -n "$REBUILD_FLAG" ]; then
        compose_cmd --profile embedded up -d $REBUILD_FLAG || {
            echo "Startup failed, cleaning up and retrying..."
            docker rm -f logstashui-logstashagent-1 2>/dev/null || true
            compose_cmd down --remove-orphans
            sleep 1
            compose_cmd --profile embedded up -d $REBUILD_FLAG
        }
    else
        compose_cmd --profile embedded up -d || {
            echo "Startup failed, cleaning up and retrying..."
            docker rm -f logstashui-logstashagent-1 2>/dev/null || true
            compose_cmd down --remove-orphans
            sleep 1
            compose_cmd --profile embedded up -d
        }
    fi
    cd "$PROJECT_ROOT"
fi

echo ""
echo "========================================"
echo "LogstashUI Started Successfully"
echo "========================================"
echo ""
echo "Containers are running in the background."
echo "To stop LogstashUI, run: ./stop_logstashui.sh"
echo ""
echo "Access LogstashUI at: https://your_ip_or_hostname_here:8443"
echo "(Product CA by default — browsers will warn until you trust it or upload a public cert in Settings.)"
echo ""
