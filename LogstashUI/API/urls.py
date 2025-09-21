from django.urls import path, include
from . import views

urlpatterns = [
    path('TestConnectivity', views.TestConnectivity, name='TestConnectivity'),
    path("DeleteConnection/<int:connection_id>/", views.DeleteConnection, name="DeleteConnection"),
    path("GetLogstashCode", views.GetLogstashCode, name="GetLogstashCode"),
    path("SavePipeline/", views.SavePipeline, name="SavePipeline"),
    path("SimulatePipeline/", views.SimulatePipeline, name="SimulatePipeline")
]