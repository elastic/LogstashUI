# LogstashUI experimental standalone (__VERSION__)

**Experimental.** PyInstaller onedir for Linux **x86_64**. No Python on the host. Not production-supported until `./logstashui serve` completes migrate, SNMP sync, collectstatic, and HTTPS :8443 without network.

Gunicorn stays `--worker-class gevent`. If this bundle cannot serve, that is a freeze bug — do not switch workers as a workaround without amending the design spec.

## Run

```sh
./run.sh
# or:
./logstashui/logstashui serve
```

Data dir default: `$(pwd)/logstashui_data`. Same `LOGSTASHUI_*` env as a wheel/Docker install.

systemd: set `ExecStart=` to the unpacked `logstashui/logstashui serve`. This zip does not write units.

Git: `__GIT_SHA__`
