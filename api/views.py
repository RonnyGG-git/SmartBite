from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from cliente.views import _productos_disponibles
from inventario.models import ItemInventario
from inventario.views import ROLES_LECTURA
from operativo.models import Mesa

from .serializers import (
    ItemInventarioSerializer,
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
    """Ítems de inventario, solo lectura. Mismos roles que el listado web."""

    serializer_class = ItemInventarioSerializer
    roles_permitidos = ROLES_LECTURA
    queryset = ItemInventario.objects.select_related("sucursal").order_by("nombre")
