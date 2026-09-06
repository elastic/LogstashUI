#!/bin/sh
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
BIN="$HERE/logstashui/logstashui"

if [ ! -x "$BIN" ]; then
    echo "missing $BIN" >&2
    exit 1
fi

exec "$BIN" serve "$@"
