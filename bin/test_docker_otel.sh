#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# Smoke that a pre-built LogstashUI image includes LogstashUI[otel].
# Does not build the image (slow). Not a default PR check.
#
#   IMAGE=logstashui:0.5.2-dev bin/test_docker_otel.sh
#   bin/test_docker_otel.sh logstashui:0.5.2-dev

set -euo pipefail

IMAGE="${1:-${IMAGE:-}}"
if [[ -z "$IMAGE" ]]; then
    echo "ERROR: pass an image tag or set IMAGE. Build first:" >&2
    echo "  docker build -f docker/Dockerfile -t logstashui:0.5.2-dev ." >&2
    echo "  # or: bin/start_logstashui.sh --rebuild" >&2
    exit 1
fi

command -v docker >/dev/null 2>&1 || {
    echo "ERROR: docker required" >&2
    exit 1
}

docker image inspect "$IMAGE" >/dev/null 2>&1 || {
    echo "ERROR: image ${IMAGE} is not local. Build it; this script never docker pull." >&2
    exit 1
}

echo "==> ${IMAGE}: import opentelemetry.sdk + instrumentation.django"
docker run --rm --entrypoint python "$IMAGE" -c \
    "import opentelemetry.sdk; import opentelemetry.instrumentation.django; print('otel extra ok')"

echo "Docker OTEL smoke passed: $IMAGE"
