
# Django
from django.shortcuts import render, redirect
from django.http import HttpResponse

## Forms
from .forms import ConnectionForm # Lives here because UI will only be here

## Tables
from Core.models import Connection as ConnectionTable
from Core.views import get_elastic_connection

from API import logstash_config_parse
import json
import os



def _load_plugin_data():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(app_dir, 'data', 'plugins.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def PipelineEditor(request):
    context = {
        "plugin_data": _load_plugin_data()
    }

    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")

        es = get_elastic_connection(es_id)
        pipeline_doc = es.get(index=".logstash", id=pipeline_name)


        context['pipeline_text'] = pipeline_doc['_source']['pipeline']

        try:
            parsed_config = logstash_config_parse.logstash_config_to_components(pipeline_doc['_source']['pipeline'])
        except:
            parsed_config = {
                "input": [],
                "filter": [],
                "output": []
            }
        context['component_data'] = parsed_config
    return render(request, "pipeline_editor.html", context=context)

# Builds the table of pipelines
def PipelineManager(request):

    context = {}
    if request.method == "POST":
        try:
            is_htmx = request.headers.get('HX-Request') == 'true'

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



            return


    context['connections'] = ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk")

    context['form'] = ConnectionForm()

    return render(request, "pipeline_manager.html", context=context)


def PipelineManagerOLD(request):

    context = {}
    logstash_pipelines = []

    for connection in ConnectionTable.objects.all():

        if connection.connection_type == "CENTRALIZED":
            es = get_elastic_connection(connection.id)
            pipelines = es.search(index=".logstash", size=2000)
            for pipeline in pipelines['hits']['hits']:
                logstash_pipelines.append(
                    {
                        "es_id": connection.id,
                        "es_name": connection.name,
                        "name": pipeline['_id']
                    }
                )

    context['pipelines'] = logstash_pipelines

    return render(request, "pipelines.html", context = context)


#TODO: Implement ssh connection

# Allows users to manage connections to Elastic
def Logstash(request):

    context = {}
    if request.method == "POST":
        try:
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



            return


    context['connections'] = ConnectionTable.objects.all()
    context['form'] = ConnectionForm()

    return render(request, "connections.html", context=context)
