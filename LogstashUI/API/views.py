
# Django
from django.shortcuts import render, HttpResponse

## Tables
from Core.models import Connection as ConnectionTable
from Core.views import get_elastic_connection, test_elastic_connectivity

# Custom libraries
from . import logstash_config_parse

# General libraries
import json

def TestConnectivity(request):
    test_id = request.GET.get('test')
    if request.GET.get("test"):

        elastic_connection = get_elastic_connection(test_id)

        return HttpResponse("""
            <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg"
                onload="setTimeout(() => this.remove(), 3000);">
                <p>{0}</p>
            </div>
        """.format(
            test_elastic_connectivity(elastic_connection))
        )

def DeleteConnection(request, connection_id=None):
    print("MADE IT")
    if connection_id:
        ConnectionTable.objects.filter(id=connection_id).delete()

    return HttpResponse("Connection deleted successfully!")


def GetLogstashCode(request):
    data = json.loads(request.POST.get("components"))
    config = logstash_config_parse.components_to_logstash_config(
        {
            "components": data
        }
    )
    
    # Return the code wrapped in a pre tag with proper formatting
    return HttpResponse(
        f'<pre class="bg-gray-900 text-green-400 p-4 rounded overflow-auto"><code class="language-ruby">{config}</code></pre>',
        content_type="text/html"
    )

def SavePipeline(request):
    data = json.loads(request.POST.get("components"))
    if "save_pipeline" in request.POST:
        pipeline_name = request.POST.get("pipeline")
        config = logstash_config_parse.components_to_logstash_config({"components": data})
        es = get_elastic_connection(request.POST.get("es_id"))
        current_pipeline_config = es.logstash.get_pipeline(id=pipeline_name)

        es.logstash.put_pipeline(id=pipeline_name, body={
            "pipeline": config,
            "last_modified": current_pipeline_config[pipeline_name]['last_modified'],
            "pipeline_metadata": current_pipeline_config[pipeline_name]['pipeline_metadata'],
            "username": "LogstashUI",
            "pipeline_settings": current_pipeline_config[pipeline_name]['pipeline_settings']}
        )

        return HttpResponse("Pipeline saved successfully!")