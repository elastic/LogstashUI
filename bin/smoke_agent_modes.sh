#!/usr/bin/env bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# E2E smoke for agent modes (Packaged / Managed / Simulate / VERSION / registry).
#
# Usage (from repo root or bin/):
#   ./bin/smoke_agent_modes.sh              # health + django + agent offline tests
#   ./bin/smoke_agent_modes.sh --rebuild    # rebuild compose smoke images first
#   ./bin/smoke_agent_modes.sh --offline    # agent pytest only (no docker)
#   ./bin/smoke_agent_modes.sh --compose-only  # health + django only
#
# Requires: docker (for compose phases), Python+pytest in LogstashAgent (offline).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_ROOT="$(cd "$UI_ROOT/../LogstashAgent" 2>/dev/null && pwd || true)"
DOCKER_DIR="$UI_ROOT/docker"

REBUILD=0
OFFLINE=0
COMPOSE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    --offline) OFFLINE=1 ;;
    --compose-only) COMPOSE_ONLY=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
  esac
done

PASS=0
FAIL=0
ok()  { echo "  OK  $*"; PASS=$((PASS+1)); }
bad() { echo " FAIL $*"; FAIL=$((FAIL+1)); }

echo "=========================================="
echo " Logstash agent-modes E2E smoke"
echo "=========================================="
echo "UI root:    $UI_ROOT"
echo "Agent root: ${AGENT_ROOT:-'(not found)'}"
echo ""

# ---------------------------------------------------------------------------
# Phase 0: offline agent pytest
# ---------------------------------------------------------------------------
run_agent_offline() {
  echo "[Phase 0] Agent offline smoke (pytest)"
  if [[ -z "${AGENT_ROOT:-}" || ! -d "$AGENT_ROOT" ]]; then
    bad "LogstashAgent sibling repo not found at ../LogstashAgent"
    return
  fi
  if [[ -x "$AGENT_ROOT/.venv/bin/python" ]]; then
    PY="$AGENT_ROOT/.venv/bin/python"
  else
    PY=python3
  fi
  (
    cd "$AGENT_ROOT"
    export PYTHONPATH=src
    if ! "$PY" -m pytest \
      tests/test_e2e_agent_modes_smoke.py \
      tests/test_coexistence.py \
      tests/test_multi_instance_units.py \
      tests/test_install_registry.py \
      tests/test_logstash_runtime_apply.py \
      -q --tb=line -p no:cacheprovider 2>/dev/null
    then
      # retry without -p if plugin flags differ
      "$PY" -m pytest \
        tests/test_e2e_agent_modes_smoke.py \
        tests/test_coexistence.py \
        tests/test_multi_instance_units.py \
        tests/test_install_registry.py \
        tests/test_logstash_runtime_apply.py \
        -q --tb=line
    fi
  ) && ok "agent offline pytest suite" || bad "agent offline pytest suite"
  echo ""
}

if [[ "$OFFLINE" -eq 1 ]]; then
  run_agent_offline
  echo "=========================================="
  echo " Result: $PASS passed, $FAIL failed (offline only)"
  echo "=========================================="
  [[ "$FAIL" -eq 0 ]]
  exit $?
fi

# ---------------------------------------------------------------------------
# Docker compose helpers
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found"
  exit 1
fi
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "ERROR: docker compose not found"
  exit 1
fi

UI_CTR="$(docker ps --format '{{.Names}}' | grep -E 'logstashui-logstashui|logstashui$' | head -1 || true)"
AGENT_CTR="$(docker ps --format '{{.Names}}' | grep -E 'logstashagent' | head -1 || true)"

