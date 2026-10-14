<<<<<<< Updated upstream
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from cliente.views import _productos_disponibles
from inventario.models import ItemInventario
from inventario.views import ROLES_INVENTARIO, ROLES_LECTURA
from operativo.models import Mesa

from .serializers import (
    AjusteStockRespuestaSerializer,
    AjusteStockSerializer,
    ItemInventarioSerializer,
    MovimientoInventarioSerializer,
    ProductoMenuSerializer,
    TokenRespuestaSerializer,
    TokenSerializer,
)


class TokenView(generics.GenericAPIView):
    """Devuelve el token del usuario (lo crea la primera vez).

    Se manda en cada pedido como `Authorization: Token <token>`; es lo que usa
    Postman, porque la sesión web exige además el token CSRF en los POST.
    """

    serializer_class = TokenSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=TokenRespuestaSerializer, tags=["auth"])
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token, _ = Token.objects.get_or_create(user=serializer.validated_data["usuario"])
        return Response({"token": token.key})


@extend_schema(
    tags=["menu"],
    parameters=[
        OpenApiParameter(
            "mesa", int, required=False,
            description="Id de la mesa (el del QR): solo platillos de su sucursal.",
        )
    ],
)
class MenuView(generics.ListAPIView):
    """CU-PED-01: platillos disponibles. Público y de solo lectura.

    Usa la misma consulta que el menú web del cliente (cliente.views), para no
    tener dos versiones de qué platillo se muestra.
    """

    serializer_class = ProductoMenuSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_queryset(self):
        mesa_id = self.request.query_params.get("mesa")
        if mesa_id is None:
            return _productos_disponibles(None)
        if not mesa_id.isdigit():
            raise ValidationError({"mesa": ["Debe ser el número de id de la mesa."]})
        mesa = Mesa.objects.select_related("sucursal").filter(pk=int(mesa_id), activa=True).first()
        if mesa is None:
            raise NotFound("La mesa no existe o no está activa.")
        return _productos_disponibles(mesa)


@extend_schema(tags=["inventario"])
class ItemInventarioViewSet(viewsets.ReadOnlyModelViewSet):
    """Ítems de inventario. Consultar: ROLES_LECTURA, como el listado web.
    Ajustar el stock: ROLES_INVENTARIO, como item_ajustar_stock."""

    queryset = ItemInventario.objects.select_related("sucursal").order_by("nombre")

    @property
    def roles_permitidos(self):
        return ROLES_INVENTARIO if self.action == "ajustar" else ROLES_LECTURA

    def get_serializer_class(self):
        return AjusteStockSerializer if self.action == "ajustar" else ItemInventarioSerializer

    @extend_schema(request=AjusteStockSerializer, responses={201: AjusteStockRespuestaSerializer})
    @action(detail=True, methods=["post"])
    def ajustar(self, request, pk=None):
        """Entrada o salida manual de stock; crea el MovimientoInventario.
        Misma regla que la vista web (ItemInventario.ajustar_stock)."""
        item = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        movimiento = item.ajustar_stock(datos["tipo"], datos["cantidad"], datos["motivo"])
        return Response(
            {"item": ItemInventarioSerializer(item).data, "movimiento": MovimientoInventarioSerializer(movimiento).data},
            status=status.HTTP_201_CREATED,
        )
=======
"""Endpoints mínimos para validar la infraestructura de la API.

No son endpoints de negocio: existen para comprobar que el manejador global de
excepciones traduce lo que lanza el dominio a respuestas HTTP correctas.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from operativo.models import Orden


class EndpointDePruebaView(APIView):
    """Lanza un ValidationError de Django crudo, sin try/except en la vista.

    Es exactamente el escenario que antes producía un 500.
    """

    # Sondas de infraestructura, no datos de negocio: se dejan abiertas para
    # poder verificar el manejador sin montar auth. Los endpoints reales de la
    # API deben usar los permisos del proyecto (IsAuthenticated por defecto).
    permission_classes = [AllowAny]

    def get(self, request):
        raise DjangoValidationError("Prueba", code="error_test")


class EndpointDePruebaConDetalleView(APIView):
    """Lanza un ValidationError de Django con errores por campo (sin `code`).

    Reproduce lo que lanza un ModelForm/forms: código ausente y detalle en
    forma de diccionario. Sirve para fijar el contrato de ese caso.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        raise DjangoValidationError({"nombre": ["Este campo es obligatorio."]})


class EndpointDeErrorInesperadoView(APIView):
    """Lanza un RuntimeError, que NO es un error de validación.

    Sirve para fijar que el manejador no maquilla bugs como 400: debe dejar
    escapar la excepción para que se reporte como 500.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        raise RuntimeError("Fallo interno no relacionado con validación.")


class TransicionOrdenView(APIView):
    """Prueba de integración real: delega en el dominio sin try/except.

    Si la transición es inválida, `Orden.cambiar_estado` lanza
    `TransicionOrdenInvalida` (subclase de django.core.exceptions.ValidationError)
    y el manejador global debe traducirla a 400 con code="transicion_invalida".
    Esta vista no captura nada: ese es el punto.
    """

    permission_classes = [AllowAny]

    def post(self, request, pk):
        orden = Orden.objects.get(pk=pk)
        estado = request.data.get("estado")

        if not estado:
            raise DjangoValidationError(
                {"estado": ["Este campo es obligatorio."]}, code="estado_requerido"
            )

        # Sin try/except a propósito: el dominio manda y el manejador responde.
        orden.cambiar_estado(estado)

        return Response(
            {"id": orden.pk, "estado": orden.estado, "transiciones_disponibles": orden.transiciones_disponibles},
            status=status.HTTP_200_OK,
        )
>>>>>>> Stashed changes
