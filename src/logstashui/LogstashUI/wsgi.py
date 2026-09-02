#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
WSGI config for logstashui project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import ssl
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LogstashUI.settings')

from LogstashUI.database import ensure_psycopg_gevent

# gunicorn --worker-class gevent monkey-patches select before this module loads.
application = get_wsgi_application()
ensure_psycopg_gevent()


# Quiet gevent/gunicorn spam: clients that reject the product CA (browser
# probes, scanners, default-trust Python) abort the handshake with
# CERTIFICATE_UNKNOWN / UNKNOWN_CA. Those are not app bugs; full greenlet
# tracebacks every 5s drown real errors. Successful HTTP still access-logs.
try:
    import gevent.hub

    _hub_print = gevent.hub.Hub.handle_error

    def _quiet_tls_handshake_errors(self, context, type, value, tb):  # noqa: A002
        if isinstance(value, ssl.SSLError):
            msg = str(value).lower()
            if (
                "certificate unknown" in msg
                or "unknown ca" in msg
                or "certificate_unknown" in msg
            ):
                return
        return _hub_print(self, context, type, value, tb)

    gevent.hub.Hub.handle_error = _quiet_tls_handshake_errors
except Exception:
    pass
