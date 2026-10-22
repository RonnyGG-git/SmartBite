from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from cliente.views import _productos_disponibles
from core.tenancy import filtrar
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
    queryset = ItemInventario.objects.select_related("sucursal").order_by("nombre")

    def get_queryset(self):
        return filtrar(super().get_queryset(), self.request, "sucursal__restaurante")

    @property
    def roles_permitidos(self):
        return ROLES_INVENTARIO if self.action == "ajustar" else ROLES_LECTURA

    def get_serializer_class(self):
        return AjusteStockSerializer if self.action == "ajustar" else ItemInventarioSerializer

    @extend_schema(request=AjusteStockSerializer, responses={201: AjusteStockRespuestaSerializer})
    @action(detail=True, methods=["post"])
    def ajustar(self, request, pk=None):
        item = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        movimiento = item.ajustar_stock(datos["tipo"], datos["cantidad"], datos["motivo"])
        return Response(
            {"item": ItemInventarioSerializer(item).data, "movimiento": MovimientoInventarioSerializer(movimiento).data},
            status=status.HTTP_201_CREATED,
        )
