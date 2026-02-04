from django.contrib import admin
from django.urls import path, include
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("Networks/", views.Networks, name="Networks"),
    path("Devices/", views.Devices, name="Devices"),
    path("Profiles/", views.Profiles, name="Profiles"),
    path("Credentials/", views.Credentials, name="Credentials")
]