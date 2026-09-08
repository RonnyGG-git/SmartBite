from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import CategoriaForm, ProductoForm
from .models import Categoria, Producto

ROLES_GESTION = ["ADMINISTRADOR", "JEFE_INVENTARIO"]
ROLES_LECTURA = ["ADMINISTRADOR", "JEFE_INVENTARIO", "JEFE_COCINA"]


class ProductoListView(RoleRequiredMixin, ListView):
    model = Producto
    roles_permitidos = ROLES_LECTURA
    template_name = "catalogo/productos_list.html"
    context_object_name = "productos"
    queryset = Producto.objects.select_related("categoria", "sucursal")


class ProductoCreateView(RoleRequiredMixin, CreateView):
    model = Producto
    form_class = ProductoForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Producto"}
    success_url = reverse_lazy("catalogo:productos_list")


class ProductoUpdateView(RoleRequiredMixin, UpdateView):
    model = Producto
    form_class = ProductoForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Producto"}
    success_url = reverse_lazy("catalogo:productos_list")


class ProductoDeleteView(RoleRequiredMixin, DeleteView):
    model = Producto
    roles_permitidos = ROLES_GESTION
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("catalogo:productos_list")


@require_POST
def producto_toggle_disponibilidad(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    usuario = request.user
    permitido = usuario.is_superuser or (usuario.rol_id and usuario.rol.nombre in ROLES_LECTURA)
    if permitido:
        producto.disponible = not producto.disponible
        producto.save(update_fields=["disponible"])
    return redirect("catalogo:productos_list")


class CategoriaListView(RoleRequiredMixin, ListView):
    model = Categoria
    roles_permitidos = ROLES_LECTURA
    template_name = "catalogo/categorias_list.html"
    context_object_name = "categorias"


class CategoriaCreateView(RoleRequiredMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Categoría"}
    success_url = reverse_lazy("catalogo:categorias_list")


class CategoriaUpdateView(RoleRequiredMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    roles_permitidos = ROLES_GESTION
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Categoría"}
    success_url = reverse_lazy("catalogo:categorias_list")


class CategoriaDeleteView(RoleRequiredMixin, DeleteView):
    model = Categoria
    roles_permitidos = ROLES_GESTION
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("catalogo:categorias_list")
