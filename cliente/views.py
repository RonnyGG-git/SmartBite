from collections import OrderedDict

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from catalogo.models import Producto
from core.mixins import RoleRequiredMixin, rol_requerido
from core.tenancy import RestauranteMixin, filtrar
from operativo.models import DetalleOrden, Mesa, Orden
from operativo.services import crear_orden, obtener_cliente
from restaurantes.geo import distancia_km, leer_coordenadas
from restaurantes.models import Sucursal

from .forms import MAX_CANTIDAD_POR_PRODUCTO, RetroalimentacionForm, leer_cantidades
from .models import Retroalimentacion

SESION_MESA = "cliente_mesa_id"
SESION_PEDIDOS = "cliente_pedidos"
SESION_MESA_ASIGNADA = "cliente_mesa_asignada"
SESION_TIPO_CONSUMO = "cliente_tipo_consumo"
SESION_CARRITO = "cliente_carrito"
SESION_NOMBRE = "cliente_nombre"
SESION_SUCURSAL = "cliente_sucursal_id"
ROLES_ADMIN = ["ADMINISTRADOR"]


def _mesa_de_sesion(request):
    mesa_id = request.session.get(SESION_MESA)
    if not mesa_id:
        return None
    return Mesa.objects.select_related("sucursal__restaurante").filter(pk=mesa_id, activa=True).first()


def _sucursales_publicas():
    return (
        Sucursal.objects.filter(activo=True, restaurante__activo=True, productos__disponible=True)
        .select_related("restaurante")
        .distinct()
    )


def _sucursal_elegida(request):
    sucursal_id = request.session.get(SESION_SUCURSAL)
    if not sucursal_id:
        return None
    return _sucursales_publicas().filter(pk=sucursal_id).first()


def _contexto(request):
    mesa = _mesa_de_sesion(request)
    if mesa is not None:
        return mesa, mesa.sucursal
    return None, _sucursal_elegida(request)


def _pedidos_de_sesion(request):
    return list(request.session.get(SESION_PEDIDOS, []))


def _pedido_en_curso(request, mesa, sucursal=None):
    if mesa is not None:
        orden = mesa.orden_activa
        if orden and orden.pk in _pedidos_de_sesion(request):
            return orden
        return None
    if sucursal is None:
        return None
    return (
        Orden.objects.filter(pk__in=_pedidos_de_sesion(request), sucursal=sucursal)
        .exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA])
        .order_by("-pk")
        .first()
    )


def _productos_de_sucursal(sucursal):
    if sucursal is None:
        return Producto.objects.none()
    qs = Producto.objects.filter(disponible=True, sucursal=sucursal).select_related("categoria")
    return qs.order_by("categoria__nombre", "nombre")


def _productos_disponibles(mesa):
    return _productos_de_sucursal(mesa.sucursal if mesa is not None else None)


def _mesa_asignada(request, mesa):
    return mesa is not None and request.session.get(SESION_MESA_ASIGNADA) == mesa.pk


def _puede_pedir(request, mesa, sucursal=None):
    if mesa is not None:
        return _mesa_asignada(request, mesa) and mesa.orden_activa is None
    return sucursal is not None


def _carrito(request, sucursal):
    guardado = request.session.get(SESION_CARRITO, {})
    return [(p, guardado[str(p.pk)]) for p in _productos_de_sucursal(sucursal) if str(p.pk) in guardado]


def _agrupar_por_categoria(productos):
    grupos = OrderedDict()
    for p in productos:
        grupos.setdefault(p.categoria, []).append(p)
    return list(grupos.items())


def _limpiar_pedido(request):
    for clave in (SESION_MESA_ASIGNADA, SESION_TIPO_CONSUMO, SESION_CARRITO, SESION_NOMBRE):
        request.session.pop(clave, None)


def restaurantes(request):
    sucursales = list(_sucursales_publicas())
    busqueda = request.GET.get("q", "").strip()[:80]
    if busqueda:
        termino = busqueda.lower()
        sucursales = [
            s for s in sucursales
            if termino in s.nombre.lower() or termino in s.restaurante.nombre.lower() or termino in s.direccion.lower()
        ]
    origen = leer_coordenadas(request.GET.get("lat"), request.GET.get("lng"))
    for s in sucursales:
        s.distancia_km = (
            distancia_km(origen[0], origen[1], s.latitud, s.longitud) if origen and s.tiene_ubicacion else None
        )
    sucursales.sort(key=lambda s: (s.distancia_km is None, s.distancia_km or 0, s.restaurante.nombre, s.nombre))
    return render(request, "cliente/restaurantes.html", {
        "sucursales": sucursales,
        "busqueda": busqueda,
        "con_ubicacion": origen is not None,
        "elegida": request.session.get(SESION_SUCURSAL),
    })