compose_up() {
  echo "[Compose] Starting smoke stack (embedded profile)..."
  # Host SANs for product CA (same idea as start_logstashui.sh — PTR FQDNs preferred)
  if [[ -z "${LOGSTASHUI_HOST_IPS:-}" ]]; then
    if command -v ip >/dev/null 2>&1; then
      LOGSTASHUI_HOST_IPS=$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | tr '\n' ',' | sed 's/,$//')
    elif command -v ifconfig >/dev/null 2>&1; then
      LOGSTASHUI_HOST_IPS=$(ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" {print $2}' | paste -sd, -)
    fi
    export LOGSTASHUI_HOST_IPS
  fi
  if [[ -z "${LOGSTASHUI_HOST_HOSTNAME:-}" ]]; then
    first_fqdn=""
    if [[ -n "${LOGSTASHUI_HOST_IPS:-}" ]]; then
      IFS=',' read -ra _smoke_ips <<< "$LOGSTASHUI_HOST_IPS"
      for _ip in "${_smoke_ips[@]}"; do
        [[ -z "$_ip" ]] && continue
        _name=""
        if command -v dig >/dev/null 2>&1; then
          _name=$(dig +short -x "$_ip" 2>/dev/null | head -1 | sed 's/\.$//')
        fi
        if [[ -z "$_name" ]] && command -v python3 >/dev/null 2>&1; then
          _name=$(python3 -c "
import socket
socket.setdefaulttimeout(1.0)
try:
    print(socket.gethostbyaddr('$_ip')[0].rstrip('.'))
except Exception:
    pass
" 2>/dev/null || true)
        fi
        if [[ -n "$_name" && "$_name" != "$_ip" && "$_name" == *.* ]]; then
          first_fqdn="$_name"
          break
        fi
      done
    fi
    export LOGSTASHUI_HOST_HOSTNAME="${first_fqdn:-$(hostname -f 2>/dev/null || hostname)}"
  fi
  if [[ -z "${LOGSTASHUI_TLS_SANS:-}" && -n "${LOGSTASHUI_HOST_HOSTNAME:-}" ]]; then
    export LOGSTASHUI_TLS_SANS="${LOGSTASHUI_HOST_HOSTNAME}${LOGSTASHUI_HOST_IPS:+,${LOGSTASHUI_HOST_IPS}}"
  fi
  cd "$DOCKER_DIR"
  # shellcheck disable=SC2086
  $DC -f docker-compose.yml -f docker-compose.smoke.yml --profile embedded up -d --build
  echo "[Compose] Waiting for UI health..."
  for i in $(seq 1 60); do
    if curl -skf "https://127.0.0.1:8443/.well-known/logstashui/ca.crt" >/dev/null 2>&1; then
      echo "  UI ready after ${i}s"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: UI did not become healthy"
  return 1
}

if [[ "$REBUILD" -eq 1 ]]; then
  compose_up
  UI_CTR="$(docker ps --format '{{.Names}}' | grep -E 'logstashui-logstashui|logstashui$' | head -1 || true)"
  AGENT_CTR="$(docker ps --format '{{.Names}}' | grep -E 'logstashagent' | head -1 || true)"
fi

# ---------------------------------------------------------------------------
# Phase 1: HTTP health
# ---------------------------------------------------------------------------
echo "[Phase 1] HTTPS health probes"
if curl -skf "https://127.0.0.1:8443/.well-known/logstashui/ca.crt" >/dev/null 2>&1; then
  ok "UI product CA https://127.0.0.1:8443/.well-known/logstashui/ca.crt"
else
  bad "UI product CA not reachable (start stack or pass --rebuild)"
fi
if curl -skf "https://127.0.0.1:9500/" >/dev/null 2>&1 || curl -sk -o /dev/null -w '' "https://127.0.0.1:9500/" 2>/dev/null; then
  CODE=$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:9500/" || echo 000)
  if [[ "$CODE" != "000" && "$CODE" != "" ]]; then
    ok "Embedded agent HTTPS :9500 (HTTP $CODE)"
  else
    bad "Embedded agent HTTPS :9500"
  fi
else
  CODE=$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:9500/" || echo 000)
  if [[ "$CODE" != "000" ]]; then
    ok "Embedded agent HTTPS :9500 (HTTP $CODE)"
  else
    bad "Embedded agent HTTPS :9500 not reachable"
  fi
fi
echo ""

# ---------------------------------------------------------------------------
# Phase 2: Django enroll / policy smoke
# ---------------------------------------------------------------------------
echo "[Phase 2] Django policy + enroll smoke"
if [[ -z "${UI_CTR:-}" ]]; then
  bad "No logstashui container running"
else
  # Copy script into container and run
  SMOKE_SRC="$SCRIPT_DIR/smoke_agent_modes_django.py"
  if [[ ! -f "$SMOKE_SRC" ]]; then
    bad "Missing $SMOKE_SRC"
  else
    docker cp "$SMOKE_SRC" "$UI_CTR:/tmp/smoke_agent_modes_django.py"
    if docker exec -w /app/src/logstashui "$UI_CTR" python /tmp/smoke_agent_modes_django.py; then
      ok "Django agent-modes smoke"
    else
      bad "Django agent-modes smoke (rebuild with --rebuild if migration 0025 missing)"
    fi
  fi
fi
echo ""

# ---------------------------------------------------------------------------
# Phase 3: Agent offline (unless compose-only)
# ---------------------------------------------------------------------------
if [[ "$COMPOSE_ONLY" -eq 0 ]]; then
  run_agent_offline
fi

echo "=========================================="
echo " Result: $PASS passed, $FAIL failed"
echo "=========================================="
if [[ "$FAIL" -gt 0 ]]; then
  echo "Hints:"
  echo "  - Stale UI image without PACKAGED/MANAGED:  $0 --rebuild"
  echo "  - Agent-only:  $0 --offline"
  echo "  - See docs: docs/docs/logstashagent/general/roles.md"
  exit 1
fi
exit 0
