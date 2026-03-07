#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import path
from . import views

urlpatterns = [
    path('', views.Monitoring, name='monitoring'),

    # Metrics endpoints
    path("GetNodeMetrics", views.GetNodeMetrics, name="GetNodeMetrics"),
    path("GetPipelineMetrics", views.GetPipelineMetrics, name="GetPipelineMetrics"),
    path("GetLogs", views.GetLogs, name="GetLogs"),
    path("GetPipelineHealthReport", views.GetPipelineHealthReport, name="GetPipelineHealthReport"),
]