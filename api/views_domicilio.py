from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from cliente.views import _sucursales_publicas
from core.tenancy import filtrar
from cuentas.forms import RegistroClienteForm
from cuentas.models import CodigoVerificacion
from domicilio import services
from domicilio.models import DireccionCliente, Domicilio, PerfilCliente
from operativo.models import Mesa, Orden, Reserva
from operativo.services import crear_orden, obtener_cliente, sincronizar_reservas

from .base import ConRestauranteMixin
from .serializers_domicilio import (
    DireccionSerializer,
    DomicilioClienteSerializer,
    DomicilioSerializer,
    EntregarSerializer,
    PedidoDomicilioSerializer,
    PedidoMesaSerializer,
    PerfilClienteSerializer,
    PuntoSerializer,
    RegistroClienteSerializer,
)
from .serializers_movil import MensajeSerializer, OrdenSerializer, PedidoPublicoRespuestaSerializer
from .views_cuenta import PublicoMixin, enviar_codigo_silencioso, errores_de_form
from .views_publico import codigo_de

ROLES_CLIENTE = ["CLIENTE"]
ROLES_DOMICILIARIO = ["DOMICILIARIO", "ADMINISTRADOR"]

DOMICILIOS = Domicilio.objects.select_related(
    "orden__sucursal__restaurante", "orden__mesa", "orden__cliente", "cliente", "domiciliario"
).prefetch_related("orden__detalles__producto", "orden__pagos")


# ---------------------------------------------------------------- Cliente: cuenta


@extend_schema(tags=["cliente-cuenta"], request=RegistroClienteSerializer)
class RegistroClienteView(PublicoMixin, generics.GenericAPIView):
    serializer_class = RegistroClienteSerializer

    def post(self, request):
        datos = {clave: request.data.get(clave, "") for clave in RegistroClienteForm.base_fields}
        form = RegistroClienteForm(data=datos)
        if not form.is_valid():
            raise errores_de_form(form)
        with transaction.atomic():
            usuario = form.save()
            PerfilCliente.objects.update_or_create(
                usuario=usuario, defaults={"telefono": str(request.data.get("telefono", "")).strip()[:30]}
            )
        enviado = enviar_codigo_silencioso(usuario, CodigoVerificacion.REGISTRO)
        return Response(
            {"email": usuario.email, "codigo_enviado": enviado,
             "detail": f"Te enviamos un código de 4 dígitos a {usuario.email}."},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["cliente-cuenta"], request=PerfilClienteSerializer, responses=PerfilClienteSerializer)
class PerfilClienteView(APIView):
    roles_permitidos = ROLES_CLIENTE

    def _datos(self, usuario):
        perfil, _ = PerfilCliente.objects.get_or_create(usuario=usuario)
        return {"nombre": usuario.nombre, "email": usuario.email, "telefono": perfil.telefono, "documento": perfil.documento}

    def get(self, request):
        return Response(self._datos(request.user))

    def patch(self, request):
        serializer = PerfilClienteSerializer(data={**self._datos(request.user), **request.data}, partial=True)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        usuario = request.user
        with transaction.atomic():
            if "nombre" in datos:
                usuario.nombre = datos["nombre"].strip()
                usuario.save(update_fields=["nombre"])
            perfil, _ = PerfilCliente.objects.get_or_create(usuario=usuario)
            for campo in ("telefono", "documento"):
                if campo in datos:
                    setattr(perfil, campo, datos[campo].strip())
            perfil.save()
        return Response(self._datos(usuario))


@extend_schema(tags=["cliente-cuenta"])
class DireccionViewSet(viewsets.ModelViewSet):
    serializer_class = DireccionSerializer
    roles_permitidos = ROLES_CLIENTE
    pagination_class = None

    def get_queryset(self):
        return DireccionCliente.objects.filter(usuario=self.request.user)

    def _marcar_principal(self, direccion):
        if direccion.principal or not self.get_queryset().exclude(pk=direccion.pk).exists():
            self.get_queryset().exclude(pk=direccion.pk).update(principal=False)
            if not direccion.principal:
                direccion.principal = True
                direccion.save(update_fields=["principal"])

    def perform_create(self, serializer):
        with transaction.atomic():
            self._marcar_principal(serializer.save(usuario=self.request.user))

    def perform_update(self, serializer):
        with transaction.atomic():
            self._marcar_principal(serializer.save())


# ---------------------------------------------------------------- Cliente: pedidos a domicilio


