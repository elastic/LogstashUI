from Core.views import get_elastic_connection




def _get_device_metrics(device, es_connection):

    results = es_connection.search(
        size=1000,
        sort=[{"@timestamp": {"order": "desc"}}],
        query = {

            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
                    {
                        "term": {
                            "event.kind": "metrics"
                        }
                    }
                ]
            }
        }
    )

    visualization_data = {
        "Uptime": 0,
        "CPU": [],
        "Memory": [],
        "Time": []
    }

    for result in results['hits']['hits']:
        visualization_data['CPU'].append(result['_source']['system']['cpu']['total']['norm']['pct'])
        visualization_data['Memory'].append(result['_source']['system']['memory']['actual']['used']['pct'])
        visualization_data['Time'].append(result['_source']['@timestamp'])


    try:
        visualization_data['Uptime'] = results['hits']['hits'][0]['_source']['host']['uptime']
    except:
        visualization_data['Uptime'] = 0

    return visualization_data

def _get_device_fans(device, es_connection):
    results = es_connection.search(
        size=0,
        sort=[{"@timestamp": {"order": "desc"}}],
        query = {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
                    {
                        "term": {
                            "event.kind": "fans"
                        }
                    }
                ]
            }
        },
        aggregations = {
            "fans": {
                "terms": {
                    "field": "table.description",
                    "size": 1000
                },
                "aggregations": {
                    "top_fan_doc": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["table.state", "table.description"]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "fans": []
    }

    for fan in results['aggregations']['fans']['buckets']:
        for doc in fan['top_fan_doc']['hits']['hits']:
            visualization_data['fans'].append(doc['_source']['table'])

    return visualization_data

def _get_device_sensors(device, es_connection):
    results = es_connection.search(
        size=0,
        sort=[{"@timestamp": {"order": "desc"}}],
        query = {

            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
                    {
                        "term": {
                            "event.kind": "sensors"
                        }
                    }
                ]
            }
        },
        aggregations = {
            "sensors": {
                "terms": {
                    "field": "table.description",
                    "size": 1000
                },
                "aggregations": {
                    "top_sensor_doc": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["table.state", "table.description", "table.temp_celsius", "table.temp_threshold"]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "sensors": []
    }


    for sensor in results['aggregations']['sensors']['buckets']:
        for doc in sensor['top_sensor_doc']['hits']['hits']:
            visualization_data['sensors'].append(doc['_source']['table'])

    return visualization_data

def generate_visualizations(visualizations, device, es_connection):
    """
    Generate visualization data based on the decided visualizations.
    """
    visualization_data = {}

    if "metrics" in visualizations:
        visualization_data['metrics'] = _get_device_metrics(device, es_connection)
    if "sensors" in visualizations:
        visualization_data['sensors'] = _get_device_sensors(device, es_connection)
    if "fans" in visualizations:
        visualization_data['fans'] = _get_device_fans(device, es_connection)

    return visualization_data


def get_visualizations(device):
    """
    Main entry point to get visualizations for a device.
    Gets the Elasticsearch connection from the device's network and fetches visualization data.
    """
    # Get the connection from the device's network
    if not device.network or not device.network.connection:
        return {
            'success': False,
            'error': 'Device has no network or network has no connection configured'
        }
    
    connection_id = device.network.connection.id
    es = get_elastic_connection(connection_id)
    
    # Decide what visualizations to show and fetch the data
    visualizations = decide_visualizations(device, es)
    return generate_visualizations(visualizations['results'], device, es)


def decide_visualizations(device, es):
    """
    Determine which visualizations to show for SNMP devices based on available data.
    Queries Elasticsearch to see what data is available for this device.
    Returns a dict with visualization configuration and query results.
    """
    try:
        results = es.search(
            index="metrics-snmp-*",
            size=0,
            query={
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": "now-6h"
                                }
                            }
                        },
                        {
                            "term": {
                                "host.hostname": device.ip_address
                            }
                        }
                    ]
                }
            },
            aggregations={
                "data_kinds": {
                    "terms": {
                        "field": "event.kind",
                        "size": 20
                    }
                }
            }
        )

        data_types = [result['key'] for result in results['aggregations']['data_kinds']['buckets']]
        
        return {
            'success': True,
            'results': data_types
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'has_data': False
        }
