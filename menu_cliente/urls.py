from django.urls import path

from . import views

app_name = "menu_cliente"

urlpatterns = [
    path("", views.menu, name="menu"),
]
