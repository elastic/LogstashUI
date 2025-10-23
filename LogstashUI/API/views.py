
# Django
from django.shortcuts import render, HttpResponse
from django.http import JsonResponse

## Tables
from Core.models import Connection as ConnectionTable
from Core.views import get_elastic_connection, test_elastic_connectivity, get_logstash_pipeline

# Custom libraries
from . import logstash_config_parse
from . import logstash_metrics

# General libraries
import json
import os
import subprocess
import tempfile
from deepdiff import DeepDiff
from PipelineManager.forms import ConnectionForm


from django.template.loader import get_template

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

def AddConnection(request):

    if request.method == "POST":
        form = ConnectionForm(request.POST)
        if form.is_valid():
            form.save()
        else:
            raise Exception(form.errors)

    return HttpResponse("""
        <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
            Connection created successfully!
            <script>
                // Close the flyout after a short delay
                setTimeout(() => {
                    const flyout = document.getElementById('connectionFormFlyout');
                    if (flyout) {
                        flyout.classList.add('hidden');
                    }
                    // Reload the page to show the new connection
                    window.location.reload();
                }, 100000);
            </script>
        </div>
    """)

def DeleteConnection(request, connection_id=None):

    print(connection_id, "MUAH")
    if connection_id:
        ConnectionTable.objects.filter(id=connection_id).delete()

    return HttpResponse("Connection deleted successfully!")

def GetLogstashCode(request, components={}):

    if not components:
        data = json.loads(request.POST.get("components"))
    else:
        data = components
    parser = logstash_config_parse.ComponentToPipeline(data)
    config = parser.components_to_logstash_config()
    #print(config)
    
    # Return the code wrapped in a pre tag with proper formatting
    return HttpResponse(
        f'<pre class="bg-gray-900 text-green-400 p-4 rounded overflow-auto"><code class="language-ruby">{config}</code></pre>',
        content_type="text/html"
    )

def SavePipeline(request):
    data = json.loads(request.POST.get("components"))
    if "save_pipeline" in request.POST:
        pipeline_name = request.POST.get("pipeline")
        parser = logstash_config_parse.ComponentToPipeline(data)
        config = parser.components_to_logstash_config()
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


def GetDiff(request):
    """Generate a unified diff between current and new pipeline configurations"""
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        pipeline_name = request.POST.get("pipeline")
        components_json = request.POST.get("components")
        
        if not es_id or not pipeline_name or not components_json:
            return JsonResponse({"error": "Missing required parameters"}, status=400)
        
        try:
            # Get the current pipeline from Elasticsearch
            current_pipeline = get_logstash_pipeline(es_id, pipeline_name)
            
            # Generate the new pipeline from components
            components = json.loads(components_json)
            parser = logstash_config_parse.ComponentToPipeline(components)
            new_pipeline = parser.components_to_logstash_config()
            
            # Generate unified diff
            import difflib
            diff = difflib.unified_diff(
                current_pipeline.splitlines(keepends=True),
                new_pipeline.splitlines(keepends=True),
                fromfile='Current Pipeline',
                tofile='New Pipeline (After Save)',
                lineterm=''
            )
            
            # Convert to string
            diff_text = ''.join(diff)
            
            # Calculate stats
            current_lines = len(current_pipeline.splitlines())
            new_lines = len(new_pipeline.splitlines())
            line_diff = new_lines - current_lines
            diff_sign = '+' if line_diff > 0 else ''
            stats = f"Current: {current_lines} lines | New: {new_lines} lines ({diff_sign}{line_diff})"
            
            return JsonResponse({
                'diff': diff_text,
                'stats': stats,
                'current': current_pipeline,
                'new': new_pipeline
            })
            
        except Exception as e:
            return JsonResponse({"error": f"Error generating diff: {str(e)}"}, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)


def GetPipelines(request, connection_id):
    context = {}
    connection = ConnectionTable.objects.get(pk=connection_id)

    logstash_pipelines = []
    if connection.connection_type == "CENTRALIZED":
        # --- Gets our pipelines from the connection
        es = get_elastic_connection(connection.id)
        pipelines = es.logstash.get_pipeline()
        for pipeline in pipelines:
            logstash_pipelines.append(
                {
                    "es_id": connection.id,
                    "es_name": connection.name,
                    "name": pipeline
                }
            )

        context['instances'] = logstash_metrics.get_instances_centralized(es)




    context['pipelines'] = logstash_pipelines
    # --- Gets monitoring data from the connection
    context['instances'] = logstash_metrics.get_instances_centralized(es)

    logstash_template = get_template("components/pipeline_manager/collapsible_row.html")
    html = logstash_template.render(context)
    return HttpResponse(html)