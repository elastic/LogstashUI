
# Django
from django.shortcuts import render

## Tables
from Core.models import Connection as ConnectionTable

## General libraries
from elasticsearch import Elasticsearch
import json

def Home(request):
    return render(request, "home.html")



def test_elastic_connectivity(elastic_connection):
    return json.dumps(dict(elastic_connection.info()), indent=4)

# TODO: Make storing of credentials.. well.. actually secure.
def _get_creds(connection_id):

    connection = ConnectionTable.objects.get(id=connection_id)
    connection_data = {}

    if connection.cloud_id:
        connection_data['cloud_id'] = connection.cloud_id
    else:
        connection_data['host'] = connection.url

    if connection.api_key:
        connection_data['api_key'] = connection.api_key
    else:
        connection_data['http_auth'] = (connection.username, connection.password)

    return connection_data


# TODO: Expand this to include SSH connection to a logstash node
def get_elastic_connection(connection_id):
    elastic_creds = _get_creds(connection_id)
    return Elasticsearch(**elastic_creds)
