"""Módulo Cliente — la cara pública del Módulo de Pedidos (diagrama de casos
de uso, actor Cliente). No requiere login: la mesa se identifica al escanear
su QR y los pedidos del comensal se recuerdan en su sesión.

CU-PED-16 Escanear código QR de mesa  -> mesa()
CU-PED-01 Consultar menú disponible   -> menu()
CU-PED-05 Realizar autopedido          -> autopedido()  (incluye 02 y 08)
CU-PED-13 Consultar estado del pedido  -> pedido()
CU-PED-17/18/19 Retroalimentación      -> retroalimentacion()
CU-ADM-16 Revisar sugerencias y denuncias (Administrador) -> RetroalimentacionListView
"""

from collections import OrderedDict

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from catalogo.models import Producto
from core.mixins import RoleRequiredMixin, rol_requerido
from operativo.models import Cliente, DetalleOrden, Mesa, Orden

from .forms import MAX_CANTIDAD_POR_PRODUCTO, RetroalimentacionForm, leer_cantidades
from .models import Retroalimentacion

SESION_MESA = "cliente_mesa_id"
SESION_PEDIDOS = "cliente_pedidos"
ROLES_ADMIN = ["ADMINISTRADOR"]


# ---------------------------------------------------------------- helpers
def _mesa_de_sesion(request):
    mesa_id = request.session.get(SESION_MESA)
    if not mesa_id:
        return None
    return Mesa.objects.select_related("sucursal").filter(pk=mesa_id, activa=True).first()


def _pedidos_de_sesion(request):
    return list(request.session.get(SESION_PEDIDOS, []))


def _pedido_en_curso(request, mesa):
    """Pedido activo de la mesa, solo si lo hizo este mismo comensal."""
    if mesa is None:
        return None
    orden = mesa.orden_activa
    if orden and orden.pk in _pedidos_de_sesion(request):
        return orden
    return None


def _productos_disponibles(mesa):
    """CU-PED-01: platillos disponibles de la sucursal de la mesa."""
    qs = Producto.objects.filter(disponible=True).select_related("categoria")
    if mesa is not None:
        qs = qs.filter(sucursal=mesa.sucursal)
    return qs.order_by("categoria__nombre", "nombre")


def _agrupar_por_categoria(productos):
    grupos = OrderedDict()
    for p in productos:
        grupos.setdefault(p.categoria, []).append(p)
    return list(grupos.items())


# ------------------------------------------------------------ vistas públicas
def mesa(request, mesa_id):
    """CU-PED-16: el QR de la mesa apunta aquí; identifica la mesa y lleva al menú."""
    mesa_obj = get_object_or_404(Mesa, pk=mesa_id, activa=True)
    request.session[SESION_MESA] = mesa_obj.pk
    return redirect("cliente:menu")


def menu(request):
    mesa_obj = _mesa_de_sesion(request)
    productos = _productos_disponibles(mesa_obj)
    en_curso = _pedido_en_curso(request, mesa_obj)
    puede_pedir = mesa_obj is not None and mesa_obj.estado == Mesa.DISPONIBLE

    return render(
        request,
        "cliente/menu.html",
        {
            "mesa": mesa_obj,
            "categorias": _agrupar_por_categoria(productos),
            "puede_pedir": puede_pedir,
            "pedido_en_curso": en_curso,
            "max_cantidad": MAX_CANTIDAD_POR_PRODUCTO,
        },
    )


@require_POST
def autopedido(request):
    """CU-PED-05 Realizar autopedido: incluye CU-PED-02 (seleccionar platillos)
    y CU-PED-08 (enviar a cocina: la orden entra PENDIENTE a la cola del Chef)."""
    mesa_obj = _mesa_de_sesion(request)
    if mesa_obj is None:
        messages.error(request, "Escanea el código QR de tu mesa para hacer un pedido.")
        return redirect("cliente:menu")

    seleccion = leer_cantidades(request.POST, _productos_disponibles(mesa_obj))
    if not seleccion:
        messages.error(request, "Elige al menos un platillo antes de enviar el pedido.")
        return redirect("cliente:menu")

    with transaction.atomic():
        mesa_bloqueada = Mesa.objects.select_for_update().get(pk=mesa_obj.pk)
        if mesa_bloqueada.estado != Mesa.DISPONIBLE:
            messages.error(request, "Esta mesa ya tiene un pedido en curso. Pide ayuda a tu mesero.")
            return redirect("cliente:menu")

        nombre = request.POST.get("nombre", "").strip()[:150]
        cliente = Cliente.objects.create(nombre=nombre) if nombre else None
        orden = Orden.objects.create(
            mesa=mesa_bloqueada, cliente=cliente, origen=Orden.ORIGEN_AUTOPEDIDO, estado=Orden.PENDIENTE
        )
        DetalleOrden.objects.bulk_create(
            DetalleOrden(orden=orden, producto=p, cantidad=c, precio_unitario=p.precio) for p, c in seleccion
        )
        mesa_bloqueada.estado = Mesa.OCUPADA
        mesa_bloqueada.save(update_fields=["estado"])

    pedidos = _pedidos_de_sesion(request)
    pedidos.append(orden.pk)
    request.session[SESION_PEDIDOS] = pedidos[-20:]
    messages.success(request, "Pedido enviado a cocina.")
    return redirect("cliente:pedido", pk=orden.pk)


def pedido(request, pk):
    """CU-PED-13: solo el comensal que hizo el pedido puede verlo."""
    if pk not in _pedidos_de_sesion(request):
        raise Http404("Pedido no encontrado")
    orden = get_object_or_404(
        Orden.objects.select_related("mesa").prefetch_related("detalles__producto"), pk=pk
    )
    return render(request, "cliente/pedido.html", {"orden": orden, "mesa": orden.mesa})


def mis_pedidos(request):
    """Acceso rápido al último pedido de la sesión (o al menú si no hay)."""
    pedidos = _pedidos_de_sesion(request)
    if pedidos:
        return redirect("cliente:pedido", pk=pedidos[-1])
    return redirect("cliente:menu")


def retroalimentacion(request):
    """CU-PED-17 (sugerencia CU-PED-18 / denuncia CU-PED-19)."""
    mesa_obj = _mesa_de_sesion(request)
    if request.method == "POST":
        form = RetroalimentacionForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.mesa = mesa_obj
            item.save()
            messages.success(request, "Gracias. El equipo del restaurante revisará tu mensaje.")
            return redirect("cliente:menu")
    else:
        form = RetroalimentacionForm(initial={"tipo": request.GET.get("tipo", Retroalimentacion.SUGERENCIA)})
    return render(request, "cliente/retroalimentacion.html", {"form": form, "mesa": mesa_obj})


# ---------------------------------------------------- vistas del Administrador
class RetroalimentacionListView(RoleRequiredMixin, ListView):
    """CU-ADM-16 Revisar sugerencias y denuncias."""

    model = Retroalimentacion
    roles_permitidos = ROLES_ADMIN
    template_name = "cliente/retroalimentacion_list.html"
    context_object_name = "mensajes"
    queryset = Retroalimentacion.objects.select_related("mesa")


@require_POST
@rol_requerido(*ROLES_ADMIN)
def retroalimentacion_revisar(request, pk):
    item = get_object_or_404(Retroalimentacion, pk=pk)
    item.revisada = not item.revisada
    item.save(update_fields=["revisada", "actualizado_en"])
    return redirect("cliente:retroalimentacion_list")
