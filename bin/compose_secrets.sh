#!/usr/bin/env bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# Sourced by start_logstashui.sh / smoke_agent_modes.sh.
#
# Per-install random secrets shared by the UI and the embedded agent:
#   LOGSTASH_AGENT_API_KEY       UI → agent /_logstash/* API (Authorization: ApiKey)
#   LOGSTASHUI_AGENT_CSR_SECRET  agent → UI server-cert bootstrap without enroll
# An explicitly exported value wins; otherwise one is generated once and kept
# (mode 600) in the host data dir so restarts reuse it.

_compose_random_secret() {
    head -c 32 /dev/urandom | base64 | tr -d '/+=\n'
}

ensure_compose_secret() {  # VAR FILE
    local var="$1" file="$2"
    if [ -n "${!var:-}" ]; then
        export "${var?}"
        return
    fi
    if [ ! -s "$file" ]; then
        (umask 077 && _compose_random_secret > "$file")
    fi
    export "$var=$(cat "$file")"
}

ensure_compose_secrets() {  # DATA_DIR
    mkdir -p "$1"
    ensure_compose_secret LOGSTASH_AGENT_API_KEY "$1/.agent_api_key"
    ensure_compose_secret LOGSTASHUI_AGENT_CSR_SECRET "$1/.agent_csr_secret"
}
