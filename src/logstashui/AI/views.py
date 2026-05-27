#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from PipelineManager.models import Connection

def IntegrationFactory(request):
    connections = Connection.objects.filter(
        connection_type=Connection.ConnectionType.CENTRALIZED
    ).values('id', 'name')
    
    return render(request, 'integration_factory.html', {
        'connections': connections
    })
