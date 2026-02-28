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