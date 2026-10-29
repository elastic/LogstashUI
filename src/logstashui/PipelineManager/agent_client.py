#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Credentials for UI → LogstashAgent API calls.

Every agent ``/_logstash/*`` route requires ``Authorization: ApiKey <key>``:

- Enrolled agents: per-connection ``Connection.agent_inbound_key``, issued at
  enrollment or delivered (encrypted) on check-in.
- Embedded agent (compose / local, never enrolled): ``settings.LOGSTASH_AGENT_API_KEY``,
  shared with the agent via the ``LOGSTASH_AGENT_API_KEY`` env var.

The embedded key is never sent to an enrolled (remote) agent.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _embedded_headers() -> dict:
    key = getattr(settings, "LOGSTASH_AGENT_API_KEY", None)
    if not key:
        logger.warning("LOGSTASH_AGENT_API_KEY is not set; embedded agent calls will be rejected")
        return {}
    return {"Authorization": f"ApiKey {key}"}


def agent_auth_headers(connection=None) -> dict:
    """Return the auth header for calling an agent.

    Args:
        connection: ``Connection`` instance, connection id, or None for the
            embedded agent at ``settings.LOGSTASH_AGENT_URL``.
    """
    if connection is None:
        return _embedded_headers()

    from PipelineManager.agent_modes import is_embedded_connection
    from PipelineManager.models import Connection

    if not isinstance(connection, Connection):
        connection = Connection.objects.select_related("policy").filter(pk=connection).first()
        if connection is None:
            return {}
    if is_embedded_connection(connection):
        return _embedded_headers()

    key = connection.get_agent_inbound_key()
    if not key:
        logger.warning(
            "Connection %s has no agent inbound key yet (delivered on next check-in)",
            connection.pk,
        )
        return {}
    return {"Authorization": f"ApiKey {key}"}
