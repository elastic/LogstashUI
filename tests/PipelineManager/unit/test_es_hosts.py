#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import importlib
from unittest.mock import MagicMock

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.http import QueryDict

from Common.elastic_utils import _get_creds
from Common.encryption import encrypt_credential
from PipelineManager.forms import ConnectionForm, normalize_es_host
from PipelineManager.models import Connection
from SNMP.snmp_pipeline_generator import _generate_output

backfill = importlib.import_module('PipelineManager.migrations.0035_connection_es_hosts_backfill')


class TestNormalizeEsHost:

    @pytest.mark.parametrize('url, port, expected', [
        ('https://es1.lab:9200', None, 'https://es1.lab:9200'),
        ('https://es1.lab', '9243', 'https://es1.lab:9243'),
        ('https://es1.lab', None, 'https://es1.lab:443'),
        ('http://es1.lab/', '', 'http://es1.lab:80'),
        ('  HTTPS://es1.lab:9200/  ', None, 'https://es1.lab:9200'),
        ('https://proxy.lab/es', '8443', 'https://proxy.lab:8443/es'),
        ('https://es1.lab:9200', 9200, 'https://es1.lab:9200'),
    ])
    def test_normalizes(self, url, port, expected):
        assert normalize_es_host(url, port) == expected

    @pytest.mark.parametrize('url, port', [
        ('es1.lab:9200', None),
        ('ftp://es1.lab', None),
        ('https://es1.lab', 'abc'),
        ('https://es1.lab', '70000'),
        ('https://es1.lab:9200', '9243'),
    ])
    def test_rejects(self, url, port):
        with pytest.raises(ValidationError):
            normalize_es_host(url, port)


def _form(rows=None, instance=None, **extra):
    data = QueryDict(mutable=True)
    data.update({
        'name': 'Multi', 'connection_type': 'CENTRALIZED', 'connection_mode': 'url',
        'auth_type': 'basic', 'username': 'elastic', 'password': 'changeme',
    })
    for url, port in rows or []:
        data.appendlist('es_host_url', url)
        data.appendlist('es_host_port', port)
    for key, value in extra.items():
        data[key] = value
    return ConnectionForm(data, instance=instance)


@pytest.mark.django_db
class TestConnectionFormHosts:

    def test_rows_saved_in_order_with_defaults(self):
        form = _form([('https://es2.lab', '9200'), ('https://es1.lab:9243', ''), ('https://es3.lab', '')])
        assert form.is_valid(), form.errors
        conn = form.save()
        conn.refresh_from_db()
        assert conn.es_hosts == ['https://es2.lab:9200', 'https://es1.lab:9243', 'https://es3.lab:443']
        assert (conn.host, conn.port) == ('https://es2.lab', 9200)

    def test_blank_rows_ignored_and_duplicates_dropped(self):
        form = _form([('https://es1.lab', '9200'), ('', ''), ('https://es1.lab:9200', '')])
        assert form.is_valid(), form.errors
        assert form.cleaned_data['es_hosts'] == ['https://es1.lab:9200']

    def test_mixed_schemes_rejected(self):
        form = _form([('https://es1.lab', '9200'), ('http://es2.lab', '9200')])
        assert not form.is_valid()
        assert 'same scheme' in str(form.errors)

    def test_no_hosts_rejected(self):
        form = _form([('', '')])
        assert not form.is_valid()
        assert 'At least one Elasticsearch node URL' in str(form.errors)

    def test_bad_port_rejected(self):
        form = _form([('https://es1.lab', '99999')])
        assert not form.is_valid()

    def test_json_es_hosts(self):
        form = _form(es_hosts='["https://es1.lab:9200", "https://es2.lab"]')
        assert form.is_valid(), form.errors
        assert form.cleaned_data['es_hosts'] == ['https://es1.lab:9200', 'https://es2.lab:443']

    def test_comma_separated_es_hosts(self):
        form = _form(es_hosts='https://es1.lab:9200, https://es2.lab:9200')
        assert form.is_valid(), form.errors
        assert form.cleaned_data['es_hosts'] == ['https://es1.lab:9200', 'https://es2.lab:9200']

    def test_legacy_host_and_port_map_to_one_node(self):
        form = _form(host='https://es1.lab', port='9243')
        assert form.is_valid(), form.errors
        assert form.cleaned_data['es_hosts'] == ['https://es1.lab:9243']

    def test_cloud_mode_clears_hosts(self):
        form = _form([('https://es1.lab', '9200')], connection_mode='cloud', cloud_id='dep:abc')
        assert form.is_valid(), form.errors
        assert form.cleaned_data['es_hosts'] == []

    @pytest.mark.parametrize('raw, expected', [
        ('https://kibana.lab:5601/app/home#/', 'https://kibana.lab:5601'),
        ('', None),
    ])
    def test_kibana_url_normalized(self, raw, expected):
        form = _form([('https://es1.lab', '9200')], kibana_url=raw)
        assert form.is_valid(), form.errors
        assert form.save().kibana_url == expected

    def test_kibana_url_bad_scheme_rejected(self):
        form = _form([('https://es1.lab', '9200')], kibana_url='ftp://kibana.lab')
        assert not form.is_valid()


