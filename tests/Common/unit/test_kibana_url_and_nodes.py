#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import base64
from unittest.mock import MagicMock, patch

import pytest
import requests

from Common.elastic_utils import (
    KibanaUrlMissing,
    _get_creds,
    check_elastic_nodes,
    check_kibana_status,
    connection_edit_url,
    get_kibana_url,
    kibana_url_from_cloud_id,
)
from PipelineManager.models import Connection


CLOUD_ID = "dep:" + base64.b64encode(b"us-east-1.aws.found.io$es1$kb1").decode()


def _conn(**kwargs):
    fields = {
        "name": "Multi",
        "connection_type": "CENTRALIZED",
        "es_hosts": ["https://es1:9200", "https://es2:9200"],
        "username": "elastic",
        "password": "changeme",
    }
    fields.update(kwargs)
    return Connection.objects.create(**fields)


@pytest.mark.django_db
class TestGetCredsHosts:

    def test_hosts_keep_order(self):
        conn = _conn(es_hosts=["https://b:9200", "https://a:9200", "https://c:9200"])
        creds, _ = _get_creds(conn.id)
        assert creds["hosts"] == ["https://b:9200", "https://a:9200", "https://c:9200"]

    def test_first_host_mirrors_to_legacy_fields(self):
        conn = _conn(es_hosts=["https://es1:9243", "https://es2:9243"])
        conn.refresh_from_db()
        assert (conn.host, conn.port) == ("https://es1", 9243)


@pytest.mark.django_db
class TestGetKibanaUrl:

    def test_saved_url_wins_over_cloud_id(self):
        conn = _conn(es_hosts=[], cloud_id=CLOUD_ID, kibana_url="https://kibana.internal:5601")
        assert get_kibana_url(conn.id) == "https://kibana.internal:5601"

    def test_saved_url_is_normalized(self):
        conn = _conn(kibana_url="https://kibana.internal:5601/app/home#/")
        assert get_kibana_url(conn.id) == "https://kibana.internal:5601"

    def test_cloud_id_fallback(self):
        conn = _conn(es_hosts=[], cloud_id=CLOUD_ID)
        assert get_kibana_url(conn.id) == "https://kb1.us-east-1.aws.found.io"

    def test_es_hosts_are_never_used(self):
        conn = _conn(es_hosts=["https://my-deploy.es.us-east-1.aws.found.io:443"])
        with pytest.raises(KibanaUrlMissing) as exc:
            get_kibana_url(conn.id)
        assert exc.value.connection_id == conn.id
        assert exc.value.edit_url == f"/ConnectionManager/?edit={conn.id}&focus=kibana_url"

    def test_missing_is_a_value_error(self):
        conn = _conn()
        with pytest.raises(ValueError, match="no Kibana URL"):
            get_kibana_url(conn.id)


class TestKibanaUrlFromCloudId:

    @pytest.mark.parametrize("cloud_id", [None, "", "no-colon", "dep:%%%not-base64", "dep:" + base64.b64encode(b"nodollar").decode()])
    def test_undecodable_returns_none(self, cloud_id):
        assert kibana_url_from_cloud_id(cloud_id) is None

    def test_without_kibana_uuid_uses_domain(self):
        cid = "dep:" + base64.b64encode(b"example.com$es1").decode()
        assert kibana_url_from_cloud_id(cid) == "https://example.com"


def test_connection_edit_url():
    assert connection_edit_url(3) == "/ConnectionManager/?edit=3&focus=kibana_url"
    assert connection_edit_url(3, focus="name") == "/ConnectionManager/?edit=3&focus=name"


@pytest.mark.django_db
class TestCheckElasticNodes:

    @patch("Common.elastic_utils.Elasticsearch")
    def test_each_node_checked_alone_in_order(self, mock_es):
        def build(**kwargs):
            client = MagicMock()
            if kwargs["hosts"] == ["https://es2:9200"]:
                client.info.side_effect = ConnectionError("refused")
            else:
                client.info.return_value = {"cluster_name": "c"}
            return client

        mock_es.side_effect = build
        conn = _conn(es_hosts=["https://es1:9200", "https://es2:9200", "https://es3:9200"])

        results = check_elastic_nodes(conn.id)

        assert [(h, ok) for h, ok, _ in results] == [
            ("https://es1:9200", True), ("https://es2:9200", False), ("https://es3:9200", True),
        ]
        assert results[1][2] == "refused"
        for call in mock_es.call_args_list:
            assert call.kwargs["max_retries"] == 0
            assert len(call.kwargs["hosts"]) == 1

    @patch("Common.elastic_utils.Elasticsearch")
    def test_cloud_id_checked_once(self, mock_es):
        mock_es.return_value.info.return_value = {"cluster_name": "c"}
        conn = _conn(es_hosts=[], cloud_id=CLOUD_ID)

        results = check_elastic_nodes(conn.id)

        assert len(results) == 1 and results[0][0] is None and results[0][1] is True
        assert "hosts" not in mock_es.call_args.kwargs
        assert mock_es.call_args.kwargs["cloud_id"] == CLOUD_ID


@pytest.mark.django_db
class TestCheckKibanaStatus:

    def test_no_saved_url_skips_check(self):
        conn = _conn(es_hosts=[], cloud_id=CLOUD_ID)
        with patch("Common.elastic_utils.requests.get") as mock_get:
            assert check_kibana_status(conn.id) is None
        mock_get.assert_not_called()

    def test_ok_returns_none_and_uses_basic_auth(self):
        conn = _conn(kibana_url="https://kb:5601", allow_self_signed_certs=True)
        with patch("Common.elastic_utils.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            assert check_kibana_status(conn.id) is None
        args, kwargs = mock_get.call_args
        assert args[0] == "https://kb:5601/api/status"
        assert kwargs["auth"] == ("elastic", "changeme")
        assert kwargs["verify"] is False

    def test_api_key_header(self):
        conn = _conn(kibana_url="https://kb:5601", api_key="secret-key")
        with patch("Common.elastic_utils.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            check_kibana_status(conn.id)
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "ApiKey secret-key"

    def test_http_error_is_warning(self):
        conn = _conn(kibana_url="https://kb:5601")
        with patch("Common.elastic_utils.requests.get") as mock_get:
            mock_get.return_value.status_code = 401
            assert check_kibana_status(conn.id) == "Kibana at https://kb:5601 returned HTTP 401 from /api/status."

    def test_unreachable_is_warning(self):
        conn = _conn(kibana_url="https://kb:5601")
        with patch("Common.elastic_utils.requests.get", side_effect=requests.ConnectionError("refused")):
            assert check_kibana_status(conn.id) == "Kibana at https://kb:5601 is unreachable: refused"
