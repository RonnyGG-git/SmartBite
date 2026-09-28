from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import RoleRequiredMixin, usuario_tiene_rol

from .forms import AjusteStockForm, CompraForm, DetalleCompraFormSet, ItemInventarioForm, ProveedorForm
from .models import Compra, ItemInventario, MovimientoInventario, Proveedor

ROLES_INVENTARIO = ["ADMINISTRADOR", "JEFE_INVENTARIO"]
ROLES_LECTURA = ["ADMINISTRADOR", "JEFE_INVENTARIO", "JEFE_COCINA"]


class ItemInventarioListView(RoleRequiredMixin, ListView):
    model = ItemInventario
    roles_permitidos = ROLES_LECTURA
    template_name = "inventario/inventario_list.html"
    context_object_name = "items"
    queryset = ItemInventario.objects.select_related("sucursal")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # Los roles de solo lectura no ven acciones que les darían 403
        contexto["puede_gestionar"] = usuario_tiene_rol(self.request.user, ROLES_INVENTARIO)
        return contexto


class ItemInventarioCreateView(RoleRequiredMixin, CreateView):
    model = ItemInventario
    form_class = ItemInventarioForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Ítem de Inventario"}
    success_url = reverse_lazy("inventario:inventario_list")


class ItemInventarioUpdateView(RoleRequiredMixin, UpdateView):
    model = ItemInventario
    form_class = ItemInventarioForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Ítem de Inventario"}
    success_url = reverse_lazy("inventario:inventario_list")


def item_ajustar_stock(request, pk):
    item = get_object_or_404(ItemInventario, pk=pk)
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:inventario_list")

    if request.method == "POST":
        form = AjusteStockForm(request.POST)
        if form.is_valid():
            cantidad = form.cleaned_data["cantidad"]
            tipo = form.cleaned_data["tipo"]
            with transaction.atomic():
                if tipo == "ENTRADA":
                    item.stock_actual += cantidad
                else:
                    item.stock_actual = max(0, item.stock_actual - cantidad)
                item.save(update_fields=["stock_actual"])
                MovimientoInventario.objects.create(
                    item=item, tipo=tipo, cantidad=cantidad, motivo=form.cleaned_data["motivo"]
                )
            return redirect("inventario:inventario_list")
    else:
        form = AjusteStockForm()
    return render(request, "inventario/item_ajuste_form.html", {"item": item, "form": form})


class MovimientoInventarioListView(RoleRequiredMixin, ListView):
    model = MovimientoInventario
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/movimientos_list.html"
    context_object_name = "movimientos"
    queryset = MovimientoInventario.objects.select_related("item")


class ProveedorListView(RoleRequiredMixin, ListView):
    model = Proveedor
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/proveedores_list.html"
    context_object_name = "proveedores"


class ProveedorCreateView(RoleRequiredMixin, CreateView):
    model = Proveedor
    form_class = ProveedorForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Proveedor"}
    success_url = reverse_lazy("inventario:proveedores_list")


class ProveedorUpdateView(RoleRequiredMixin, UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Proveedor"}
    success_url = reverse_lazy("inventario:proveedores_list")


class ProveedorDeleteView(RoleRequiredMixin, DeleteView):
    model = Proveedor
    roles_permitidos = ROLES_INVENTARIO
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("inventario:proveedores_list")


class CompraListView(RoleRequiredMixin, ListView):
    model = Compra
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/compras_list.html"
    context_object_name = "compras"
    queryset = Compra.objects.select_related("proveedor").prefetch_related("detalles__item")


class CompraDetailView(RoleRequiredMixin, DetailView):
    model = Compra
    roles_permitidos = ROLES_INVENTARIO
    template_name = "inventario/compra_detail.html"
    context_object_name = "compra"


def compra_crear(request):
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:compras_list")

    if request.method == "POST":
        form = CompraForm(request.POST)
        formset = DetalleCompraFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                compra = form.save()
                formset.instance = compra
                formset.save()
            return redirect("inventario:compra_detalle", pk=compra.pk)
    else:
        form = CompraForm()
        formset = DetalleCompraFormSet()
    return render(request, "inventario/compra_form.html", {"form": form, "formset": formset})


@require_POST
def compra_recibir(request, pk):
    compra = get_object_or_404(Compra, pk=pk)
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:compras_list")
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
    compra = get_object_or_404(Compra, pk=pk)
    usuario = request.user
    if not usuario_tiene_rol(usuario, ROLES_INVENTARIO):
        return redirect("inventario:compras_list")
    if compra.estado == Compra.PENDIENTE:
        compra.estado = Compra.ANULADA
        compra.save(update_fields=["estado"])
    return redirect("inventario:compra_detalle", pk=compra.pk)
