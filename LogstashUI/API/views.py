
# Django
from django.shortcuts import render, HttpResponse
from django.http import JsonResponse

## Tables
from Core.models import Connection as ConnectionTable
from Core.views import get_elastic_connection, test_elastic_connectivity

# Custom libraries
from . import logstash_config_parse

# General libraries
import json
import os
import subprocess
import tempfile
from deepdiff import DeepDiff

from django.conf import settings

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

def SimulatePipeline(request):
    components = request.POST.get("components")
    data = json.loads(components)
    input_json = json.loads(request.POST.get("log_text"))

    # 1. Generate the Logstash config
    config_str = logstash_config_parse.components_to_logstash_config({"components": data}, test=True)


    print(config_str)
    # 2. Write config to a temp file
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as tmp:
        tmp.write(config_str)
        tmp_path = tmp.name

    container_conf = "/usr/share/logstash/pipeline/simulate.conf"

    # 3. Spin up logstash container with the config
    cmd = [
        "docker", "run", "--rm", "-i",
        "-v", f"{tmp_path}:{container_conf}:ro",
        "docker.elastic.co/logstash/logstash:9.1.4",
        "-f", container_conf,
        "--pipeline.ecs_compatibility=disabled"
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    while True:
        line = proc.stdout.readline()
        print(line)
        if not line:
            break
        if "Pipelines running" in line:
            ready = True
            break

    filter_counter = 0
    test_results = {}
    for test_filter in range(0, len(json.loads(components)['filter'])):
        print("HERE", filter_counter)
        input_json['plugin_num'] = filter_counter
        proc.stdin.write(json.dumps(input_json)+"\n")
        proc.stdin.flush()

        out = proc.stdout.readline()
        print(out)

        test_results[filter_counter] = {
            "Result": json.loads(out),
            "Action": json.loads(components)['filter'][test_filter]['plugin'] + " / " + json.loads(components)['filter'][test_filter]['id']
        }


        filter_counter += 1

    # 5. Cleanup temp file
    os.remove(tmp_path)

    html_text = ""
    last_result = input_json
    for result in test_results:
        step = test_results[result]['Action']
        res = test_results[result]['Result']

        html_text += f"<h1>{step}</h1>"

        difference = DeepDiff(last_result, res).to_dict()


        html_text += f'''<textarea class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500" rows="10">

{json.dumps(res,indent=4)}

{difference}</textarea>'''
        last_result = res



    return HttpResponse(html_text)
