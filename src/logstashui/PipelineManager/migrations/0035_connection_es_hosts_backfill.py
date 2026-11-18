from urllib.parse import urlparse

from django.db import migrations


def _legacy_host(host, port):
    """Return the single host string the pre-es_hosts code dialled."""
    return f"{host}:{port}" if port else host


def _split(url):
    """Split a node URL into ``(host, port)``; URLs with a path stay whole."""
    parsed = urlparse(url if '://' in url else f'//{url}')
    try:
        port = parsed.port
    except ValueError:
        return url, None
    if port is None or parsed.path.strip('/'):
        return url, None
    return url.rsplit(':', 1)[0], port


def forwards(apps, schema_editor):
    """Copy each URL-mode CENTRALIZED row's host verbatim into es_hosts."""
    Connection = apps.get_model('PipelineManager', 'Connection')
    rows = Connection.objects.filter(connection_type='CENTRALIZED').exclude(host__isnull=True).exclude(host='')
    for conn in rows:
        if conn.es_hosts or conn.cloud_id:
            continue
        Connection.objects.filter(pk=conn.pk).update(es_hosts=[_legacy_host(conn.host, conn.port)])


def backwards(apps, schema_editor):
    """Put the first es_hosts node back into host/port.

    Rows whose host/port already produce that node are left untouched, so
    rows that were never edited get their original values back exactly.
    """
    Connection = apps.get_model('PipelineManager', 'Connection')
    for conn in Connection.objects.filter(connection_type='CENTRALIZED'):
        hosts = [h for h in (conn.es_hosts or []) if isinstance(h, str) and h.strip()]
        if not hosts:
            continue
        if conn.host and _legacy_host(conn.host, conn.port) == hosts[0]:
            continue
        host, port = _split(hosts[0])
        Connection.objects.filter(pk=conn.pk).update(host=host, port=port)


class Migration(migrations.Migration):

    dependencies = [
        ('PipelineManager', '0034_connection_es_hosts_kibana_url'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
