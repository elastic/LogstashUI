#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""URL configuration for the REST API."""

from django.urls import path

from API import connections_views, security_views, snmp_views, policies_views, pipelines_views

urlpatterns = [
    # Connections
    path('connections/', connections_views.connection_list, name='api-connections-list'),
    path('connections/<int:connection_id>/', connections_views.connection_detail, name='api-connections-detail'),
    path('connections/<int:connection_id>/test/', connections_views.connection_test, name='api-connections-test'),

    # SNMP Devices
    path('snmp/devices/', snmp_views.device_list, name='api-snmp-device-list'),
    path('snmp/devices/<int:device_id>/', snmp_views.device_detail, name='api-snmp-device-detail'),

    # SNMP Credentials
    path('snmp/credentials/', snmp_views.credential_list, name='api-snmp-credential-list'),
    path('snmp/credentials/<int:credential_id>/', snmp_views.credential_detail, name='api-snmp-credential-detail'),

    # SNMP Networks
    path('snmp/networks/', snmp_views.network_list, name='api-snmp-network-list'),
    path('snmp/networks/<int:network_id>/', snmp_views.network_detail, name='api-snmp-network-detail'),

    # SNMP Profiles
    path('snmp/profiles/', snmp_views.profile_list, name='api-snmp-profile-list'),
    path('snmp/profiles/<int:profile_id>/', snmp_views.profile_detail, name='api-snmp-profile-detail'),

    # SNMP Device Templates
    path('snmp/templates/', snmp_views.template_list, name='api-snmp-template-list'),
    path('snmp/templates/<int:template_id>/', snmp_views.template_detail, name='api-snmp-template-detail'),

    # SNMP Deploy
    path('snmp/deploy/status/', snmp_views.deploy_status, name='api-snmp-deploy-status'),
    path('snmp/deploy/diff/', snmp_views.deploy_diff, name='api-snmp-deploy-diff'),
    path('snmp/deploy/apply/', snmp_views.deploy_apply, name='api-snmp-deploy-apply'),

    # Pipelines — agent/policy (Django ORM, integer IDs)
    path('pipelines/', pipelines_views.pipeline_list, name='api-pipeline-list'),
    path('pipelines/simulate/', pipelines_views.pipeline_simulate, name='api-pipeline-simulate'),
    path('pipelines/policies/<int:policy_id>/deploy/', pipelines_views.policy_deploy, name='api-pipeline-deploy'),
    path('pipelines/es/<int:connection_id>/', pipelines_views.es_pipeline_list, name='api-es-pipeline-list'),
    path('pipelines/es/<int:connection_id>/<str:name>/', pipelines_views.es_pipeline_detail, name='api-es-pipeline-detail'),
    path('pipelines/<int:pipeline_id>/', pipelines_views.pipeline_detail, name='api-pipeline-detail'),

    # Policies
    path('policies/', policies_views.policy_list, name='api-policies-list'),
    path('policies/<int:policy_id>/', policies_views.policy_detail, name='api-policies-detail'),
    path('policies/<int:policy_id>/deploy/', policies_views.policy_deploy, name='api-policies-deploy'),
    path('policies/<int:policy_id>/clone/', policies_views.policy_clone, name='api-policies-clone'),
    path('policies/<int:policy_id>/diff/', policies_views.policy_diff, name='api-policies-diff'),
    path('policies/<int:policy_id>/tokens/', policies_views.policy_tokens, name='api-policies-tokens'),
    path('policies/<int:policy_id>/tokens/<int:token_id>/', policies_views.policy_token_detail, name='api-policies-token-detail'),

    # Security — bootstrap, users, API keys
    path('security/bootstrap/', security_views.bootstrap_view, name='api-security-bootstrap'),
    path('security/me/', security_views.me_view, name='api-security-me'),
    path('security/users/', security_views.user_list, name='api-security-user-list'),
    path('security/users/<int:user_id>/', security_views.user_detail, name='api-security-user-detail'),
    path('security/keys/', security_views.key_list, name='api-security-key-list'),
    path('security/keys/<int:key_id>/revoke/', security_views.key_revoke, name='api-security-key-revoke'),
    path('security/keys/<int:key_id>/', security_views.key_detail, name='api-security-key-detail'),
]
