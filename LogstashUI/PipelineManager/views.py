
# Django
from django.shortcuts import render, redirect
from django.http import HttpResponse

## Forms
from .forms import ConnectionForm # Lives here because UI will only be here

## Tables
from Core.models import Connection as ConnectionTable
from Core.views import get_elastic_connection, get_logstash_pipeline

from API import logstash_config_parse
import json
import os



def _load_plugin_data():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(app_dir, 'data', 'plugins.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def PipelineGraph(request):
    context = {
        "plugin_data": _load_plugin_data()
    }

    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")

        es = get_elastic_connection(es_id)
        pipeline_doc = es.logstash.get_pipeline(id=pipeline_name)[pipeline_name]


        context['pipeline_text'] = pipeline_doc['pipeline']
        context['pipeline_name'] = pipeline_name

        try:
            parsed_config = logstash_config_parse.logstash_config_to_components(pipeline_doc['pipeline'])
        except:
            parsed_config = {
                "input": [],
                "filter": [],
                "output": []
            }
        context['component_data'] = parsed_config
    return render(request, "pipeline_graph.html", context=context)


def PipelineEditor(request):
    context = {
        "plugin_data": _load_plugin_data()
    }

    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")


        context['pipeline_text'] = get_logstash_pipeline(es_id, pipeline_name)
        context['pipeline_name'] = pipeline_name

        try:
            parsed_config = logstash_config_parse.logstash_config_to_components(context['pipeline_text'])
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

                if form.is_valid():
                    form.save()
                else:
                    raise Exception(form.errors)

                # TODO: Move this into an HTML file
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
