#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Public product CA endpoint for agent enroll pin-and-fetch."""

import logging

from django.http import HttpResponse
from django.views.decorators.http import require_GET

from Common.product_ca import get_ca_pem

logger = logging.getLogger(__name__)


@require_GET
def product_ca_crt(request):
    """
    GET /.well-known/logstashui/ca.crt

    Returns the product CA certificate (PEM). Public; used by agents that
    receive a fingerprint in the enrollment token.
    """
    try:
        pem = get_ca_pem()
    except Exception as e:
        logger.error("Failed to serve product CA: %s", e, exc_info=True)
        return HttpResponse("CA unavailable", status=503, content_type="text/plain")
    return HttpResponse(
        pem,
        content_type="application/x-pem-file",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": 'inline; filename="ca.crt"',
        },
    )
