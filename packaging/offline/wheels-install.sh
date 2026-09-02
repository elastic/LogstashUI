#!/bin/sh
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# Air-gapped install: CPython 3.12 x86_64 venv + pip --no-index.
# Do not upgrade pip (that hits PyPI).

set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
WHEELS="$HERE/wheels"
PYTHON="${PYTHON:-python3.12}"

die() {
    printf '%s\n' "$*" >&2
    exit 1
}

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    else
        die "need CPython 3.12 x86_64 (python3.12 not found). On Debian/Ubuntu: apt install python3.12 python3.12-venv"
    fi
fi

"$PYTHON" - <<'PY' || die "need CPython 3.12 x86_64"
import platform
import sys

if sys.version_info[:2] != (3, 12):
    sys.exit(1)
if sys.maxsize <= 2**32:
    sys.exit(1)
mach = platform.machine().lower()
if mach not in ("x86_64", "amd64"):
    sys.exit(1)
PY

[ -d "$WHEELS" ] || die "missing $WHEELS"

VENV="$HERE/.venv"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install \
    --disable-pip-version-check \
    --no-index \
    --no-cache-dir \
    --find-links "$WHEELS" \
    'LogstashUI[databases]'

printf '\nInstalled into %s\n' "$VENV"
printf 'Start:\n'
printf '  %s/bin/logstashui serve\n' "$VENV"
printf 'Data directory default: $(pwd)/logstashui_data  (override LOGSTASHUI_DATA_DIR)\n'
printf 'Configuration is environment variables only. See README.md.\n'
