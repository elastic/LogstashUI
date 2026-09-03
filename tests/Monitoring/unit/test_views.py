#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import reverse
from unittest.mock import patch, MagicMock
import pytest

from Common.formatters import (
    _safe_get_numeric,
    _safe_extract_value,
    _format_uptime
)

from Monitoring.views import (
    check_for_monitoring_indices,
    get_logs,
    get_node_metrics,
    get_pipeline_metrics,
)

# ---------------------------------------------------------------------------
# _safe_get_numeric
# ---------------------------------------------------------------------------

def test_safe_get_numeric_none_returns_default():
    assert _safe_get_numeric(None) == 0


def test_safe_get_numeric_none_custom_default():
    assert _safe_get_numeric(None, default=99) == 99


def test_safe_get_numeric_integer():
    assert _safe_get_numeric(42) == 42


def test_safe_get_numeric_float():
    assert _safe_get_numeric(3.14) == 3.14


def test_safe_get_numeric_string_int():
    assert _safe_get_numeric("7") == 7


def test_safe_get_numeric_string_float():
    assert _safe_get_numeric("3.14") == 3.14


def test_safe_get_numeric_invalid_string():
    assert _safe_get_numeric("abc") == 0


def test_safe_get_numeric_list_with_value():
    assert _safe_get_numeric([5]) == 5


def test_safe_get_numeric_empty_list():
    assert _safe_get_numeric([]) == 0


def test_safe_get_numeric_list_uses_first_element():
    assert _safe_get_numeric([10, 20, 30]) == 10


# ---------------------------------------------------------------------------
# _safe_extract_value
# ---------------------------------------------------------------------------

def test_safe_extract_value_none():
    assert _safe_extract_value(None) == 0


def test_safe_extract_value_scalar():
    assert _safe_extract_value(7) == 7


def test_safe_extract_value_empty_list():
    assert _safe_extract_value([]) == 0


def test_safe_extract_value_all_none_list():
    assert _safe_extract_value([None, None]) == 0


def test_safe_extract_value_first_non_none():
    assert _safe_extract_value([None, 5, 10]) == 5


def test_safe_extract_value_all_empty_string_list():
    assert _safe_extract_value(['', '']) == 0


def test_safe_extract_value_custom_default():
    assert _safe_extract_value(None, default="N/A") == "N/A"


# ---------------------------------------------------------------------------
# _format_uptime
# ---------------------------------------------------------------------------

def test_format_uptime_seconds_only():
    assert _format_uptime(30_000) == "30s"


def test_format_uptime_minutes_and_seconds():
    assert _format_uptime(90_000) == "1m 30s"


def test_format_uptime_hours_and_minutes():
    assert _format_uptime(3_660_000) == "1h 1m"


def test_format_uptime_days_and_hours():
    assert _format_uptime(90_000_000) == "1d 1h"


def test_format_uptime_zero():
    assert _format_uptime(0) == "0s"


def test_format_uptime_exactly_one_hour():
    assert _format_uptime(3_600_000) == "1h 0m"


def test_format_uptime_exactly_one_day():
    assert _format_uptime(86_400_000) == "1d 0h"


# ---------------------------------------------------------------------------
# check_for_monitoring_indices
# ---------------------------------------------------------------------------

def _make_mock_es(index_names):
    """
    Return a mock ES client whose cat.indices returns json-format index records
    for the names provided.
    """
    mock_es = MagicMock()
    mock_es.cat.indices.return_value = [{'index': name} for name in index_names]
    return mock_es


def test_check_for_monitoring_indices_has_all():
    all_streams = [
        "metrics-logstash.plugins-000001",
        "metrics-logstash.node-000001",
        "metrics-logstash.pipeline-000001",
        "logs-logstash.log-000001",
        "metrics-logstash.health_report-000001",
    ]
    mock_es = _make_mock_es(all_streams)
    connections = [{'es': mock_es, 'name': 'test-conn'}]

    result = check_for_monitoring_indices(connections)

    assert result['test-conn']['has_all'] is True
    assert result['test-conn']['missing'] == []


