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
