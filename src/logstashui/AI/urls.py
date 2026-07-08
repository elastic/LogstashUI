#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import path
from . import views
from . import integration_factory

urlpatterns = [
    path("IntegrationFactory/", views.IntegrationFactory, name="IntegrationFactory"),
    path("IntegrationFactory/models/", integration_factory.get_models, name="GetModels"),
    path("IntegrationFactory/classify/", integration_factory.classify_logs, name="ClassifyLogs"),
    path("IntegrationFactory/generate/", integration_factory.generate_integration, name="GenerateIntegration"),
    path("IntegrationFactory/delete/", integration_factory.delete_integration_assets, name="DeleteIntegrationAssets"),
    path("IntegrationFactory/install-prebuilt/", integration_factory.install_prebuilt_integration, name="InstallPrebuiltIntegration"),

    # AI-assisted SNMP device onboarding (discover -> author -> approve -> deploy)
    path("Onboarding/", views.AIOnboarding, name="AIOnboarding"),
    path("Onboarding/Settings/", views.SaveAISettings, name="SaveAISettings"),
    path("Onboarding/Generate/", views.GenerateDraft, name="GenerateDraft"),
    path("Onboarding/Approve/", views.ApproveDraft, name="ApproveDraft"),
    path("Onboarding/Reject/", views.RejectDraft, name="RejectDraft"),
]