def sucursal(request, sucursal_id):
    elegida = get_object_or_404(_sucursales_publicas(), pk=sucursal_id)
    if request.session.get(SESION_MESA) or request.session.get(SESION_SUCURSAL) != elegida.pk:
        _limpiar_pedido(request)
    request.session.pop(SESION_MESA, None)
    request.session[SESION_SUCURSAL] = elegida.pk
    return redirect("cliente:menu" if request.session.get(SESION_TIPO_CONSUMO) else "cliente:tipo_consumo")


def mesa(request, mesa_id):
    mesa_obj = get_object_or_404(Mesa, pk=mesa_id, activa=True)
    if request.session.get(SESION_MESA) != mesa_obj.pk:
        _limpiar_pedido(request)
    request.session[SESION_MESA] = mesa_obj.pk
    request.session[SESION_SUCURSAL] = mesa_obj.sucursal_id
    if _mesa_asignada(request, mesa_obj):
        return redirect("cliente:menu" if request.session.get(SESION_TIPO_CONSUMO) else "cliente:tipo_consumo")
    with transaction.atomic():
        libre = Mesa.objects.select_for_update().get(pk=mesa_obj.pk)
        if libre.estado == Mesa.DISPONIBLE and libre.orden_activa is None:
            libre.estado = Mesa.OCUPADA
            libre.save(update_fields=["estado"])
            request.session[SESION_MESA_ASIGNADA] = libre.pk
            return redirect("cliente:tipo_consumo")
    return redirect("cliente:menu")


def tipo_consumo(request):
    mesa_obj, sucursal_obj = _contexto(request)
    if not (_mesa_asignada(request, mesa_obj) or (mesa_obj is None and sucursal_obj is not None)):
        return redirect("cliente:menu")
    if request.method == "POST":
        tipo = request.POST.get("tipo")
        if tipo in dict(Orden.TIPO_CONSUMO_CHOICES):
            request.session[SESION_TIPO_CONSUMO] = tipo
            return redirect("cliente:menu")
        messages.error(request, "Elige si tu pedido es para llevar o para comer aquí.")
    return render(request, "cliente/tipo_consumo.html", {
        "mesa": mesa_obj,
        "sucursal": sucursal_obj,
        "tipos": Orden.TIPO_CONSUMO_CHOICES,
        "actual": request.session.get(SESION_TIPO_CONSUMO),
    })


def menu(request):
    mesa_obj, sucursal_obj = _contexto(request)
    productos = list(_productos_de_sucursal(sucursal_obj))
    guardado = request.session.get(SESION_CARRITO, {})
    for producto in productos:
        producto.cantidad_carrito = guardado.get(str(producto.pk), 0)
    en_curso = _pedido_en_curso(request, mesa_obj, sucursal_obj)
    puede_pedir = _puede_pedir(request, mesa_obj, sucursal_obj)
    tipo = request.session.get(SESION_TIPO_CONSUMO)
    if puede_pedir and not tipo:
        return redirect("cliente:tipo_consumo")
    return render(
        request,
        "cliente/menu.html",
        {
            "mesa": mesa_obj,
            "sucursal": sucursal_obj,
            "categorias": _agrupar_por_categoria(productos),
            "puede_pedir": puede_pedir,
            "pedido_en_curso": en_curso,
            "max_cantidad": MAX_CANTIDAD_POR_PRODUCTO,
            "tipo_consumo": dict(Orden.TIPO_CONSUMO_CHOICES).get(tipo),
            "nombre": request.session.get(SESION_NOMBRE, ""),
        },
    )


@require_POST
def carrito(request):
    mesa_obj, sucursal_obj = _contexto(request)
    if not _puede_pedir(request, mesa_obj, sucursal_obj):
        return redirect("cliente:menu")
    seleccion = leer_cantidades(request.POST, _productos_de_sucursal(sucursal_obj))
    if not seleccion:
        messages.error(request, "Elige al menos un platillo para ir al apartado de compra.")
        return redirect("cliente:menu")
    request.session[SESION_CARRITO] = {str(p.pk): c for p, c in seleccion}
    request.session[SESION_NOMBRE] = request.POST.get("nombre", "").strip()[:150]
    return redirect("cliente:compra")


