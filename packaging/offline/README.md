# Offline freeze templates

Used by `bin/freeze_logstashui.sh`. Placeholders `__VERSION__`, `__GIT_SHA__`, `__IMAGE_NAME__` are substituted at freeze time.

These files are **not** shipped in the default hatchling wheel (systemd templates stay in `src/logstashui/LogstashUI/packaging/`).
