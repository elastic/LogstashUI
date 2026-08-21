#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

set -e

# Change to Django project directory
cd /app/src/logstashui

DATA_DIR="${LOGSTASHUI_DATA_DIR:-/var/lib/logstashui}"

_data_dir_not_writable_msg() {
    echo "ERROR: $DATA_DIR is not writable by uid $(id -u) gid $(id -g)."
    echo "Linux Docker bind-mounts keep host ownership; the UI cannot create sqlite/TLS."
    echo "Fix: run bin/start_logstashui.sh (sets PUID/PGID to your uid), or"
    echo "  export PUID=\$(id -u) PGID=\$(id -g)"
    echo "or chown the host directory, or use a named volume."
}

# Root: make DATA_DIR writable for appuser (or PUID/PGID), then drop privileges.
# Non-root (K8s runAsNonRoot + fsGroup): skip chown; fail fast if still unwritable.
# Ownership changes only — never delete or rewrite tls/product-ca.crt.
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR" "$DATA_DIR/tls" "$DATA_DIR/logs"
    if [ -n "${PUID:-}" ]; then
        TARGET_UID="$PUID"
    else
        TARGET_UID="$(id -u appuser)"
    fi
    if [ -n "${PGID:-}" ]; then
        TARGET_GID="$PGID"
    else
        TARGET_GID="$(id -g appuser)"
    fi
    if ! setpriv --reuid="$TARGET_UID" --regid="$TARGET_GID" --clear-groups -- test -w "$DATA_DIR"; then
        echo "DATA_DIR $DATA_DIR not writable by uid $TARGET_UID — chowning bind-mount"
        chown -R "$TARGET_UID:$TARGET_GID" "$DATA_DIR"
    fi
    if ! setpriv --reuid="$TARGET_UID" --regid="$TARGET_GID" --clear-groups -- test -w "$DATA_DIR"; then
        _data_dir_not_writable_msg
        exit 1
    fi
    echo "Dropping privileges to uid $TARGET_UID gid $TARGET_GID"
    exec setpriv --reuid="$TARGET_UID" --regid="$TARGET_GID" --clear-groups --inh-caps=-all -- "$0" "$@"
fi

mkdir -p "$DATA_DIR" "$DATA_DIR/tls" "$DATA_DIR/logs"
if [ ! -w "$DATA_DIR" ]; then
    _data_dir_not_writable_msg
    exit 1
fi

# Diagnostic: Check data directory permissions and contents
echo "=========================================="
echo "Database Directory Diagnostics"
echo "=========================================="
echo "LOGSTASHUI_DATA_DIR=$DATA_DIR"
echo "Directory permissions:"
ls -lah "$DATA_DIR" | head
echo ""
echo "User ID: $(id)"
echo ""

# Check if database file exists and is readable
if [ -f "$DATA_DIR/db.sqlite3" ]; then
    echo "Database file exists ($(stat -c%s "$DATA_DIR/db.sqlite3") bytes)"
    if [ -r "$DATA_DIR/db.sqlite3" ]; then
        echo "Database file is readable"
    else
        echo "WARNING: Database file exists but is NOT readable!"
    fi
    if [ -w "$DATA_DIR/db.sqlite3" ]; then
        echo "Database file is writable"
    else
        echo "WARNING: Database file exists but is NOT writable!"
    fi
    
    # Check if migrations table exists
    echo ""
    echo "Checking for existing migrations table..."
    if sqlite3 "$DATA_DIR/db.sqlite3" "SELECT COUNT(*) FROM django_migrations;" 2>/dev/null; then
        MIGRATION_COUNT=$(sqlite3 "$DATA_DIR/db.sqlite3" "SELECT COUNT(*) FROM django_migrations;" 2>/dev/null)
        echo "Found django_migrations table with $MIGRATION_COUNT entries"
    else
        echo "No django_migrations table found (fresh database)"
    fi
else
    echo "Database file does not exist - will be created"
fi
echo "=========================================="
echo ""

# Show what migrations Django thinks need to be applied
echo "Checking migration status..."
python manage.py showmigrations
echo ""

# Run migrations
python manage.py migrate --noinput

# Sync SNMP official profiles and device templates
echo ""
echo "Syncing SNMP official data..."
python manage.py sync_snmp_official_data --cleanup || echo "Warning: SNMP sync encountered an error but continuing startup"
echo ""

# Product CA + UI server cert (DATA_DIR/tls/; SANs from host hostname/IPs via env + callback URL)
echo "Ensuring product CA and UI server certificate..."
echo "  LOGSTASHUI_DATA_DIR=${LOGSTASHUI_DATA_DIR:-}"
echo "  LOGSTASHUI_HOST_HOSTNAME=${LOGSTASHUI_HOST_HOSTNAME:-}"
echo "  LOGSTASHUI_HOST_IPS=${LOGSTASHUI_HOST_IPS:-}"
echo "  LOGSTASHUI_TLS_SANS=${LOGSTASHUI_TLS_SANS:-}"
python - <<'PY'
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from Common.product_ca import (
    collect_desired_ui_sans,
    ensure_default_ui_server_cert,
    get_ca_fingerprint,
    get_ui_tls_status,
    ui_server_cert_path,
)
from django.conf import settings

print(f"DATA_DIR={settings.DATA_DIR}")
dns, ips = collect_desired_ui_sans()
print(f"Desired SANs dns={dns} ips={[str(i) for i in ips]}")
cert, key = ensure_default_ui_server_cert()
print(f"UI server cert: {cert}")
print(f"UI server key:  {key}")
print(f"Product CA fingerprint: {get_ca_fingerprint()}")
status = get_ui_tls_status()
leaf = (status.get("certificate") or {})
print(f"Leaf SANs: {leaf.get('sans')}")
print(f"Agents fetch CA from /.well-known/logstashui/ca.crt (no shared volume)")
assert ui_server_cert_path().is_file(), "ui-server.crt missing after ensure"
PY
echo ""

# Display welcome message
echo ""
echo "=========================================="
echo "  Welcome to LogstashUI!"
echo "=========================================="
echo ""
echo "To get started, please visit:"
echo "  https://<your-server-ip-or-hostname>:8443"
echo ""
echo "Replace <your-server-ip-or-hostname> with:"
echo "  - localhost (if accessing locally)"
echo "  - Your server's IP address"
echo "  - Your server's hostname/domain"
echo ""
echo "UI serves HTTPS on :8443 using \$LOGSTASHUI_DATA_DIR/tls/ui-server.* (product CA by default)."
echo "Agents pin the product CA from /.well-known/logstashui/ca.crt — not a shared volume."
echo ""
echo "=========================================="
echo ""

# Assemble fullchain for gunicorn --certfile (leaf + optional intermediates)
TLS_DIR="$DATA_DIR/tls"
if [ -f "$TLS_DIR/ui-server.crt" ]; then
  if [ -f "$TLS_DIR/ui-server.chain.crt" ]; then
    cat "$TLS_DIR/ui-server.crt" "$TLS_DIR/ui-server.chain.crt" > "$TLS_DIR/gunicorn-fullchain.pem"
  else
    cp "$TLS_DIR/ui-server.crt" "$TLS_DIR/gunicorn-fullchain.pem"
  fi
fi

if [ "$1" = "gunicorn" ]; then
  shift
  exec gunicorn \
    --certfile "$TLS_DIR/gunicorn-fullchain.pem" \
    --keyfile "$TLS_DIR/ui-server.key" \
    "$@"
fi

exec "$@"
