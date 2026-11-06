from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from caja.views import ROLES_CAJA, ROLES_ENTREGA
from catalogo.models import Producto
from cocina.services import iniciar_preparacion, marcar_lista
from cocina.views import ROLES_COCINA
from core.tenancy import filtrar
from operativo.models import DetalleOrden, Mesa, Orden, Reserva
from operativo.services import (
    abrir_orden_en_mesa,
    agregar_producto_a_orden,
    asignar_mesa_a_orden,
    cancelar_reserva,
    confirmar_llegada,
    obtener_cliente,
    sincronizar_reservas,
    solicitar_cuenta,
)
from operativo.views import ROLES_MESERO, ROLES_ORDEN, TRANSICIONES_MESERO

from .base import ConRestauranteMixin
from .serializers_movil import (
    AgregarProductoSerializer,
    AsignarMesaSerializer,
    CrearOrdenSerializer,
    IniciarPreparacionSerializer,
    MesaSerializer,
    OrdenCocinaSerializer,
    OrdenSerializer,
    ProductoSerializer,
    ReservaSerializer,
)

ROLES_EMPLEADOS = ["ADMINISTRADOR", "MESERO", "JEFE_COCINA", "CAJERO", "JEFE_INVENTARIO"]

DETALLES = Prefetch("detalles", queryset=DetalleOrden.objects.select_related("producto"))


def ordenes_del_restaurante(request):
    return (
        filtrar(Orden.objects, request, "sucursal__restaurante")
        .select_related("mesa", "cliente", "sucursal")
        .prefetch_related(DETALLES, "pagos")
    )


@extend_schema(tags=["mesero"])
class MesaListView(ConRestauranteMixin, generics.ListAPIView):
    serializer_class = MesaSerializer
    roles_permitidos = ROLES_MESERO
    pagination_class = None

    def get_queryset(self):
        sincronizar_reservas(filtrar(Reserva.objects, self.request, "mesa__sucursal__restaurante"))
        return (
            filtrar(Mesa.objects, self.request, "sucursal__restaurante")
            .filter(activa=True)
            .select_related("sucursal")
            .order_by("sucursal__nombre", "numero")
        )


@extend_schema(tags=["mesero"])
class ReservaViewSet(ConRestauranteMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ReservaSerializer
    roles_permitidos = ROLES_MESERO
    pagination_class = None

    def get_queryset(self):
        qs = filtrar(Reserva.objects, self.request, "mesa__sucursal__restaurante").select_related("mesa")
        if self.action == "list":
            return qs.filter(estado=Reserva.CONFIRMADA, fecha_hora__gte=timezone.now() - Reserva.TOLERANCIA)[:20]
        return qs

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def confirmar(self, request, pk=None):
        reserva = self.get_object()
        confirmar_llegada(reserva)
        return Response(ReservaSerializer(reserva).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        reserva = self.get_object()
        cancelar_reserva(reserva)
        return Response(ReservaSerializer(reserva).data)


@extend_schema(
    tags=["mesero"],
    parameters=[OpenApiParameter("sucursal", int, required=False)],
)
class ProductoListView(ConRestauranteMixin, generics.ListAPIView):
    serializer_class = ProductoSerializer
    roles_permitidos = ROLES_EMPLEADOS
    pagination_class = None

    def get_queryset(self):
        qs = (
            filtrar(Producto.objects, self.request, "sucursal__restaurante")
            .filter(disponible=True)
            .select_related("categoria")
            .order_by("categoria__nombre", "nombre")
        )
        sucursal = self.request.query_params.get("sucursal", "")
        if sucursal:
            if not sucursal.isdigit():
                raise ValidationError({"sucursal": ["Debe ser el id de la sucursal."]})
            qs = qs.filter(sucursal_id=int(sucursal))
        return qs


ROLES_POR_ACCION = {
    "list": ROLES_ORDEN,
    "retrieve": ROLES_ORDEN,
    "create": ROLES_MESERO,
    "detalles": ROLES_MESERO,
    "asignar_mesa": ROLES_MESERO,
    "solicitar_cuenta": ROLES_MESERO,
    "cancelar": ROLES_MESERO,
    "entregar": ROLES_ENTREGA,
}


@extend_schema(
    tags=["ordenes"],
    parameters=[
        OpenApiParameter("sin_mesa", bool, required=False, description="Solo pedidos sin mesa activos."),
        OpenApiParameter("activas", bool, required=False, description="Excluye entregadas y canceladas."),
    ],
)
class OrdenViewSet(
    ConRestauranteMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = OrdenSerializer

    @property
    def roles_permitidos(self):
        return ROLES_POR_ACCION.get(self.action, ROLES_ORDEN)

    def get_queryset(self):
        qs = ordenes_del_restaurante(self.request)
        if self.action != "list":
            return qs
        params = self.request.query_params
        if params.get("activas") in ("1", "true") or params.get("sin_mesa") in ("1", "true"):
            qs = qs.exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA])
        if params.get("sin_mesa") in ("1", "true"):
            qs = qs.filter(mesa__isnull=True).order_by("creado_en")
        return qs

    def _respuesta(self, orden, codigo=status.HTTP_200_OK):
        orden = ordenes_del_restaurante(self.request).get(pk=orden.pk)
        return Response(OrdenSerializer(orden).data, status=codigo)

    @extend_schema(request=CrearOrdenSerializer, responses={201: OrdenSerializer})
    def create(self, request):
        serializer = CrearOrdenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        mesa = get_object_or_404(
            filtrar(Mesa.objects, request, "sucursal__restaurante").filter(activa=True), pk=datos["mesa"]
        )
        cliente = obtener_cliente(
            mesa.sucursal.restaurante, datos.get("cliente_nombre", ""), (datos.get("cliente_telefono") or "").strip()
        )
        orden = abrir_orden_en_mesa(mesa.pk, cliente=cliente)
        return self._respuesta(orden, status.HTTP_201_CREATED)

    @extend_schema(request=AgregarProductoSerializer, responses={201: OrdenSerializer})
    @action(detail=True, methods=["post"])
    def detalles(self, request, pk=None):
        orden = self.get_object()
        serializer = AgregarProductoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        producto = Producto.objects.filter(
            pk=serializer.validated_data["producto"], disponible=True, sucursal=orden.sucursal_id
        ).first()
        if producto is None:
            raise ValidationError({"producto": ["Ese producto no está disponible en esta sucursal."]})
        agregar_producto_a_orden(orden, producto, serializer.validated_data["cantidad"])
        return self._respuesta(orden, status.HTTP_201_CREATED)

    @extend_schema(request=AsignarMesaSerializer)
    @action(detail=True, methods=["post"], url_path="asignar-mesa")
    def asignar_mesa(self, request, pk=None):
        orden = self.get_object()
        serializer = AsignarMesaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asignar_mesa_a_orden(orden, serializer.validated_data["mesa"])
        return self._respuesta(orden)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="solicitar-cuenta")
    def solicitar_cuenta(self, request, pk=None):
        orden = self.get_object()
        solicitar_cuenta(orden)
        return self._respuesta(orden)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        orden = self.get_object()
        if orden.estado not in TRANSICIONES_MESERO[Orden.CANCELADA]:
            raise ValidationError("Solo se pueden cancelar órdenes que todavía no entran a cocina.", code="transicion_invalida")
        orden.cambiar_estado(Orden.CANCELADA)
        return self._respuesta(orden)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def entregar(self, request, pk=None):
        orden = self.get_object()
        if orden.estado != Orden.LISTA:
            raise ValidationError("Solo se entregan órdenes que cocina marcó como listas.", code="orden_no_lista")
        if not orden.pagada:
            raise ValidationError(
                f"La orden #{orden.pk} no está pagada: cóbrala antes de entregarla.", code="orden_sin_pagar"
            )
        orden.cambiar_estado(Orden.ENTREGADA)
        return self._respuesta(orden)


