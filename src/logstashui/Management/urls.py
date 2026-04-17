#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("Login/", views.BootstrapLoginView.as_view(), name="Login"),
    path("Logout/", auth_views.LogoutView.as_view(), name="Logout"),
    
    path("", views.Management, name="Management"),
    path("Users/", views.Users, name="Users"),
    path("Logs/", views.Logs, name="Logs"),
    path("Logs/filter", views.LogsFilter, name="LogsFilter"),
    path("Logs/download", views.LogsDownload, name="LogsDownload"),
]