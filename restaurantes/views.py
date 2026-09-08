from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import RestauranteForm, SucursalForm
from .models import Restaurante, Sucursal

ROLES_ADMIN = ["ADMINISTRADOR"]


class RestauranteListView(RoleRequiredMixin, ListView):
    model = Restaurante
    roles_permitidos = ROLES_ADMIN
    template_name = "restaurantes/restaurantes_list.html"
    context_object_name = "restaurantes"


class RestauranteCreateView(RoleRequiredMixin, CreateView):
    model = Restaurante
    form_class = RestauranteForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Restaurante"}
    success_url = reverse_lazy("restaurantes:restaurantes_list")


class RestauranteUpdateView(RoleRequiredMixin, UpdateView):
    model = Restaurante
    form_class = RestauranteForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Restaurante"}
    success_url = reverse_lazy("restaurantes:restaurantes_list")


class RestauranteDeleteView(RoleRequiredMixin, DeleteView):
    model = Restaurante
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("restaurantes:restaurantes_list")


class SucursalListView(RoleRequiredMixin, ListView):
    model = Sucursal
    roles_permitidos = ROLES_ADMIN
    template_name = "restaurantes/sucursales_list.html"
    context_object_name = "sucursales"


class SucursalCreateView(RoleRequiredMixin, CreateView):
    model = Sucursal
    form_class = SucursalForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Sucursal"}
    success_url = reverse_lazy("restaurantes:sucursales_list")


class SucursalUpdateView(RoleRequiredMixin, UpdateView):
    model = Sucursal
    form_class = SucursalForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Sucursal"}
    success_url = reverse_lazy("restaurantes:sucursales_list")


class SucursalDeleteView(RoleRequiredMixin, DeleteView):
    model = Sucursal
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("restaurantes:sucursales_list")
