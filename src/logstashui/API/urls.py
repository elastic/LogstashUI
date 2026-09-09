#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""URL configuration for the REST API."""

from django.urls import path
from API import views

urlpatterns = [
    path('connections/', views.connection_list, name='api-connections-list'),
    path('connections/<int:connection_id>/', views.connection_detail, name='api-connections-detail'),
]