def test_check_for_monitoring_indices_missing_all():
    mock_es = _make_mock_es([])  # no logstash indices at all
    connections = [{'es': mock_es, 'name': 'test-conn'}]

    result = check_for_monitoring_indices(connections)

    assert result['test-conn']['has_all'] is False
    assert len(result['test-conn']['missing']) == 5
    assert result['test-conn'].get('has_none') is True


def test_check_for_monitoring_indices_missing_some():
    # provide only some of the required streams
    partial_streams = [
        "metrics-logstash.node-000001",
        "logs-logstash.log-000001",
    ]
    mock_es = _make_mock_es(partial_streams)
    connections = [{'es': mock_es, 'name': 'test-conn'}]

    result = check_for_monitoring_indices(connections)

    assert result['test-conn']['has_all'] is False
    assert result['test-conn'].get('has_none') is not True  # some present, not none
    assert len(result['test-conn']['missing']) == 3


def test_check_for_monitoring_indices_multiple_connections():
    all_streams = [
        "metrics-logstash.plugins-000001",
        "metrics-logstash.node-000001",
        "metrics-logstash.pipeline-000001",
        "logs-logstash.log-000001",
        "metrics-logstash.health_report-000001",
    ]
    es_a = _make_mock_es(all_streams)
    es_b = _make_mock_es([])

    connections = [
        {'es': es_a, 'name': 'conn-a'},
        {'es': es_b, 'name': 'conn-b'},
    ]

    result = check_for_monitoring_indices(connections)

    assert result['conn-a']['has_all'] is True
    assert result['conn-b']['has_all'] is False


# ---------------------------------------------------------------------------
# get_logs
# ---------------------------------------------------------------------------

def _make_mock_es_with_logs(log_entries):
    mock_es = MagicMock()
    mock_es.search.return_value = {
        'hits': {
            'hits': [{'_source': entry} for entry in log_entries]
        }
    }
    return mock_es


def test_get_logs_no_filter_uses_match_all():
    mock_es = _make_mock_es_with_logs([])
    get_logs(mock_es)

    call_kwargs = mock_es.search.call_args[1]
    assert call_kwargs['query'] == {'match_all': {}}


def test_get_logs_with_node_filter():
    mock_es = _make_mock_es_with_logs([])
    get_logs(mock_es, logstash_node='my-node')

    call_kwargs = mock_es.search.call_args[1]
    assert call_kwargs['query']['bool']['filter'][0]['term']['host.hostname'] == 'my-node'


def test_get_logs_with_pipeline_filter():
    mock_es = _make_mock_es_with_logs([])
    get_logs(mock_es, pipeline_name='my-pipeline')

    call_kwargs = mock_es.search.call_args[1]
    filters = call_kwargs['query']['bool']['filter']
    pipeline_terms = [f for f in filters if 'logstash.log.pipeline_id' in f.get('term', {})]
    assert len(pipeline_terms) == 1
    assert pipeline_terms[0]['term']['logstash.log.pipeline_id'] == 'my-pipeline'


def test_get_logs_with_both_filters():
    mock_es = _make_mock_es_with_logs([])
    get_logs(mock_es, logstash_node='my-node', pipeline_name='my-pipeline')

    call_kwargs = mock_es.search.call_args[1]
    filters = call_kwargs['query']['bool']['filter']
    assert len(filters) == 2


def test_get_logs_returns_sources():
    entries = [
        {'message': 'hello', '@timestamp': '2024-01-01T00:00:00Z', 'log': {'level': 'INFO'}},
        {'message': 'world', '@timestamp': '2024-01-01T00:01:00Z', 'log': {'level': 'ERROR'}},
    ]
    mock_es = _make_mock_es_with_logs(entries)
    result = get_logs(mock_es)

    assert len(result) == 2
    assert result[0]['message'] == 'hello'


# ---------------------------------------------------------------------------
# get_node_metrics — non-CENTRALIZED connections are skipped
# ---------------------------------------------------------------------------

def test_get_node_metrics_skips_non_centralized():
    connections = [
        {'name': 'conn-a', 'connection_type': 'DIRECT', 'es': MagicMock()}
    ]
    result = get_node_metrics(connections)

    assert result['nodes'] == []
    assert result['cpu'] == 0
    assert result['heap_memory'] == 0


