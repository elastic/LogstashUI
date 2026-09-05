#!/bin/sh
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
TAR="$HERE/image.tar.gz"
IMAGE="__IMAGE_NAME__"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required to load this image" >&2
    exit 1
fi

[ -f "$TAR" ] || {
    echo "missing $TAR" >&2
    exit 1
}

echo "Loading $TAR ..."
docker load -i "$TAR"
echo "Loaded image: $IMAGE"
echo "Start (UI only, no Agent):"
echo "  docker compose -f \"$HERE/compose.offline.yml\" up -d"
echo "Browse https://<host>:8443  — data volume logstashui_data"
