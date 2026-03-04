"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

from django.urls import path
from . import views

urlpatterns = [
    path("GrokDebugger/", views.GrokDebugger, name="GrokDebugger"),
    path("GrokDebugger/simulate/", views.simulate_grok, name="simulate_grok"),
    path("GrokDebugger/patterns/", views.get_grok_patterns, name="get_grok_patterns"),
]