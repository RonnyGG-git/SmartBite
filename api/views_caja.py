from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from caja import servicios
from caja.models import Factura, MetodoPago, Pago
from caja.pasarelas import url_absoluta
from caja.qr import obtener_enlace_pago
from caja.servicios import CobroInvalido
from caja.views import ROLES_CAJA
from caja.vistas_qr import _qr_base64
from core.tenancy import filtrar
from operativo.models import Orden

from .base import ConRestauranteMixin
from .serializers_caja import (
    CobrarSerializer,
    CuentaSerializer,
    FacturaResumenSerializer,
    FacturaSerializer,
    MetodoPagoSerializer,
)
from .serializers_movil import OrdenSerializer
from .views_operacion import ordenes_del_restaurante


def _ip(request):
    return request.META.get("REMOTE_ADDR")


class CajaMixin(ConRestauranteMixin):
    roles_permitidos = ROLES_CAJA

    def orden(self, pk):
        return get_object_or_404(ordenes_del_restaurante(self.request), pk=pk)

    def cuenta(self, orden, codigo=status.HTTP_200_OK, **extra):
        orden = ordenes_del_restaurante(self.request).get(pk=orden.pk)
        datos = CuentaSerializer(orden).data
        datos.update(extra)
        return Response(datos, status=codigo)


@extend_schema(tags=["caja"])
class MetodosPagoView(CajaMixin, generics.ListAPIView):
    serializer_class = MetodoPagoSerializer
    pagination_class = None
    queryset = MetodoPago.objects.filter(activo=True)


@extend_schema(tags=["caja"], responses=CuentaSerializer)
class CuentaView(CajaMixin, APIView):
    def get(self, request, pk):
        return self.cuenta(self.orden(pk))


@extend_schema(tags=["caja"], request=CobrarSerializer, responses=CuentaSerializer)
class CobrarView(CajaMixin, APIView):
    def post(self, request, pk):
        orden = self.orden(pk)
        if not orden.cobrable:
            raise ValidationError(
                "La orden aún no está lista para cobrar." if orden.mesa_id else "Esta orden no está disponible para cobro.",
                code="no_cobrable",
            )
        entrada = CobrarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        metodo, monto, propina = datos["metodo"], datos["monto"], datos["propina"]
        try:
            if metodo.requiere_pasarela:
                pago, pasarela = servicios.iniciar_cobro_tarjeta(
                    orden.pk, metodo=metodo, monto=monto, propina=propina, usuario=request.user, ip=_ip(request), origen="app",
                )
                checkout = pasarela.url_checkout(request, pago)
                return self.cuenta(orden, status.HTTP_202_ACCEPTED, checkout=url_absoluta(request, checkout) if checkout.startswith("/") else checkout)
            servicios.registrar_pago_manual(
                orden.pk, metodo=metodo, monto=monto, propina=propina,
                referencia=datos["referencia"], usuario=request.user, ip=_ip(request),
            )
        except CobroInvalido as error:
            raise ValidationError(str(error), code="cobro_invalido")
        recibido = datos.get("efectivo_recibido")
        cambio = recibido - monto - propina if recibido and recibido > monto + propina else None
        return self.cuenta(orden, status.HTTP_201_CREATED, cambio=str(cambio) if cambio is not None else None)


@extend_schema(tags=["caja"])
class QrCobroView(CajaMixin, APIView):
    def post(self, request, pk):
        orden = self.orden(pk)
        if orden.es_final:
            raise ValidationError("La orden ya está cerrada.", code="orden_final")
        enlace = obtener_enlace_pago(orden, request.user)
        url = url_absoluta(request, reverse("caja:pagar_cliente", args=[enlace.token]))
        return Response({
            "url": url, "qr_png_base64": _qr_base64(url), "expira_en": enlace.expira_en,
            "saldo_pendiente": str(servicios.saldo_pendiente(orden)),
        })


class _CambioParaLlevar(CajaMixin, APIView):
    destino = None

    def post(self, request, pk):
        orden = self.orden(pk)
        if orden.estado != Orden.POR_CONFIRMAR or orden.mesa_id is not None:
            raise ValidationError("Solo se aceptan o rechazan pedidos sin mesa por confirmar.", code="no_por_confirmar")
        orden.cambiar_estado(self.destino)
        return Response(OrdenSerializer(ordenes_del_restaurante(request).get(pk=orden.pk)).data)


@extend_schema(tags=["caja"], request=None, responses=OrdenSerializer)
class AceptarParaLlevarView(_CambioParaLlevar):
    destino = Orden.PENDIENTE


@extend_schema(tags=["caja"], request=None, responses=OrdenSerializer)
class RechazarParaLlevarView(_CambioParaLlevar):
    destino = Orden.CANCELADA


@extend_schema(tags=["caja"])
class VentasView(CajaMixin, generics.ListAPIView):
    serializer_class = OrdenSerializer

    def get_queryset(self):
        return ordenes_del_restaurante(self.request).filter(pagos__estado=Pago.APROBADO).distinct().order_by("-actualizado_en")


@extend_schema(tags=["caja"])
class FacturasView(CajaMixin, generics.ListAPIView):
    serializer_class = FacturaResumenSerializer

    def get_queryset(self):
        return filtrar(Factura.objects, self.request, "orden__sucursal__restaurante").order_by("-numero")


@extend_schema(tags=["caja"])
class FacturaDetalleView(CajaMixin, generics.RetrieveAPIView):
    serializer_class = FacturaSerializer

    def get_queryset(self):
        return filtrar(Factura.objects, self.request, "orden__sucursal__restaurante")
