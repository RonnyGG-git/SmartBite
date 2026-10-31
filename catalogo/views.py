from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin, usuario_tiene_rol
from core.tenancy import RestauranteMixin, filtrar

from .forms import CategoriaForm, ProductoForm
from .models import Categoria, Producto

ROLES_GESTION = ["ADMINISTRADOR", "JEFE_COCINA"]
ROLES_LECTURA = ["ADMINISTRADOR", "JEFE_INVENTARIO", "JEFE_COCINA"]


class ProductoListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "sucursal__restaurante"
    model = Producto
    roles_permitidos = ROLES_LECTURA
    template_name = "catalogo/productos_list.html"
    context_object_name = "productos"
    queryset = Producto.objects.select_related("categoria", "sucursal")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["puede_gestionar"] = usuario_tiene_rol(self.request.user, ROLES_GESTION)
        return contexto


class ProductoCreateView(RestauranteMixin, RoleRequiredMixin, CreateView):
    ruta_restaurante = "sucursal__restaurante"
    model = Producto
    form_class = ProductoForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Producto"}
    success_url = reverse_lazy("catalogo:productos_list")

    def get_initial(self):
        inicial = super().get_initial()
        if self.request.method == "GET":
            for campo in ("nombre", "descripcion"):
                valor = self.request.GET.get(campo)
                if valor:
                    inicial[campo] = valor
        return inicial


class ProductoUpdateView(RestauranteMixin, RoleRequiredMixin, UpdateView):
    ruta_restaurante = "sucursal__restaurante"
    model = Producto
    form_class = ProductoForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Producto"}
    success_url = reverse_lazy("catalogo:productos_list")


class ProductoDeleteView(RestauranteMixin, RoleRequiredMixin, DeleteView):
    ruta_restaurante = "sucursal__restaurante"
    model = Producto
    roles_permitidos = ROLES_GESTION
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("catalogo:productos_list")


@require_POST
def producto_toggle_disponibilidad(request, pk):
    usuario = request.user
    permitido = usuario_tiene_rol(usuario, ROLES_GESTION)
    if permitido:
        producto = get_object_or_404(filtrar(Producto.objects, request, "sucursal__restaurante"), pk=pk)
        producto.disponible = not producto.disponible
        producto.save(update_fields=["disponible"])
    return redirect("catalogo:productos_list")


class CategoriaListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "restaurante"
    model = Categoria
    roles_permitidos = ROLES_LECTURA
    template_name = "catalogo/categorias_list.html"
    context_object_name = "categorias"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["puede_gestionar"] = usuario_tiene_rol(self.request.user, ROLES_GESTION)
        return contexto


class CategoriaCreateView(RestauranteMixin, RoleRequiredMixin, CreateView):
    ruta_restaurante = "restaurante"
    asignar_restaurante = True
    model = Categoria
    form_class = CategoriaForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Categoría"}
    success_url = reverse_lazy("catalogo:categorias_list")


class CategoriaUpdateView(RestauranteMixin, RoleRequiredMixin, UpdateView):
    ruta_restaurante = "restaurante"
    model = Categoria
    form_class = CategoriaForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Categoría"}
    success_url = reverse_lazy("catalogo:categorias_list")


class CategoriaDeleteView(RestauranteMixin, RoleRequiredMixin, DeleteView):
    ruta_restaurante = "restaurante"
    model = Categoria
    roles_permitidos = ROLES_GESTION
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("catalogo:categorias_list")
