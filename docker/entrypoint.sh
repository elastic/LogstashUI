#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

set -e

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

echo "=========================================="
echo "  LogstashUI"
echo "=========================================="
echo "LOGSTASHUI_DATA_DIR=$DATA_DIR"
echo "Directory permissions:"
ls -lah "$DATA_DIR" | head

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

echo ""
echo "User: $(id)"
echo "Command: $*"
echo "UI (default): https://<host>:8443"
echo "Config is environment-only (ConfigMap / /etc/default/logstashui)."
echo "=========================================="

if [ $# -eq 0 ]; then
  exec logstashui serve
fi

exec "$@"
