from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import ProductoIngredienteForm
from .models import ProductoIngrediente

ROLES_GESTION = ["ADMINISTRADOR", "JEFE_COCINA"]
ROLES_LECTURA = ["ADMINISTRADOR", "JEFE_COCINA", "JEFE_INVENTARIO"]


class RecetaListView(RoleRequiredMixin, ListView):
    model = ProductoIngrediente
    roles_permitidos = ROLES_LECTURA
    template_name = "recetas/recetas_list.html"
    context_object_name = "recetas"
    queryset = ProductoIngrediente.objects.select_related("producto", "item_inventario")


class RecetaCreateView(RoleRequiredMixin, CreateView):
    model = ProductoIngrediente
    form_class = ProductoIngredienteForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Receta"}
    success_url = reverse_lazy("recetas:recetas_list")


class RecetaUpdateView(RoleRequiredMixin, UpdateView):
    model = ProductoIngrediente
    form_class = ProductoIngredienteForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Receta"}
    success_url = reverse_lazy("recetas:recetas_list")


class RecetaDeleteView(RoleRequiredMixin, DeleteView):
    model = ProductoIngrediente
    roles_permitidos = ROLES_GESTION
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("recetas:recetas_list")
