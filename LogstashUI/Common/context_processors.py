from Site.views import check_for_update
from PipelineManager.models import Connection
from SNMP.models import Device


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
    - If connections exist but no devices: highlight "SNMP Devices"
    - If both exist: no highlight
    """
    has_connections = Connection.objects.exists()
    has_devices = Device.objects.exists()
    
    highlight_connection_manager = not has_connections
    highlight_snmp_devices = has_connections and not has_devices
    
    return {
        'highlight_connection_manager': highlight_connection_manager,
        'highlight_snmp_devices': highlight_snmp_devices
    }
