from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reportes/", views.ReportesView.as_view(), name="reportes"),
]
