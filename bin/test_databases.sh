#!/usr/bin/env bash
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
echo "==> SQLite pytest (no compose)"
uv run pytest src/logstashui --no-cov
echo "==> Starting Postgres / MariaDB / MySQL"
"${COMPOSE[@]}" up -d --wait
run_engine () {
  local name="$1"; shift
  echo "==> pytest on ${name}"
  env "$@" uv run pytest src/logstashui --no-cov
}
run_engine postgresql LOGSTASHUI_DB_ENGINE=postgresql LOGSTASHUI_DB_HOST=127.0.0.1 LOGSTASHUI_DB_PORT=55432 LOGSTASHUI_DB_NAME=logstashui LOGSTASHUI_DB_USER=logstashui LOGSTASHUI_DB_PASSWORD=logstashui
run_engine mariadb LOGSTASHUI_DB_ENGINE=mysql LOGSTASHUI_DB_HOST=127.0.0.1 LOGSTASHUI_DB_PORT=53306 LOGSTASHUI_DB_NAME=logstashui LOGSTASHUI_DB_USER=root LOGSTASHUI_DB_PASSWORD=logstashui
run_engine mysql LOGSTASHUI_DB_ENGINE=mysql LOGSTASHUI_DB_HOST=127.0.0.1 LOGSTASHUI_DB_PORT=53307 LOGSTASHUI_DB_NAME=logstashui LOGSTASHUI_DB_USER=root LOGSTASHUI_DB_PASSWORD=logstashui
echo "==> Live migrator tests"
env LOGSTASHUI_LIVE_DB=1 LOGSTASHUI_LIVE_PG_PORT=55432 LOGSTASHUI_LIVE_MARIA_PORT=53306 LOGSTASHUI_LIVE_MYSQL_PORT=53307 LOGSTASHUI_LIVE_DB_USER=root LOGSTASHUI_LIVE_DB_PASSWORD=logstashui LOGSTASHUI_LIVE_PG_USER=logstashui uv run pytest src/logstashui/LogstashUI/tests/test_migrate_live.py -v --no-cov
if [[ "$KEEP" -eq 0 ]]; then "${COMPOSE[@]}" down -v; fi
