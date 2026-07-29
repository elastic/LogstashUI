#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

set -e

# Change to Django project directory
cd /app/src/logstashui

# Create data directory if it doesn't exist
mkdir -p /app/data

# Diagnostic: Check data directory permissions and contents
echo "=========================================="
echo "Database Directory Diagnostics"
echo "=========================================="
echo "Directory permissions:"
ls -lah /app/ | grep data
echo ""
echo "Directory contents:"
ls -lah /app/data/
echo ""
echo "Current user: $(whoami)"
echo "User ID: $(id)"
echo ""

# Check if database file exists and is readable
if [ -f /app/data/db.sqlite3 ]; then
    echo "Database file exists ($(stat -c%s /app/data/db.sqlite3) bytes)"
    if [ -r /app/data/db.sqlite3 ]; then
        echo "Database file is readable"
    else
        echo "WARNING: Database file exists but is NOT readable!"
    fi
    if [ -w /app/data/db.sqlite3 ]; then
        echo "Database file is writable"
    else
        echo "WARNING: Database file exists but is NOT writable!"
    fi
    
    # Check if migrations table exists
    echo ""
    echo "Checking for existing migrations table..."
    if sqlite3 /app/data/db.sqlite3 "SELECT COUNT(*) FROM django_migrations;" 2>/dev/null; then
        MIGRATION_COUNT=$(sqlite3 /app/data/db.sqlite3 "SELECT COUNT(*) FROM django_migrations;" 2>/dev/null)
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

# Product CA + UI server cert for nginx (written under data/tls/; agents pull CA via well-known)
echo "Ensuring product CA and UI server certificate..."
python - <<'PY'
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from Common.product_ca import ensure_default_ui_server_cert, get_ca_fingerprint, ui_server_cert_path

cert, key = ensure_default_ui_server_cert()
print(f"UI server cert: {cert}")
print(f"UI server key:  {key}")
print(f"Product CA fingerprint: {get_ca_fingerprint()}")
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
echo "UI serves HTTPS on :8443 using data/tls/ui-server.* (product CA by default)."
echo "Agents pin the product CA from /.well-known/logstashui/ca.crt — not a shared volume."
echo ""
echo "=========================================="
echo ""

# Assemble fullchain for gunicorn --certfile (leaf + optional intermediates)
TLS_DIR="/app/src/logstashui/data/tls"
if [ -f "$TLS_DIR/ui-server.crt" ]; then
  if [ -f "$TLS_DIR/ui-server.chain.crt" ]; then
    cat "$TLS_DIR/ui-server.crt" "$TLS_DIR/ui-server.chain.crt" > "$TLS_DIR/gunicorn-fullchain.pem"
  else
    cp "$TLS_DIR/ui-server.crt" "$TLS_DIR/gunicorn-fullchain.pem"
  fi
fi

exec "$@"
