from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from caja import servicios as servicios_caja
from caja.pasarelas import url_absoluta
from caja.qr import obtener_enlace_pago, es_simulada
from cliente.views import _productos_de_sucursal, _sucursales_publicas, buscar_sucursales
from operativo.models import Orden
from operativo.services import crear_orden, obtener_cliente
from restaurantes.geo import leer_coordenadas

from .serializers_movil import (
    OrdenSerializer,
    PedidoPublicoRespuestaSerializer,
    PedidoPublicoSerializer,
    ProductoSerializer,
    SucursalPublicaSerializer,
)

SAL_PEDIDO = "api.pedido-publico"


def codigo_de(orden):
    return signing.dumps(orden.pk, salt=SAL_PEDIDO)


class PublicoMixin:
    permission_classes = [AllowAny]
    authentication_classes = []


@extend_schema(
    tags=["cliente"],
    parameters=[
        OpenApiParameter("q", str, required=False),
        OpenApiParameter("lat", float, required=False),
        OpenApiParameter("lng", float, required=False),
    ],
)
class SucursalPublicaListView(PublicoMixin, generics.ListAPIView):
    serializer_class = SucursalPublicaSerializer
    pagination_class = None

    def get_queryset(self):
        params = self.request.query_params
        busqueda = params.get("q", "").strip()[:80]
        return buscar_sucursales(busqueda, leer_coordenadas(params.get("lat"), params.get("lng")))


@extend_schema(tags=["cliente"])
class MenuSucursalView(PublicoMixin, generics.ListAPIView):
    serializer_class = ProductoSerializer
    pagination_class = None

    def get_queryset(self):
        sucursal = get_object_or_404(_sucursales_publicas(), pk=self.kwargs["pk"])
        return _productos_de_sucursal(sucursal)


@extend_schema(tags=["cliente"], request=PedidoPublicoSerializer, responses={201: PedidoPublicoRespuestaSerializer})
class PedidoPublicoCrearView(PublicoMixin, generics.GenericAPIView):
    serializer_class = PedidoPublicoSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        sucursal = _sucursales_publicas().filter(pk=datos["sucursal"]).first()
        if sucursal is None:
            raise ValidationError({"sucursal": ["Ese restaurante no está recibiendo pedidos."]})
        lineas = [(linea["producto"], linea["cantidad"]) for linea in datos["lineas"]]
        try:
            with transaction.atomic():
                cliente = obtener_cliente(sucursal.restaurante, datos.get("nombre", ""))
                orden = crear_orden(
                    sucursal, lineas, Orden.ORIGEN_AUTOPEDIDO, datos["tipo_consumo"],
                    cliente=cliente, estado=Orden.POR_CONFIRMAR,
                )
        except DjangoValidationError:
            raise ValidationError("Algún platillo dejó de estar disponible. Revisa tu pedido.", code="no_disponible")
        orden = Orden.objects.select_related("mesa", "cliente").prefetch_related("detalles__producto", "pagos").get(pk=orden.pk)
        return Response({"codigo": codigo_de(orden), "orden": OrdenSerializer(orden).data}, status=status.HTTP_201_CREATED)


@extend_schema(tags=["cliente"], responses=OrdenSerializer)
class PedidoPublicoDetalleView(PublicoMixin, generics.GenericAPIView):
    serializer_class = OrdenSerializer

    def get(self, request, codigo):
        try:
            pk = signing.loads(codigo, salt=SAL_PEDIDO)
        except signing.BadSignature:
            raise NotFound("Pedido no encontrado.")
        orden = get_object_or_404(
            Orden.objects.select_related("mesa", "cliente").prefetch_related("detalles__producto", "pagos"), pk=pk
        )
        return Response(OrdenSerializer(orden).data)


@extend_schema(tags=["cliente"], request=None)
class PagoPedidoPublicoView(PublicoMixin, generics.GenericAPIView):
    def post(self, request, codigo):
        try:
            pk = signing.loads(codigo, salt=SAL_PEDIDO)
        except signing.BadSignature:
            raise NotFound("Pedido no encontrado.")
        orden = get_object_or_404(Orden.objects.prefetch_related("detalles", "pagos"), pk=pk)
        if orden.es_final:
            raise ValidationError("Este pedido ya está cerrado.", code="orden_final")
        if orden.estado == Orden.POR_CONFIRMAR:
            raise ValidationError("Podrás pagar cuando el restaurante confirme tu pedido.", code="por_confirmar")
        if orden.pagada:
            raise ValidationError("Este pedido ya está pagado.", code="ya_pagada")
        enlace = obtener_enlace_pago(orden)
        return Response({
            "url": url_absoluta(request, reverse("caja:pagar_cliente", args=[enlace.token])),
            "expira_en": enlace.expira_en,
            "saldo_pendiente": str(servicios_caja.saldo_pendiente(orden)),
            "en_linea": "simulada" if es_simulada() else "wompi",
        })