@pytest.mark.django_db
class TestConnectionModel:

    def test_get_es_hosts_drops_blank_and_non_strings(self):
        assert Connection(es_hosts=['https://a:1', '', '  ', None, 5]).get_es_hosts() == ['https://a:1']
        assert Connection(es_hosts=None).get_es_hosts() == []

    def test_legacy_create_backfills_hosts(self):
        conn = Connection.objects.create(name='Legacy', connection_type='CENTRALIZED',
                                         host='https://es.lab', port=9200, username='e', password='p')
        assert conn.es_hosts == ['https://es.lab:9200']

    def test_requires_cloud_id_or_hosts(self):
        with pytest.raises(ValidationError):
            Connection.objects.create(name='Empty', connection_type='CENTRALIZED', username='e', password='p')

    def test_cloud_id_ignores_stored_hosts(self):
        conn = Connection(cloud_id='dep:abc', es_hosts=['https://es1:9200'])
        assert conn.get_es_hosts() == []

    def test_cloud_only_clears_legacy_host(self):
        conn = Connection.objects.create(name='Cloud', connection_type='CENTRALIZED',
                                         cloud_id='dep:abc', api_key='k')
        assert (conn.host or '', conn.port) == ('', None)


def _network(connection):
    net = MagicMock()
    net.id = 1
    net.connection = connection
    net.namespace = 'default'
    net.deployment_mode = 'CENTRALIZED'
    net.credential_mode = 'KEYSTORE'
    net.ssl_certificate_authorities = ''
    return net


def test_generator_emits_every_host_in_order():
    conn = Connection(id=7, connection_type='CENTRALIZED', username='elastic', password='x',
                      es_hosts=['https://es3:9200', 'https://es1:9200', 'https://es2:9200'])
    cfg = _generate_output(_network(conn))[0]['config']
    assert cfg['hosts'] == ['https://es3:9200', 'https://es1:9200', 'https://es2:9200']


def test_generator_cloud_id_wins_over_hosts():
    conn = Connection(id=7, connection_type='CENTRALIZED', cloud_id='dep:abc', api_key='k',
                      es_hosts=['https://es1:9200'])
    cfg = _generate_output(_network(conn))[0]['config']
    assert cfg['cloud_id'] == 'dep:abc' and 'hosts' not in cfg


LEGACY_ROWS = [
    # (host, port, cloud_id, connection_type, expected es_hosts after forwards)
    ('https://es.lab', 9200, None, 'CENTRALIZED', ['https://es.lab:9200']),
    ('https://es.lab:9243', None, None, 'CENTRALIZED', ['https://es.lab:9243']),
    ('http://es.lab', None, None, 'CENTRALIZED', ['http://es.lab']),
    ('es.lab', 9200, None, 'CENTRALIZED', ['es.lab:9200']),
    ('https://proxy.lab/es', None, None, 'CENTRALIZED', ['https://proxy.lab/es']),
    ('', None, 'dep:abc', 'CENTRALIZED', []),
    ('https://leftover.lab', 9200, 'dep:abc', 'CENTRALIZED', []),
    ('https://agent.lab', 9600, None, 'AGENT', []),
]


@pytest.mark.django_db
class TestBackfillMigration:

    def _rows(self):
        password = encrypt_credential('x')
        objs = [
            Connection(name=f'row{i}', host=host, port=port, cloud_id=cloud_id,
                       connection_type=ctype, username='elastic', password=password, es_hosts=[])
            for i, (host, port, cloud_id, ctype, _) in enumerate(LEGACY_ROWS)
        ]
        # bulk_create skips save(), so rows look exactly like pre-migration data.
        Connection.objects.bulk_create(objs)
        return list(Connection.objects.filter(name__startswith='row').order_by('name'))

    def test_forwards_copies_host_verbatim(self):
        self._rows()
        backfill.forwards(django_apps, None)
        for i, (*_, expected) in enumerate(LEGACY_ROWS):
            assert Connection.objects.get(name=f'row{i}').es_hosts == expected

    def test_forwards_keeps_existing_hosts(self):
        Connection.objects.bulk_create([Connection(
            name='set', connection_type='CENTRALIZED', host='https://old', port=9200,
            es_hosts=['https://new:9200', 'https://new2:9200'])])
        backfill.forwards(django_apps, None)
        assert Connection.objects.get(name='set').es_hosts == ['https://new:9200', 'https://new2:9200']

    def test_dialled_hosts_and_generated_output_unchanged(self):
        """Before: one ``host:port`` string. After: that same string as the only node."""
        rows = [r for r in self._rows() if r.connection_type == 'CENTRALIZED' and r.host and not r.cloud_id]
        before = {r.pk: (f'{r.host}:{r.port}' if r.port else r.host) for r in rows}
        backfill.forwards(django_apps, None)
        for pk, legacy in before.items():
            creds, conn = _get_creds(pk)
            assert creds['hosts'] == [legacy]
            assert _generate_output(_network(conn))[0]['config']['hosts'] == [legacy]

    def test_backwards_restores_untouched_rows_exactly(self):
        original = {r.name: (r.host, r.port) for r in self._rows()}
        backfill.forwards(django_apps, None)
        backfill.backwards(django_apps, None)
        for name, values in original.items():
            conn = Connection.objects.get(name=name)
            assert (conn.host, conn.port) == values

    def test_backwards_takes_first_node_after_edit(self):
        self._rows()
        backfill.forwards(django_apps, None)
        Connection.objects.filter(name='row0').update(es_hosts=['https://other.lab:9300', 'https://b:9300'])
        Connection.objects.filter(name='row4').update(es_hosts=['https://proxy2.lab/es'])
        backfill.backwards(django_apps, None)
        assert (lambda c: (c.host, c.port))(Connection.objects.get(name='row0')) == ('https://other.lab', 9300)
        assert (lambda c: (c.host, c.port))(Connection.objects.get(name='row4')) == ('https://proxy2.lab/es', None)
