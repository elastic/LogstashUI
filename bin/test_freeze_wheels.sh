#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# Smoke the air-gapped wheelhouse: unzip, pip --no-index in a network-none
# linux/amd64 CPython 3.12 container. Pull python:3.12-slim first (needs net).

set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
OUT="${1:-$ROOT/dist/offline}"

ZIP=$(ls -1 "$OUT"/logstashui-*-offline-wheels-linux-x86_64-cp312.zip 2>/dev/null | tail -n 1 || true)
[[ -n "$ZIP" && -f "$ZIP" ]] || {
    echo "ERROR: no wheels zip in $OUT. Run: bin/freeze_logstashui.sh --wheels" >&2
    exit 1
}

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
unzip -q "$ZIP" -d "$WORKDIR"
STAGE=$(find "$WORKDIR" -maxdepth 1 -type d -name 'logstashui-*-offline-wheels-*' | head -n 1)
[[ -n "$STAGE" ]] || STAGE=$WORKDIR

shopt -s nullglob
sdists=("$STAGE"/wheels/*.tar.gz)
if (( ${#sdists[@]} )); then
    echo "ERROR: sdist in wheelhouse" >&2
    printf '%s\n' "${sdists[@]}"
    exit 1
fi

command -v docker >/dev/null 2>&1 || {
    echo "ERROR: docker required for network-none install smoke" >&2
    exit 1
}

echo "==> docker pull python:3.12-slim (linux/amd64)"
docker pull --platform linux/amd64 python:3.12-slim

echo "==> install.sh + logstashui --help / manage check (--network=none)"
docker run --rm \
    --platform linux/amd64 \
    --network=none \
    -v "$STAGE:/offline:ro" \
    -w /tmp \
    python:3.12-slim \
    bash -lc '
        set -euo pipefail
        cp -a /offline /tmp/pkg
        cd /tmp/pkg
        PYTHON=python3 sh install.sh
        .venv/bin/logstashui --help
        .venv/bin/logstashui manage check
    '

echo "Wheels freeze smoke passed: $ZIP"
