from django.urls import path

from . import views

app_name = "cocina"

urlpatterns = [
    path("", views.CocinaListView.as_view(), name="cocina"),
]