def compra(request):
    mesa_obj, sucursal_obj = _contexto(request)
    items = _carrito(request, sucursal_obj)
    if not _puede_pedir(request, mesa_obj, sucursal_obj) or not items:
        return redirect("cliente:menu")
    lineas = [(p, c, p.precio * c) for p, c in items]
    tipo = request.session.get(SESION_TIPO_CONSUMO, Orden.EN_RESTAURANTE)
    return render(request, "cliente/compra.html", {
        "mesa": mesa_obj,
        "sucursal": sucursal_obj,
        "lineas": lineas,
        "total": sum(sub for _, _, sub in lineas),
        "tipo_consumo": dict(Orden.TIPO_CONSUMO_CHOICES)[tipo],
        "nombre": request.session.get(SESION_NOMBRE, ""),
    })


def _registrar_pedido(request, orden):
    request.session.pop(SESION_CARRITO, None)
    pedidos = _pedidos_de_sesion(request)
    pedidos.append(orden.pk)
    request.session[SESION_PEDIDOS] = pedidos[-20:]
    if orden.estado == Orden.POR_CONFIRMAR:
        messages.success(request, "Pedido recibido. El restaurante lo confirmará en breve.")
    else:
        messages.success(request, "Pedido enviado a cocina.")
    return redirect("cliente:pedido", pk=orden.pk)


@require_POST
def autopedido(request):
    mesa_obj, sucursal_obj = _contexto(request)
    if sucursal_obj is None:
        messages.error(request, "Elige un restaurante o escanea el código QR de tu mesa para hacer un pedido.")
        return redirect("cliente:restaurantes")

    seleccion = leer_cantidades(request.POST, _productos_de_sucursal(sucursal_obj))
    if not seleccion:
        messages.error(request, "Elige al menos un platillo antes de enviar el pedido.")
        return redirect("cliente:menu")

    nombre = request.POST.get("nombre", "").strip()[:150]
    tipo = request.session.get(SESION_TIPO_CONSUMO, Orden.EN_RESTAURANTE)

    if mesa_obj is None:
        try:
            with transaction.atomic():
                cliente = obtener_cliente(sucursal_obj.restaurante, nombre)
                orden = crear_orden(
                    sucursal_obj, [(p.pk, c) for p, c in seleccion], Orden.ORIGEN_AUTOPEDIDO, tipo,
                    cliente=cliente, estado=Orden.POR_CONFIRMAR,
                )
        except ValidationError:
            messages.error(request, "Algún platillo dejó de estar disponible. Revisa tu pedido.")
            return redirect("cliente:menu")
        return _registrar_pedido(request, orden)

    with transaction.atomic():
        mesa_bloqueada = Mesa.objects.select_for_update().get(pk=mesa_obj.pk)
        if not _mesa_asignada(request, mesa_bloqueada) or mesa_bloqueada.orden_activa is not None:
            messages.error(request, "Esta mesa ya tiene un pedido en curso. Pide ayuda a tu mesero.")
            return redirect("cliente:menu")

        restaurante = mesa_bloqueada.sucursal.restaurante
        cliente = obtener_cliente(restaurante, nombre)
        orden = Orden.objects.create(
            mesa=mesa_bloqueada, cliente=cliente, origen=Orden.ORIGEN_AUTOPEDIDO, estado=Orden.PENDIENTE,
            tipo_consumo=tipo,
        )
        DetalleOrden.objects.bulk_create(
            DetalleOrden(orden=orden, producto=p, cantidad=c, precio_unitario=p.precio) for p, c in seleccion
        )
        mesa_bloqueada.estado = Mesa.OCUPADA
        mesa_bloqueada.save(update_fields=["estado"])

    return _registrar_pedido(request, orden)


def pedido(request, pk):
    if pk not in _pedidos_de_sesion(request):
        raise Http404("Pedido no encontrado")
    orden = get_object_or_404(
        Orden.objects.select_related("mesa", "sucursal__restaurante").prefetch_related("detalles__producto"), pk=pk
    )
    return render(request, "cliente/pedido.html", {"orden": orden, "mesa": orden.mesa, "sucursal": orden.sucursal})


def mis_pedidos(request):
    pedidos = _pedidos_de_sesion(request)
    if pedidos:
        return redirect("cliente:pedido", pk=pedidos[-1])
    return redirect("cliente:menu")


def retroalimentacion(request):
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


class RetroalimentacionListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "mesa__sucursal__restaurante"
    model = Retroalimentacion
    roles_permitidos = ROLES_ADMIN
    template_name = "cliente/retroalimentacion_list.html"
    context_object_name = "mensajes"
    queryset = Retroalimentacion.objects.select_related("mesa")


@require_POST
@rol_requerido(*ROLES_ADMIN)
def retroalimentacion_revisar(request, pk):
    item = get_object_or_404(filtrar(Retroalimentacion.objects, request, "mesa__sucursal__restaurante"), pk=pk)
    item.revisada = not item.revisada
    item.save(update_fields=["revisada", "actualizado_en"])
    return redirect("cliente:retroalimentacion_list")
