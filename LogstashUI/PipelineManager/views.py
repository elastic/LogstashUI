from django.shortcuts import render, redirect
from . import models
from .forms import ConnectionForm
# Create your views here.
from elasticsearch import Elasticsearch
from django.http import HttpResponse
import json



import os
from django.conf import settings

def load_plugin_data():
    # Get the base directory of the project
    app_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the path to the JSON file
    json_path = os.path.join(app_dir, 'data', 'plugins.json')

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Transform the data to match the expected format in the template
    transformed = {
        'input': {},
        'filter': {},
        'output': {}
    }
    
    # Process each plugin type
    for plugin_type in ['input', 'filter', 'output']:
        if plugin_type in data:
            for plugin_name, plugin_data in data[plugin_type].items():
                transformed[plugin_type][plugin_name] = {
                    'name': plugin_data.get('name', plugin_name),
                    'version': plugin_data.get('version', ''),
                    'description': f"{plugin_name} plugin (v{plugin_data.get('version', '?')})",
                    'params': plugin_data.get('params', {}),
                    'link': f"/guide/en/logstash/current/plugins-{plugin_type}s-{plugin_name}.html",
                    'repo_link': f"https://github.com/logstash-plugins/logstash-{plugin_type}-{plugin_name}"
                }
    
    return transformed

# Load plugin data once when the module is imported
plugin_data = load_plugin_data()

def PipelineEditor(request):
    context = {
        "plugin_data": plugin_data
    }
    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")


        es = Elasticsearch(**_get_elastic_creds(es_id))
        pipeline_doc = es.get(index=".logstash", id=pipeline_name)


        context['pipeline_text'] = pipeline_doc['_source']['pipeline']
        print(pipeline_doc)




    return render(request, "pipeline_editor.html", context=context)

def PipelineManager(request):

    logstash_pipelines = []

    for connection in models.Connection.objects.all():

        if connection.connection_type == "CENTRALIZED":
            es = Elasticsearch(**_get_elastic_creds(connection.id))
            pipelines = es.search(index=".logstash", size=2000)
            for pipeline in pipelines['hits']['hits']:
                logstash_pipelines.append(
                    {
                        "es_id": connection.id,
                        "es_name": connection.name,
                        "name": pipeline['_id']
                    }
                )
            # TODO: Allow editing of Logstash metadata too




    return render(request, "pipelines.html", context = {"pipelines": logstash_pipelines})


def _get_elastic_creds(connection_id):

    connection = models.Connection.objects.get(id=connection_id)
    connection_data = {}

    if connection.cloud_id:
        connection_data['cloud_id'] = connection.cloud_id
    else:
        connection_data['host'] = connection.url

    if connection.api_key:
        connection_data['api_key'] = connection.api_key
    else:
        connection_data['username'] = connection.username
        connection_data['password'] = connection.password

    return connection_data


def test_elastic_connectivity(connection_id):
    elastic_creds = _get_elastic_creds(connection_id)
    es = Elasticsearch(**elastic_creds)
    es_info = json.dumps(dict(es.info()), indent=4)
    return es_info

#TODO: Implement ssh connection
#TODO: Change naming of connections
def Logstash(request):
    if request.method == "POST":
        try:
            print("Form data:", request.POST)  # Debug print

            is_htmx = request.headers.get('HX-Request') == 'true'
            print(f"Is HTMX request: {is_htmx}")

            if is_htmx:

                form = ConnectionForm(request.POST)

                print("----")
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
        except Exception as e:
            error_message = f"Error: {str(e)}"
            if request.headers.get('HX-Request') == 'true':
                return HttpResponse(f"""
                    <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
                        {error_message}
                    </div>
                """, status=400)

            return redirect('logstash')


    if request.method == "GET":

        delete_id = request.GET.get('delete_id')
        if request.GET.get('delete_id'):
            models.Connection.objects.filter(id=delete_id).delete()
            return

        test_id = request.GET.get('test')
        if request.GET.get("test"):
            return HttpResponse("""
                <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg"
                    onload="setTimeout(() => this.remove(), 3000);">
                    <p>{0}</p>
                </div>
            """.format(test_elastic_connectivity(test_id)))
            return test_elastic_connectivity(test_id)


    connections = models.Connection.objects.all()

    #print(connections, "ME")
    for connection in connections:
        print(connection, dir(connection))
    return render(request, "connections.html", context={"connections": connections, "form": ConnectionForm()})