@extend_schema(tags=["cocina"])
class CocinaViewSet(ConRestauranteMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = OrdenCocinaSerializer
    roles_permitidos = ROLES_COCINA
    pagination_class = None

    def get_queryset(self):
        return (
            filtrar(Orden.objects, self.request, "sucursal__restaurante")
            .filter(estado__in=[Orden.PENDIENTE, Orden.EN_PREPARACION])
            .select_related("mesa", "cliente")
            .prefetch_related("detalles__producto__ingredientes__item_inventario")
            .order_by("creado_en")
        )

    @extend_schema(request=IniciarPreparacionSerializer, responses=OrdenSerializer)
    @action(detail=True, methods=["post"])
    def iniciar(self, request, pk=None):
        orden = self.get_object()
        serializer = IniciarPreparacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        iniciar_preparacion(orden, serializer.validated_data["tiempo_estimado"])
        return Response(OrdenSerializer(ordenes_del_restaurante(request).get(pk=orden.pk)).data)

    @extend_schema(request=None, responses=OrdenSerializer)
    @action(detail=True, methods=["post"])
    def listo(self, request, pk=None):
        orden = self.get_object()
        marcar_lista(orden)
        return Response(OrdenSerializer(ordenes_del_restaurante(request).get(pk=orden.pk)).data)


@extend_schema(tags=["caja"])
class PorCobrarView(ConRestauranteMixin, generics.ListAPIView):
    serializer_class = OrdenSerializer
    roles_permitidos = ROLES_CAJA
    pagination_class = None

    def get_queryset(self):
        return (
            ordenes_del_restaurante(self.request)
            .filter(cuenta_solicitada_en__isnull=False)
            .exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA])
            .order_by("cuenta_solicitada_en")
        )


@extend_schema(tags=["caja"])
class ParaLlevarView(ConRestauranteMixin, generics.ListAPIView):
    serializer_class = OrdenSerializer
    roles_permitidos = ROLES_CAJA
    pagination_class = None

    def get_queryset(self):
        return (
            ordenes_del_restaurante(self.request)
            .filter(mesa__isnull=True)
            .exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA])
            .order_by("creado_en")
        )
