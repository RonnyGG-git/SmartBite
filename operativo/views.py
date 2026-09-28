import base64
from io import BytesIO

import qrcode
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from catalogo.models import Producto
from core.mixins import RoleRequiredMixin, rol_requerido

from .forms import AgregarProductoForm, CambiarEstadoOrdenForm, ClienteRapidoForm, CrearOrdenForm, MesaForm
from .models import Cliente, DetalleOrden, Mesa, Orden

ROLES_ADMIN = ["ADMINISTRADOR"]
ROLES_MESERO = ["ADMINISTRADOR", "MESERO"]
ROLES_ORDEN = ["ADMINISTRADOR", "MESERO", "CAJERO"]


class MesaListView(RoleRequiredMixin, ListView):
    model = Mesa
    roles_permitidos = ROLES_MESERO
    template_name = "operativo/mesas_list.html"
    context_object_name = "mesas"
    queryset = Mesa.objects.select_related("sucursal").prefetch_related("ordenes")


class MesaCreateView(RoleRequiredMixin, CreateView):
    model = Mesa
    form_class = MesaForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Mesa"}
    success_url = reverse_lazy("operativo:mesas_list")


class MesaUpdateView(RoleRequiredMixin, UpdateView):
    model = Mesa
    form_class = MesaForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Mesa"}
    success_url = reverse_lazy("operativo:mesas_list")


class MesaDeleteView(RoleRequiredMixin, DeleteView):
    model = Mesa
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("operativo:mesas_list")


def crear_orden(request):
    usuario = request.user
    if not (usuario.is_superuser or (usuario.rol_id and usuario.rol.nombre in ROLES_MESERO)):
        return redirect("operativo:mesas_list")

    mesa_id = request.GET.get("mesaId")
    cliente_form = ClienteRapidoForm()

    if request.method == "POST":
        form = CrearOrdenForm(request.POST)
        if form.is_valid():
            # RF-010: transaccion atomica con bloqueo selectivo de la fila de
            # la mesa y verificacion de orden activa antes de crear.
            with transaction.atomic():
                mesa_bloqueada = Mesa.objects.select_for_update().get(
                    pk=form.cleaned_data["mesa"].pk
                )
                if mesa_bloqueada.orden_activa is not None:
                    form.add_error(None, "Esta mesa ya tiene una orden activa.")
                else:
                    orden = form.save(commit=False)
                    orden.mesa = mesa_bloqueada
                    orden.save()
                    mesa_bloqueada.estado = Mesa.OCUPADA
                    mesa_bloqueada.save(update_fields=["estado"])
                    return redirect("operativo:detalle_orden", pk=orden.pk)
    else:
        initial = {"mesa": mesa_id} if mesa_id else {}
        form = CrearOrdenForm(initial=initial)

    return render(
        request,
        "operativo/crear_orden.html",
        {"form": form, "cliente_form": cliente_form},
    )


@rol_requerido(*ROLES_MESERO)
def crear_cliente_rapido(request):
    if request.method == "POST":
        form = ClienteRapidoForm(request.POST)
        if form.is_valid():
            form.save()
    return redirect("operativo:crear_orden")


class DetalleOrdenView(RoleRequiredMixin, DetailView):
    model = Orden
    roles_permitidos = ROLES_ORDEN
    template_name = "operativo/detalle_orden.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        productos_qs = Producto.objects.filter(disponible=True, sucursal=self.object.mesa.sucursal)
        contexto["agregar_form"] = AgregarProductoForm(productos_qs=productos_qs)
        return contexto


@rol_requerido(*ROLES_MESERO)
@require_POST
def agregar_producto(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    productos_qs = Producto.objects.filter(disponible=True, sucursal=orden.mesa.sucursal)
    if request.method == "POST":
        form = AgregarProductoForm(request.POST, productos_qs=productos_qs)
        if form.is_valid():
            producto = form.cleaned_data["producto"]
            DetalleOrden.objects.create(
                orden=orden,
                producto=producto,
                cantidad=form.cleaned_data["cantidad"],
                precio_unitario=producto.precio,
            )
    return redirect("operativo:detalle_orden", pk=pk)


@rol_requerido(*ROLES_MESERO)
@require_POST
def cambiar_estado_orden(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    if request.method == "POST":
        form = CambiarEstadoOrdenForm(request.POST, orden=orden)
        if form.is_valid():
            orden.estado = form.cleaned_data["estado"]
            orden.save(update_fields=["estado"])
            if orden.estado in (Orden.ENTREGADA, Orden.CANCELADA):
                orden.mesa.estado = Mesa.DISPONIBLE
                orden.mesa.save(update_fields=["estado"])
    return redirect("operativo:detalle_orden", pk=pk)


@rol_requerido(*ROLES_MESERO)
def generar_qr(request, mesa_id):
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    url_menu = request.build_absolute_uri(reverse("menu_cliente:menu") + f"?mesa={mesa.id}")

    imagen = qrcode.make(url_menu)
    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return render(
        request,
        "operativo/generar_qr.html",
        {"mesa": mesa, "url_menu": url_menu, "qr_base64": qr_base64},
    )