def test_get_node_metrics_filters_by_connection_name():
    es = MagicMock()
    es.search.return_value = {'aggregations': {'nodes': {'buckets': []}}}

    connections = [
        {'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': es},
        {'name': 'conn-b', 'connection_type': 'CENTRALIZED', 'es': MagicMock()},
    ]
    get_node_metrics(connections, connection_name='conn-a')

    # Only conn-a's ES client should have been called
    assert es.search.called


def test_get_node_metrics_no_aggregations_continues():
    mock_es = MagicMock()
    mock_es.search.return_value = {}  # no 'aggregations' key

    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es}]
    result = get_node_metrics(connections)

    assert result['nodes'] == []


# ---------------------------------------------------------------------------
# get_pipeline_metrics — no data paths
# ---------------------------------------------------------------------------

def test_get_pipeline_metrics_skips_non_centralized():
    connections = [
        {'name': 'conn-a', 'connection_type': 'DIRECT', 'es': MagicMock()}
    ]
    result = get_pipeline_metrics(connections)

    assert result['pipelines'] == []
    assert result['duration'] == 0


def test_get_pipeline_metrics_no_aggregations_continues():
    mock_es = MagicMock()
    mock_es.search.return_value = {}  # no 'aggregations' key

    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es}]
    result = get_pipeline_metrics(connections)

    assert result['pipelines'] == []
    assert result['connections_with_no_data'] == []


def test_get_pipeline_metrics_empty_host_buckets_adds_warning():
    mock_es = MagicMock()
    mock_es.search.return_value = {
        'aggregations': {'hosts': {'buckets': []}}
    }

    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]
    result = get_pipeline_metrics(connections)

    assert len(result['connections_with_no_data']) == 1
    assert result['connections_with_no_data'][0]['name'] == 'conn-a'


# ---------------------------------------------------------------------------
# View endpoint tests (HTTP layer)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_monitoring_page_no_connections(client, django_user_model):
    user = django_user_model.objects.create_user(username='testuser', password='testpass')
    client.force_login(user)

    with patch('Monitoring.views.check_for_monitoring_indices', return_value={}), \
         patch('Monitoring.views.get_elastic_connections_from_list', return_value=[]):
        response = client.get(reverse('monitoring'))

    assert response.status_code == 200
    assert response.context['has_connections'] is False


@pytest.mark.django_db
def test_get_logs_missing_connection_id_returns_400(client, django_user_model):
    user = django_user_model.objects.create_user(username='testuser2', password='testpass')
    client.force_login(user)

    response = client.get(reverse('GetLogs'))

    assert response.status_code == 400
    assert 'error' in response.json()


@pytest.mark.django_db
def test_get_logs_invalid_connection_id_returns_500(client, django_user_model):
    user = django_user_model.objects.create_user(username='testuser3', password='testpass')
    client.force_login(user)

    with patch('Monitoring.views.get_elastic_connection', side_effect=Exception("connection failed")):
        response = client.get(reverse('GetLogs'), {'connection_id': '99999'})

    assert response.status_code == 500
    data = response.json()
    # Should NOT echo raw exception detail to the client
    assert 'connection failed' not in data.get('error', '')


@pytest.mark.django_db
def test_get_node_metrics_returns_200(client, django_user_model):
    user = django_user_model.objects.create_user(username='testuser4', password='testpass')
    client.force_login(user)

    with patch('Monitoring.views.get_elastic_connections_from_list', return_value=[]):
        response = client.get(reverse('GetNodeMetrics'))

    assert response.status_code == 200


@pytest.mark.django_db
def test_get_pipeline_metrics_returns_200(client, django_user_model):
    user = django_user_model.objects.create_user(username='testuser5', password='testpass')
    client.force_login(user)

    with patch('Monitoring.views.get_elastic_connections_from_list', return_value=[]):
        response = client.get(reverse('GetPipelineMetrics'))

    assert response.status_code == 200


@pytest.mark.django_db
def test_get_pipeline_health_report_no_connection_id(client, django_user_model):
    """GetPipelineHealthReport with no connection_id should not crash — validate graceful failure."""
    user = django_user_model.objects.create_user(username='testuser6', password='testpass')
    client.force_login(user)

    with patch('Monitoring.views.get_elastic_connection', side_effect=Exception("bad id")):
        response = client.get(reverse('GetPipelineHealthReport'), {'pipeline': 'test'})

    # Should return a JSON response, not a raw 500 traceback page
    assert response.status_code in (400, 404, 500)


