
# Django
from django.shortcuts import render


## Tables
from Core.models import Connection as ConnectionTable

## General libraries
from elasticsearch import Elasticsearch
import json


## Project
from Core import logstash_metrics






def Home(request):
    connections = list(ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk"))

    context = {
        "Connections": connections,
        "has_connections": len(connections) > 0
    }

    context['monitoring_indices'] = logstash_metrics.check_for_monitoring_indices(
        [{
            "es": get_elastic_connection(connection_id['pk']),
            "name": connection_id['name']
        } for connection_id in context['Connections']]
    )

    # List out all of the monitoring indices

    print(context['monitoring_indices'])


    return render(request, "home.html", context=context)



def get_logstash_pipeline(es_id, pipeline_name):
    es = get_elastic_connection(es_id)
    pipeline_doc = es.logstash.get_pipeline(id=pipeline_name)[pipeline_name]
    return pipeline_doc



def test_elastic_connectivity(elastic_connection):
    return json.dumps(dict(elastic_connection.info()), indent=4)

def _get_creds(connection_id):

    connection = ConnectionTable.objects.get(id=connection_id)
    connection_data = {}

    if connection.cloud_id:
        connection_data['cloud_id'] = connection.cloud_id
    else:
        connection_data['hosts'] = connection.host

    if connection.api_key:
        connection_data['api_key'] = connection.api_key
    else:
        connection_data['http_auth'] = (connection.username, connection.password)

    return connection_data


def get_elastic_connection(connection_id):
    elastic_creds = _get_creds(connection_id)
    return Elasticsearch(**elastic_creds)
