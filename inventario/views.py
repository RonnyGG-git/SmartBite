from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import RoleRequiredMixin, usuario_tiene_rol
from core.tenancy import RestauranteMixin, filtrar, limitar_opciones

from .forms import AjusteStockForm, CompraForm, DetalleCompraFormSet, ItemInventarioForm, ProveedorForm
from .models import Compra, ItemInventario, MovimientoInventario, Proveedor

ROLES_INVENTARIO = ["ADMINISTRADOR", "JEFE_INVENTARIO"]
ROLES_LECTURA = ["ADMINISTRADOR", "JEFE_INVENTARIO", "JEFE_COCINA"]


class ItemInventarioListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "sucursal__restaurante"
    model = ItemInventario
    roles_permitidos = ROLES_LECTURA
    template_name = "inventario/inventario_list.html"
    context_object_name = "items"
    queryset = ItemInventario.objects.select_related("sucursal")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["puede_gestionar"] = usuario_tiene_rol(self.request.user, ROLES_INVENTARIO)
        return contexto


class ItemInventarioCreateView(RestauranteMixin, RoleRequiredMixin, CreateView):
    ruta_restaurante = "sucursal__restaurante"
    model = ItemInventario
    form_class = ItemInventarioForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Ítem de Inventario"}
    success_url = reverse_lazy("inventario:inventario_list")


class ItemInventarioUpdateView(RestauranteMixin, RoleRequiredMixin, UpdateView):
    ruta_restaurante = "sucursal__restaurante"
    model = ItemInventario
    form_class = ItemInventarioForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Ítem de Inventario"}
    success_url = reverse_lazy("inventario:inventario_list")


def item_ajustar_stock(request, pk):
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:inventario_list")
    item = get_object_or_404(filtrar(ItemInventario.objects, request, "sucursal__restaurante"), pk=pk)

    if request.method == "POST":
        form = AjusteStockForm(request.POST)
        if form.is_valid():
            item.ajustar_stock(
                form.cleaned_data["tipo"], form.cleaned_data["cantidad"], form.cleaned_data["motivo"]
            )
            return redirect("inventario:inventario_list")
    else:
        form = AjusteStockForm()
    return render(request, "inventario/item_ajuste_form.html", {"item": item, "form": form})


class MovimientoInventarioListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "item__sucursal__restaurante"
    model = MovimientoInventario
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/movimientos_list.html"
    context_object_name = "movimientos"
    queryset = MovimientoInventario.objects.select_related("item")


class ProveedorListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "restaurante"
    model = Proveedor
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/proveedores_list.html"
    context_object_name = "proveedores"


class ProveedorCreateView(RestauranteMixin, RoleRequiredMixin, CreateView):
    ruta_restaurante = "restaurante"
    asignar_restaurante = True
    model = Proveedor
    form_class = ProveedorForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Proveedor"}
    success_url = reverse_lazy("inventario:proveedores_list")


class ProveedorUpdateView(RestauranteMixin, RoleRequiredMixin, UpdateView):
    ruta_restaurante = "restaurante"
    model = Proveedor
    form_class = ProveedorForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Proveedor"}
    success_url = reverse_lazy("inventario:proveedores_list")


class ProveedorDeleteView(RestauranteMixin, RoleRequiredMixin, DeleteView):
    ruta_restaurante = "restaurante"
    model = Proveedor
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("inventario:proveedores_list")


class CompraListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "proveedor__restaurante"
    model = Compra
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/compras_list.html"
    context_object_name = "compras"
    queryset = Compra.objects.select_related("proveedor").prefetch_related("detalles__item")


class CompraDetailView(RestauranteMixin, RoleRequiredMixin, DetailView):
    ruta_restaurante = "proveedor__restaurante"
    model = Compra
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/compra_detail.html"
    context_object_name = "compra"


def compra_crear(request):
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:compras_list")

    if request.method == "POST":
        form = limitar_opciones(CompraForm(request.POST), request)
        formset = DetalleCompraFormSet(request.POST)
        for detalle in formset.forms:
            limitar_opciones(detalle, request)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                compra = form.save()
                formset.instance = compra
                formset.save()
            return redirect("inventario:compra_detalle", pk=compra.pk)
    else:
        form = limitar_opciones(CompraForm(), request)
        formset = DetalleCompraFormSet()
        for detalle in formset.forms:
            limitar_opciones(detalle, request)
    return render(request, "inventario/compra_form.html", {"form": form, "formset": formset})


@require_POST
def compra_recibir(request, pk):
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:compras_list")
    compra = get_object_or_404(filtrar(Compra.objects, request, "proveedor__restaurante"), pk=pk)
    if compra.estado == Compra.PENDIENTE:
        with transaction.atomic():
            for detalle in compra.detalles.select_related("item"):
                detalle.item.stock_actual += detalle.cantidad
                detalle.item.save(update_fields=["stock_actual"])
                MovimientoInventario.objects.create(
                    item=detalle.item,
                    tipo=MovimientoInventario.ENTRADA,
                    cantidad=detalle.cantidad,
                    motivo=f"Recepción compra #{compra.pk}",
                )
            compra.estado = Compra.RECIBIDA
            compra.save(update_fields=["estado"])
    return redirect("inventario:compra_detalle", pk=compra.pk)


@require_POST
def compra_anular(request, pk):
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:compras_list")
    compra = get_object_or_404(filtrar(Compra.objects, request, "proveedor__restaurante"), pk=pk)
    if compra.estado == Compra.PENDIENTE:
        compra.estado = Compra.ANULADA
        compra.save(update_fields=["estado"])
    return redirect("inventario:compra_detalle", pk=compra.pk)