# ---------------------------------------------------------------------------
# check_for_monitoring_indices — string response branch
# ---------------------------------------------------------------------------

def test_check_for_monitoring_indices_string_response():
    """Exercises the string-parsing branch (cat.indices returns a string)"""
    # Simulate the table-format string that Elasticsearch cat.indices returns
    string_response = (
        "green open metrics-logstash.plugins-000001 abc 1 0\n"
        "green open metrics-logstash.node-000001 def 1 0\n"
        "green open metrics-logstash.pipeline-000001 ghi 1 0\n"
        "green open logs-logstash.log-000001 jkl 1 0\n"
        "green open metrics-logstash.health_report-000001 mno 1 0\n"
    )
    mock_es = MagicMock()
    mock_es.cat.indices.return_value = string_response  # plain string, not a list
    connections = [{'es': mock_es, 'name': 'str-conn'}]

    result = check_for_monitoring_indices(connections)

    assert result['str-conn']['has_all'] is True
    assert result['str-conn']['missing'] == []


def test_check_for_monitoring_indices_empty_string_response():
    """Empty string response results in everything missing"""
    mock_es = MagicMock()
    mock_es.cat.indices.return_value = ''
    connections = [{'es': mock_es, 'name': 'empty-conn'}]

    result = check_for_monitoring_indices(connections)

    assert result['empty-conn']['has_all'] is False
    assert result['empty-conn']['has_none'] is True


def test_check_for_monitoring_indices_data_stream_prefix():
    """Data streams prefixed with .ds- are detected via substring match"""
    ds_streams = [
        ".ds-metrics-logstash.plugins-000001",
        ".ds-metrics-logstash.node-000001",
        ".ds-metrics-logstash.pipeline-000001",
        ".ds-logs-logstash.log-000001",
        ".ds-metrics-logstash.health_report-000001",
    ]
    mock_es = MagicMock()
    mock_es.cat.indices.return_value = [{'index': name} for name in ds_streams]
    connections = [{'es': mock_es, 'name': 'ds-conn'}]

    result = check_for_monitoring_indices(connections)

    assert result['ds-conn']['has_all'] is True


# ---------------------------------------------------------------------------
# get_logs — query structure and parameters
# ---------------------------------------------------------------------------

def test_get_logs_uses_correct_index():
    """get_logs always queries the logs-logstash.log-* index"""
    mock_es = _make_mock_es_with_logs([])
    get_logs(mock_es)
    call_kwargs = mock_es.search.call_args[1]
    assert call_kwargs['index'] == 'logs-logstash.log-*'


def test_get_logs_size_is_1000():
    """get_logs always requests size=1000"""
    mock_es = _make_mock_es_with_logs([])
    get_logs(mock_es)
    call_kwargs = mock_es.search.call_args[1]
    assert call_kwargs['size'] == 1000


def test_get_logs_sorted_desc_by_timestamp():
    """get_logs sorts by @timestamp descending"""
    mock_es = _make_mock_es_with_logs([])
    get_logs(mock_es)
    call_kwargs = mock_es.search.call_args[1]
    sort = call_kwargs['sort']
    assert sort[0]['@timestamp']['order'] == 'desc'


def test_get_logs_returns_empty_list_when_no_hits():
    """get_logs returns [] when there are no hits"""
    mock_es = _make_mock_es_with_logs([])
    result = get_logs(mock_es)
    assert result == []


# ---------------------------------------------------------------------------
# get_node_metrics — happy path with real stats data
# ---------------------------------------------------------------------------

def _make_node_stats_response(
    hostname='host-1',
    cpu=40, heap=60,
    events_in=100, events_out=95, queue=5,
    reload_success=2, reload_failures=0,
    conn_id=None
):
    """Build a minimal es.search() response structure for get_node_metrics."""
    source = {
        'logstash': {
            'node': {
                'stats': {
                    'logstash': {'status': 'green', 'version': '8.12.0'},
                    'jvm': {'uptime_in_millis': 3_600_000, 'mem': {'heap_used_percent': heap}},
                    'os': {'cpu': {'percent': cpu}},
                    'events': {'in': events_in, 'out': events_out},
                    'queue': {'events_count': queue},
                    'reloads': {'successes': reload_success, 'failures': reload_failures},
                }
            }
        }
    }
    bucket = {
        'key': hostname,
        'last_hit': {'hits': {'hits': [{'_source': source['logstash']}]}},
        'connection_id': conn_id,
        'connection_name': 'test-conn',
    }
    # The actual source in last_hit is the full document, not just logstash
    bucket['last_hit']['hits']['hits'][0]['_source'] = {'logstash': source['logstash']}
    return bucket


