from django.urls import path

from . import views

app_name = "cocina"

urlpatterns = [
    path("", views.CocinaListView.as_view(), name="cocina"),
    path("ordenes/<int:pk>/estado/", views.actualizar_estado, name="actualizar_estado"),
]
