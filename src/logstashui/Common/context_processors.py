#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Template context processors for nav, version, and experimental mode."""

from Site.views import check_for_update
from PipelineManager.models import Connection
from Management.models import Settings


def version_update_info(request):
    """Add ``version_update`` (latest-release check) to every template."""
    update_info = check_for_update()
    return {
        'version_update': update_info
    }


def navigation_highlight(request):
    """Choose which nav item gets the throbbing onboarding border.

    If no connections exist, highlight Connection Manager. SNMP highlighting
    is tracked in localStorage on the client — this processor does not query
    Device rows.

    Returns:
        Dict with ``highlight_connection_manager`` and ``has_connections``.
    """
    has_connections = Connection.objects.exists()

    return {
        'highlight_connection_manager': not has_connections,
        'has_connections': has_connections,
    }


def experimental_mode(request):
    """Add ``experimental_mode_enabled`` from ``Settings``, defaulting False."""
    try:
        app_settings = Settings.get_settings()
        return {
            'experimental_mode_enabled': app_settings.experimental_mode
        }
    except Exception:
        # If settings table doesn't exist yet, default to False
        return {
            'experimental_mode_enabled': False
        }
