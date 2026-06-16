#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Site.views import check_for_update
from PipelineManager.models import Connection
from Management.models import Settings


def version_update_info(request):
    """
    Context processor to add version update information to all templates.
    """
    update_info = check_for_update()
    return {
        'version_update': update_info
    }


def navigation_highlight(request):
    """
    Context processor to determine which navigation item should have the throbbing border.
    Logic:
    - If no connections exist: highlight "Connection Manager"
    - If connections exist and user has never visited SNMP: highlight "SNMP Devices" (tracked
      via localStorage on the client — no Device DB query needed here)
    """
    has_connections = Connection.objects.exists()

    return {
        'highlight_connection_manager': not has_connections,
        'has_connections': has_connections,
    }


def experimental_mode(request):
    """
    Context processor to add experimental mode status to all templates.
    """
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
