from django.shortcuts import render, redirect
from . import models
from .forms import ConnectionForm
# Create your views here.
from elasticsearch import Elasticsearch

def PipelineManager(request):
    return render(request, "pipelines.html")


from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import render_to_string


def Logstash(request):
    if request.method == "POST":
        try:
            print("Form data:", request.POST)  # Debug print
            # Process form data and save
            # connection = Connection.objects.create(...)

            # Check if it's an HTMX request
            is_htmx = request.headers.get('HX-Request') == 'true'
            print(f"Is HTMX request: {is_htmx}")

            if is_htmx:
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
            return redirect('logstash')

        except Exception as e:
            error_message = f"Error: {str(e)}"
            if request.headers.get('HX-Request') == 'true':
                return HttpResponse(f"""
                    <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
                        {error_message}
                    </div>
                """, status=400)
            messages.error(request, error_message)
            return redirect('logstash')

    connections = models.Connection.objects.all()
    return render(request, "connections.html", context={"connections": connections, "form": ConnectionForm()})
