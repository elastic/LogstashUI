#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Root URLconf for LogstashUI.

Mounts app URLconfs and the public product CA at
``/.well-known/logstashui/ca.crt`` so agents can fetch it without auth.
"""

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from Site import product_ca_views


# Custom error handlers
handler400 = 'Common.error_handlers.handler400'
handler403 = 'Common.error_handlers.handler403'
handler404 = 'Common.error_handlers.handler404'
handler500 = 'Common.error_handlers.handler500'

def crash(request):
    """Raise a test exception (deliberate debug view)."""
    raise Exception("Test Exception")

urlpatterns = [
    # Must be public and at site root for agents: {ui_url}/.well-known/logstashui/ca.crt
    path(
        '.well-known/logstashui/ca.crt',
        product_ca_views.product_ca_crt,
        name='product_ca_crt_root',
    ),
    path('ConnectionManager/', include('PipelineManager.urls')),
    path('Management/', include('Management.urls')),
    path('Utilities/', include('Utilities.urls')),
    path('SNMP/', include('SNMP.urls')),
    path('Monitoring/', include('Monitoring.urls')),
    path('', include('Site.urls')),
    path('Documentation/', include("Documentation.urls")),

    path('AI/', include ("AI.urls"))
    #path('Crash', crash)
]




if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]

    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")