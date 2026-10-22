from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin, rol_requerido
from core.tenancy import SESION_RESTAURANTE, RestauranteMixin, restaurantes_accesibles

from .forms import RestauranteForm, SucursalForm
from .models import Restaurante, Sucursal

ROLES_ADMIN = ["ADMINISTRADOR"]


class MisRestaurantesMixin:
    def get_queryset(self):
        return restaurantes_accesibles(self.request.user)


class RestauranteListView(MisRestaurantesMixin, RoleRequiredMixin, ListView):
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

    def form_valid(self, form):
        form.instance.administrador = self.request.user
        respuesta = super().form_valid(form)
        self.request.session[SESION_RESTAURANTE] = self.object.pk
        messages.success(
            self.request,
            f"Restaurante creado. Código de acceso para tus empleados: {self.object.codigo_acceso}",
        )
        return respuesta


class RestauranteUpdateView(MisRestaurantesMixin, RoleRequiredMixin, UpdateView):
    model = Restaurante
    form_class = RestauranteForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Restaurante"}
    success_url = reverse_lazy("restaurantes:restaurantes_list")


class RestauranteDeleteView(MisRestaurantesMixin, RoleRequiredMixin, DeleteView):
    model = Restaurante
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("restaurantes:restaurantes_list")


class SucursalListView(RestauranteMixin, RoleRequiredMixin, ListView):
    model = Sucursal
    roles_permitidos = ROLES_ADMIN
    template_name = "restaurantes/sucursales_list.html"
    context_object_name = "sucursales"
    ruta_restaurante = "restaurante"


class SucursalCreateView(RestauranteMixin, RoleRequiredMixin, CreateView):
    model = Sucursal
    ruta_restaurante = "restaurante"
    form_class = SucursalForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Sucursal"}
    success_url = reverse_lazy("restaurantes:sucursales_list")


class SucursalUpdateView(RestauranteMixin, RoleRequiredMixin, UpdateView):
    model = Sucursal
    ruta_restaurante = "restaurante"
    form_class = SucursalForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Sucursal"}
    success_url = reverse_lazy("restaurantes:sucursales_list")


class SucursalDeleteView(RestauranteMixin, RoleRequiredMixin, DeleteView):
    model = Sucursal
    ruta_restaurante = "restaurante"
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("restaurantes:sucursales_list")


@require_POST
@rol_requerido(*ROLES_ADMIN)
def regenerar_codigo(request, pk):
    restaurante = get_object_or_404(restaurantes_accesibles(request.user), pk=pk)
    restaurante.regenerar_codigo_acceso()
    messages.success(request, f"Nuevo código de {restaurante.nombre}: {restaurante.codigo_acceso}")
    return redirect("restaurantes:restaurantes_list")


@require_POST
@rol_requerido(*ROLES_ADMIN)
def seleccionar_restaurante(request, pk):
    restaurante = get_object_or_404(restaurantes_accesibles(request.user), pk=pk)
    request.session[SESION_RESTAURANTE] = restaurante.pk
    messages.success(request, f"Ahora trabajas con {restaurante.nombre}.")
    return redirect("restaurantes:restaurantes_list")
