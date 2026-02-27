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