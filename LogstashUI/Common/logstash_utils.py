"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

from Common.elastic_utils import get_elastic_connection

import logging

logger = logging.getLogger(__name__)



def get_logstash_pipeline(es_id, pipeline_name):
    try:
        es = get_elastic_connection(es_id)
        pipeline_doc = es.logstash.get_pipeline(id=pipeline_name)[pipeline_name]
        return pipeline_doc
    except KeyError:
        logger.error(f"Pipeline '{pipeline_name}' not found in Elasticsearch connection {es_id}")
        return None
    except Exception as e:
        logger.error(f"Error fetching pipeline '{pipeline_name}' from connection {es_id}: {e}")
        return None
