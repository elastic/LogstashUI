#!/usr/bin/env bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker/docker-compose.db.yml)
KEEP=0
if [[ "${1:-}" == "--keep" ]]; then KEEP=1; fi
if ! command -v docker >/dev/null; then
  echo "ERROR: Docker is required for bin/test_databases.sh" >&2
  echo "Default pytest (SQLite) still works: uv run pytest" >&2
  exit 1
fi

uv sync --extra databases --group dev

"${COMPOSE[@]}" up -d --wait

echo "==> Database test suite (testcontainers)"
uv run pytest tests/Database/ -v --no-cov
if [[ "$KEEP" -eq 0 ]]; then "${COMPOSE[@]}" down -v; fi
