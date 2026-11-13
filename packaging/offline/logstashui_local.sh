#!/bin/sh
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# acceptance #1
set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
INSTALL_DIR=$HERE
ACTION=
ARCHIVE=

usage() {
    printf '%s\n' "usage: logstashui_local.sh [--help|-h] [--install-path DIR] --install | serve | --serve [args] | --upgrade ARCHIVE_OR_DIR"
}

fail_usage() {
    printf '%s\n' "error: invalid invocation" >&2
    usage >&2
    exit 1
}

need_py() {
    printf '%s\n' "need CPython 3.12 x86_64" >&2
    exit 1
}

missing_wheels() {
    printf '%s\n' "missing wheels directory" >&2
    exit 1
}

py_ok() {
    "$1" -c 'import platform, sys; sys.exit(0 if (sys.version_info[:2] == (3, 12) and sys.implementation.name == "cpython" and platform.machine().lower() in ("x86_64", "amd64") and sys.maxsize > 2**32) else 1)'
}

discover_python() {
    if [ -n "${PYTHON:-}" ]; then
        py_ok "$PYTHON" || need_py
        return 0
    fi
    if command -v python3.12 >/dev/null 2>&1; then
        PYTHON=$(command -v python3.12)
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON=$(command -v python3)
    else
        need_py
    fi
    py_ok "$PYTHON" || need_py
}

do_install() {
    if [ ! -d "$HERE/wheels" ]; then
        missing_wheels
    fi
    discover_python
    "$PYTHON" -m venv "$VENV"
    "$VENV/bin/python" -m pip install --disable-pip-version-check --no-index --no-cache-dir --find-links "$HERE/wheels" "LogstashUI[databases,otel]"
}

find_wheels() {
    root=$1
    if [ -d "$root/wheels" ]; then
        WHEELS_DIR=$root/wheels
        return 0
    fi
    for d in "$root"/*/wheels; do
        if [ -d "$d" ]; then
            WHEELS_DIR=$d
            return 0
        fi
    done
    return 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --install-path)
            [ $# -ge 2 ] || fail_usage
            INSTALL_DIR=$2
            shift 2
            ;;
        --install)
            ACTION=install
            shift
            break
            ;;
        serve|--serve)
            ACTION=serve
            shift
            break
            ;;
        --upgrade)
            ACTION=upgrade
            shift
            ARCHIVE=${1:-}
            [ $# -gt 0 ] && shift
            break
            ;;
        *)
            fail_usage
            ;;
    esac
done

[ -n "$ACTION" ] || fail_usage

VENV=$INSTALL_DIR/.venv
DATA_DIR=${LOGSTASHUI_DATA_DIR:-$INSTALL_DIR/logstashui_data}
# acceptance #1: app path resolution expands a leading tilde (paths.py:53-58).
case $DATA_DIR in
    \~/*) DATA_DIR=$HOME/${DATA_DIR#\~/} ;;
    \~) DATA_DIR=$HOME ;;
esac

case "$ACTION" in
    install)
        do_install
        exit 0
        ;;
    serve)
        if [ ! -e "$VENV/bin/logstashui" ]; then
            do_install
        fi
        export PATH="$VENV/bin:$PATH"
        export LOGSTASHUI_DATA_DIR="$DATA_DIR"
        exec "$VENV/bin/logstashui" serve "$@"
        ;;
    upgrade)
        if [ ! -e "$VENV/bin/logstashui" ]; then
            printf '%s\n' "error: no existing virtualenv found to upgrade" >&2
            exit 1
        fi
        PID_DIR=$(LOGSTASHUI_DATA_DIR="$DATA_DIR" "$VENV/bin/python" -c "from LogstashUI.paths import resolve_data_dir; print(resolve_data_dir(migrate_legacy=False))" 2>/dev/null || true)
        PID_DIR=${PID_DIR:-$DATA_DIR}
        if [ -f "$PID_DIR/gunicorn.pid" ] && kill -0 $(cat "$PID_DIR/gunicorn.pid") 2>/dev/null; then
            printf '%s\n' "error: logstashui server is running. Stop server before upgrading." >&2
            exit 1
        fi
        if [ -z "$ARCHIVE" ]; then
            missing_wheels
        fi
        WHEELS_DIR=
        if [ -d "$ARCHIVE" ]; then
            find_wheels "$ARCHIVE" || missing_wheels
        elif [ -f "$ARCHIVE" ]; then
            case "$ARCHIVE" in
                *.zip) ;;
                *) missing_wheels ;;
            esac
            TMP=$(mktemp -d)
            trap 'rm -rf "$TMP"' EXIT
            "$VENV/bin/python" -m zipfile -e "$ARCHIVE" "$TMP"
            find_wheels "$TMP" || missing_wheels
        else
            missing_wheels
        fi
        "$VENV/bin/python" -m pip install --disable-pip-version-check --no-index --no-cache-dir --find-links "$WHEELS_DIR" --upgrade --upgrade-strategy eager "LogstashUI[databases,otel]"
        export LOGSTASHUI_DATA_DIR="$DATA_DIR"
        "$VENV/bin/logstashui" manage migrate --noinput
        exit 0
        ;;
esac