@extend_schema(tags=["cliente-domicilio"])
class DomicilioClienteViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DomicilioClienteSerializer
    roles_permitidos = ROLES_CLIENTE

    def get_queryset(self):
        return DOMICILIOS.filter(cliente=self.request.user)

    @extend_schema(request=PedidoDomicilioSerializer, responses={201: DomicilioClienteSerializer})
    def create(self, request):
        serializer = PedidoDomicilioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        sucursal = _sucursales_publicas().filter(pk=datos["sucursal"]).first()
        if sucursal is None:
            raise ValidationError({"sucursal": ["Ese restaurante no está recibiendo pedidos."]})
        direccion = DireccionCliente.objects.filter(pk=datos["direccion"], usuario=request.user).first()
        if direccion is None:
            raise ValidationError({"direccion": ["Elige una de tus direcciones."]})
        perfil = PerfilCliente.objects.filter(usuario=request.user).first()
        telefono = (datos.get("telefono") or (perfil.telefono if perfil else "")).strip()
        if not telefono:
            raise ValidationError({"telefono": ["Agrega un teléfono para que el domiciliario pueda llamarte."]})
        lineas = [(linea["producto"], linea["cantidad"]) for linea in datos["lineas"]]
        try:
            domicilio = services.crear_pedido_domicilio(request.user, sucursal, lineas, direccion, telefono=telefono)
        except DjangoValidationError:
            raise ValidationError("Algún platillo dejó de estar disponible. Revisa tu pedido.", code="no_disponible")
        return Response(DomicilioClienteSerializer(DOMICILIOS.get(pk=domicilio.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        domicilio = self.get_object()
        services.cancelar_por_cliente(domicilio, request.user)
        return Response(DomicilioClienteSerializer(DOMICILIOS.get(pk=domicilio.pk)).data)


# ---------------------------------------------------------------- Cliente (con o sin cuenta): QR de la mesa


@extend_schema(tags=["cliente"], request=PedidoMesaSerializer, responses={201: PedidoPublicoRespuestaSerializer})
class PedidoMesaView(PublicoMixin, generics.GenericAPIView):
    serializer_class = PedidoMesaSerializer

    def get(self, request, pk):
        mesa = get_object_or_404(Mesa.objects.select_related("sucursal__restaurante"), pk=pk, activa=True)
        sincronizar_reservas(Reserva.objects.filter(mesa=mesa))
        mesa.refresh_from_db()
        return Response({
            "id": mesa.pk, "numero": mesa.numero, "estado": mesa.estado,
            "disponible": mesa.estado == Mesa.DISPONIBLE and mesa.orden_activa is None,
            "sucursal": {"id": mesa.sucursal_id, "nombre": mesa.sucursal.nombre, "restaurante": mesa.sucursal.restaurante.nombre},
        })

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        lineas = [(linea["producto"], linea["cantidad"]) for linea in datos["lineas"]]
        mesa = get_object_or_404(Mesa.objects.select_related("sucursal__restaurante"), pk=pk, activa=True)
        sincronizar_reservas(Reserva.objects.filter(mesa=mesa))
        with transaction.atomic():
            bloqueada = Mesa.objects.select_for_update().get(pk=mesa.pk)
            if bloqueada.estado == Mesa.RESERVADA:
                raise ValidationError("Esta mesa está reservada. Si la reserva es tuya, avísale al mesero.", code="mesa_reservada")
            if bloqueada.orden_activa is not None:
                raise ValidationError("Esta mesa ya tiene un pedido en curso. Pide ayuda a tu mesero.", code="mesa_ocupada")
            try:
                cliente = obtener_cliente(mesa.sucursal.restaurante, datos.get("nombre", ""))
                orden = crear_orden(
                    mesa.sucursal, lineas, Orden.ORIGEN_AUTOPEDIDO, datos["tipo_consumo"],
                    cliente=cliente, mesa=bloqueada, estado=Orden.PENDIENTE,
                )
            except DjangoValidationError:
                raise ValidationError("Algún platillo dejó de estar disponible. Revisa tu pedido.", code="no_disponible")
            bloqueada.estado = Mesa.OCUPADA
            bloqueada.save(update_fields=["estado"])
        orden = Orden.objects.select_related("mesa", "cliente").prefetch_related("detalles__producto", "pagos").get(pk=orden.pk)
        return Response({"codigo": codigo_de(orden), "orden": OrdenSerializer(orden).data}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------- Domiciliario


@extend_schema(tags=["domiciliario"])
class DomiciliarioViewSet(ConRestauranteMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DomicilioSerializer
    roles_permitidos = ROLES_DOMICILIARIO
    pagination_class = None

    def get_queryset(self):
        return filtrar(DOMICILIOS, self.request, "orden__sucursal__restaurante")

    def _responder(self, domicilio):
        return Response(DomicilioSerializer(DOMICILIOS.get(pk=domicilio.pk)).data)

    @action(detail=False)
    def disponibles(self, request):
        qs = self.get_queryset().filter(estado=Domicilio.LISTO_PARA_RECOGER, domiciliario__isnull=True).order_by("actualizado_en")
        return Response(DomicilioSerializer(qs, many=True).data)

    @action(detail=False)
    def mios(self, request):
        qs = self.get_queryset().filter(domiciliario=request.user)
        activos = list(qs.filter(estado__in=Domicilio.EN_RUTA).order_by("asignado_en"))
        terminados = list(qs.filter(estado__in=Domicilio.FINALES).order_by("-entregado_en")[:10])
        return Response(DomicilioSerializer(activos + terminados, many=True).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def tomar(self, request, pk=None):
        return self._responder(services.tomar(self.get_object(), request.user))

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def recoger(self, request, pk=None):
        return self._responder(services.recoger(self.get_object(), request.user))

    @extend_schema(request=PuntoSerializer, responses=MensajeSerializer)
    @action(detail=True, methods=["post"])
    def ubicacion(self, request, pk=None):
        serializer = PuntoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        services.actualizar_ubicacion(self.get_object(), request.user, d["latitud"], d["longitud"])
        return Response({"detail": "Ubicación actualizada."})

    @extend_schema(request=EntregarSerializer)
    @action(detail=True, methods=["post"])
    def entregar(self, request, pk=None):
        serializer = EntregarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._responder(services.confirmar_entrega(self.get_object(), request.user, serializer.validated_data["codigo"]))