def test_get_node_metrics_happy_path_aggregates_stats():
    """Happy path: node bucket data is aggregated into meta_agg_stats correctly"""
    bucket = _make_node_stats_response(
        events_in=100, events_out=90, queue=10,
        reload_success=3, reload_failures=1, cpu=50, heap=70
    )
    mock_es = MagicMock()
    mock_es.search.return_value = {
        'aggregations': {'nodes': {'buckets': [bucket]}}
    }
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    result = get_node_metrics(connections)

    assert result['events']['in'] == 100
    assert result['events']['out'] == 90
    assert result['events']['queued'] == 10
    assert result['reloads']['successes'] == 3
    assert result['reloads']['failures'] == 1
    assert 'host-1' in result['nodes']


def test_get_node_metrics_averages_cpu_and_heap_across_nodes():
    """CPU and heap_memory are averaged (not summed) when multiple nodes exist"""
    def make_bucket(hostname, cpu, heap):
        return _make_node_stats_response(hostname=hostname, cpu=cpu, heap=heap)

    bucket_a = make_bucket('host-a', cpu=40, heap=60)
    bucket_b = make_bucket('host-b', cpu=60, heap=80)

    mock_es = MagicMock()
    mock_es.search.return_value = {
        'aggregations': {'nodes': {'buckets': [bucket_a, bucket_b]}}
    }
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    result = get_node_metrics(connections)

    # Average of 40+60=100 / 2 nodes = 50
    assert result['cpu'] == 50.0
    # Average of 60+80=140 / 2 nodes = 70
    assert result['heap_memory'] == 70.0


def test_get_node_metrics_skips_bucket_with_missing_last_hit():
    """If last_hit data is missing (KeyError), the node is skipped without crashing"""
    bad_bucket = {
        'key': 'broken-host',
        'last_hit': {'hits': {'hits': []}},     # empty hits → IndexError
        'connection_id': 1,
        'connection_name': 'conn-a',
    }
    mock_es = MagicMock()
    mock_es.search.return_value = {
        'aggregations': {'nodes': {'buckets': [bad_bucket]}}
    }
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    # Should not raise
    result = get_node_metrics(connections)
    # Node appears in nodes list (key was appended before the KeyError)
    assert result['events']['in'] == 0


def test_get_node_metrics_logstash_host_filter_appended_to_query():
    """When logstash_host is provided, a term filter for host.hostname is added"""
    mock_es = MagicMock()
    mock_es.search.return_value = {'aggregations': {'nodes': {'buckets': []}}}
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    get_node_metrics(connections, logstash_host='my-host')

    call_kwargs = mock_es.search.call_args[1]
    filters = call_kwargs['query']['bool']['filter']
    host_filters = [f for f in filters if f.get('term', {}).get('host.hostname') == 'my-host']
    assert len(host_filters) == 1


# ---------------------------------------------------------------------------
# get_pipeline_metrics — happy path and edge cases
# ---------------------------------------------------------------------------

def _make_pipeline_bucket(pipeline_name='my-pipeline', events_in=200, events_out=195,
                           events_filtered=190, duration_ms=1000,
                           reload_success=1, reload_failures=0,
                           workers=4, batch_size=125, conn_id=1):
    """Build a minimal pipeline bucket for get_pipeline_metrics."""
    source = {
        'logstash': {
            'pipeline': {
                'host': {'name': 'host-1'},
                'info': {'workers': workers, 'batch_size': batch_size},
                'total': {
                    'events': {
                        'in': events_in, 'out': events_out, 'filtered': events_filtered
                    },
                    'time': {'duration': {'ms': duration_ms}},
                    'reloads': {'successes': reload_success, 'failures': reload_failures},
                    'queue': {'events_count': 0},
                }
            }
        }
    }
    return {
        'key': pipeline_name,
        'last_hit': {'hits': {'hits': [{'_source': source}]}},
        'connection_id': conn_id,
        'connection_name': 'conn-a',
    }


