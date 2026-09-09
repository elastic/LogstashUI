#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""URL configuration for the REST API."""

from django.urls import path

from API import connections_views, security_views

urlpatterns = [
    # Connections
    path('connections/', connections_views.connection_list, name='api-connections-list'),
    path('connections/<int:connection_id>/', connections_views.connection_detail, name='api-connections-detail'),
    path('connections/<int:connection_id>/test/', connections_views.connection_test, name='api-connections-test'),

    # Security — bootstrap, users, API keys
    path('security/bootstrap/', security_views.bootstrap_view, name='api-security-bootstrap'),
    path('security/me/', security_views.me_view, name='api-security-me'),
    path('security/users/', security_views.user_list, name='api-security-user-list'),
    path('security/users/<int:user_id>/', security_views.user_detail, name='api-security-user-detail'),
    path('security/keys/', security_views.key_list, name='api-security-key-list'),
    path('security/keys/<int:key_id>/revoke/', security_views.key_revoke, name='api-security-key-revoke'),
    path('security/keys/<int:key_id>/', security_views.key_detail, name='api-security-key-detail'),
]
