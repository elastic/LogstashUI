#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
URL configuration for logstashui project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


# Custom error handlers
handler400 = 'Common.error_handlers.handler400'
handler403 = 'Common.error_handlers.handler403'
handler404 = 'Common.error_handlers.handler404'
handler500 = 'Common.error_handlers.handler500'

def crash(request):
    raise Exception("Test Exception")

urlpatterns = [
    path('ConnectionManager/', include('PipelineManager.urls')),
    path('Management/', include('Management.urls')),
    path('Utilities/', include('Utilities.urls')),
    path('SNMP/', include('SNMP.urls')),
    path('Monitoring/', include('Monitoring.urls')),
    path('', include('Site.urls')),
    path('Documentation/', include("Documentation.urls")),
    #path('Crash', crash)
]




if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]

    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")