def test_get_pipeline_metrics_happy_path():
    """Happy path: pipeline bucket stats are aggregated correctly"""
    bucket = _make_pipeline_bucket(events_in=200, events_out=195, reload_success=2)
    host_buckets = [{'key': 'host-1', 'pipelines': {'buckets': [bucket]}}]

    mock_es = MagicMock()
    mock_es.search.return_value = {'aggregations': {'hosts': {'buckets': host_buckets}}}
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    result = get_pipeline_metrics(connections)

    assert result['events']['in'] == 200
    assert result['events']['out'] == 195
    assert result['reloads']['successes'] == 2
    assert 'my-pipeline' in result['pipelines']
    assert 'host-1' in result['hosts']


def test_get_pipeline_metrics_averages_duration():
    """Duration is averaged across pipeline buckets"""
    b1 = _make_pipeline_bucket('pipe-1', duration_ms=1000)
    b2 = _make_pipeline_bucket('pipe-2', duration_ms=2000)
    host_buckets = [{'key': 'host-1', 'pipelines': {'buckets': [b1, b2]}}]

    mock_es = MagicMock()
    mock_es.search.return_value = {'aggregations': {'hosts': {'buckets': host_buckets}}}
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    result = get_pipeline_metrics(connections)
    # Duration average: (1000 + 2000) / 2 buckets = 1500
    assert result['duration'] == 1500.0


def test_get_pipeline_metrics_skips_bucket_with_missing_last_hit():
    """Pipeline buckets that are missing last_hit data are skipped gracefully"""
    bad_bucket = {
        'key': 'broken-pipe',
        'last_hit': {'hits': {'hits': []}},  # empty → IndexError
        'connection_id': 1,
        'connection_name': 'conn-a',
    }
    host_buckets = [{'key': 'host-1', 'pipelines': {'buckets': [bad_bucket]}}]

    mock_es = MagicMock()
    mock_es.search.return_value = {'aggregations': {'hosts': {'buckets': host_buckets}}}
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    # Should not raise
    result = get_pipeline_metrics(connections)
    assert result['events']['in'] == 0


def test_get_pipeline_metrics_connection_name_filter_skips_non_matching():
    """When connection_name is set, non-matching connections are skipped"""
    mock_es_b = MagicMock()
    connections = [
        {'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': MagicMock(), 'id': 1},
        {'name': 'conn-b', 'connection_type': 'CENTRALIZED', 'es': mock_es_b, 'id': 2},
    ]
    mock_es_b.search.return_value = {'aggregations': {'hosts': {'buckets': []}}}

    get_pipeline_metrics(connections, connection_name='conn-b')

    assert mock_es_b.search.called
    # conn-a's ES client must NOT have been called
    assert not connections[0]['es'].search.called


def test_get_pipeline_metrics_logstash_host_filter_appended():
    """When logstash_host is provided, a term filter is appended to the query"""
    mock_es = MagicMock()
    mock_es.search.return_value = {'aggregations': {'hosts': {'buckets': []}}}
    connections = [{'name': 'conn-a', 'connection_type': 'CENTRALIZED', 'es': mock_es, 'id': 1}]

    get_pipeline_metrics(connections, logstash_host='my-host')

    call_kwargs = mock_es.search.call_args[1]
    filters = call_kwargs['query']['bool']['filter']
    host_filters = [
        f for f in filters
        if f.get('term', {}).get('logstash.pipeline.host.name') == 'my-host'
    ]
    assert len(host_filters) == 1


# ---------------------------------------------------------------------------
# get_pipeline_health_report
# ---------------------------------------------------------------------------

def test_get_pipeline_health_report_returns_hit_source():
    """When a hit is found, returns the _source document"""
    from Monitoring.views import get_pipeline_health_report

    source_doc = {'logstash': {'pipeline': {'id': 'main', 'status': 'healthy'}}}
    mock_es = MagicMock()
    mock_es.search.return_value = {
        'hits': {'hits': [{'_source': source_doc}]}
    }

    result = get_pipeline_health_report(mock_es, pipeline_name='main')
    assert result == source_doc


def test_get_pipeline_health_report_returns_empty_when_no_hits():
    """When no hits are found, returns an empty dict"""
    from Monitoring.views import get_pipeline_health_report

    mock_es = MagicMock()
    mock_es.search.return_value = {'hits': {'hits': []}}

    result = get_pipeline_health_report(mock_es, pipeline_name='nonexistent')
    assert result == {}


def test_get_pipeline_health_report_passes_pipeline_name_in_query():
    """The pipeline_name is passed into the match query"""
    from Monitoring.views import get_pipeline_health_report

    mock_es = MagicMock()
    mock_es.search.return_value = {'hits': {'hits': []}}

    get_pipeline_health_report(mock_es, pipeline_name='my-pipeline')

    call_kwargs = mock_es.search.call_args[1]
    match_val = call_kwargs['query']['bool']['filter']['match']['logstash.pipeline.id']
    assert match_val == 'my-pipeline'


def test_get_pipeline_health_report_queries_correct_index():
    """The health report query targets the correct index"""
    from Monitoring.views import get_pipeline_health_report

    mock_es = MagicMock()
    mock_es.search.return_value = {'hits': {'hits': []}}

    get_pipeline_health_report(mock_es, pipeline_name='p')

    call_kwargs = mock_es.search.call_args[1]
    assert call_kwargs['index'] == 'metrics-logstash.health_report-*'


# ---------------------------------------------------------------------------
# View-layer — success paths and header tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_logs_success_returns_json(client, django_user_model):
    """GetLogs with a valid connection should return JSON array of log entries"""
    user = django_user_model.objects.create_user(username='logsuser', password='testpass')
    client.force_login(user)

    entries = [
        {'message': 'hello', '@timestamp': '2024-01-01T00:00:00Z', 'log': {'level': 'INFO'}}
    ]
    mock_es = MagicMock()
    mock_es.search.return_value = {
        'hits': {'hits': [{'_source': e} for e in entries]}
    }

    with patch('Monitoring.views.get_elastic_connection', return_value=mock_es):
        response = client.get(reverse('GetLogs'), {'connection_id': '1'})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]['message'] == 'hello'


@pytest.mark.django_db
def test_get_node_metrics_response_has_available_hosts_header(client, django_user_model):
    """GetNodeMetrics adds the X-Available-Hosts header with the node list as JSON"""
    user = django_user_model.objects.create_user(username='headeruser', password='testpass')
    client.force_login(user)

    with patch('Monitoring.views.get_elastic_connections_from_list', return_value=[]):
        response = client.get(reverse('GetNodeMetrics'))

    assert response.status_code == 200
    import json as _json
    header = response.get('X-Available-Hosts')
    assert header is not None
    assert isinstance(_json.loads(header), list)


@pytest.mark.django_db
def test_get_pipeline_health_report_success_returns_json(client, django_user_model):
    """GetPipelineHealthReport with a valid connection returns a JSON health report"""
    user = django_user_model.objects.create_user(username='hruser', password='testpass')
    client.force_login(user)

    health_doc = {'status': 'green', 'indicators': {}}
    mock_es = MagicMock()

    with patch('Monitoring.views.get_elastic_connection', return_value=mock_es), \
         patch('Monitoring.views.get_pipeline_health_report', return_value=health_doc):
        response = client.get(
            reverse('GetPipelineHealthReport'),
            {'connection_id': '1', 'pipeline': 'main'}
        )

    assert response.status_code == 200
    assert response.json() == health_doc


@pytest.mark.django_db
def test_monitoring_view_exception_path(client, django_user_model):
    """If check_for_monitoring_indices raises, the Monitoring view still returns 200"""
    user = django_user_model.objects.create_user(username='excuser', password='testpass')
    client.force_login(user)

    with patch('Monitoring.views.get_elastic_connections_from_list', return_value=[]), \
         patch('Monitoring.views.check_for_monitoring_indices',
               side_effect=Exception("ES down")):
        response = client.get(reverse('monitoring'))

    # The exception is caught internally — should not result in a 500 to the user
    assert response.status_code == 200
    # monitoring_indices key should be absent from context (exception prevented it)
    assert 'monitoring_indices' not in response.context
