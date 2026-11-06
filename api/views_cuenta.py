import logging

from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import restaurante_actual, restaurantes_accesibles
from cuentas import otp
from cuentas.forms import RegistroAdministradorForm, RegistroEmpleadoForm, RestablecerForm
from cuentas.models import CodigoVerificacion, Usuario

from .base import ConRestauranteMixin
from .serializers import TokenSerializer
from .serializers_movil import (
    EmailSerializer,
    MensajeSerializer,
    PerfilSerializer,
    RegistroEmpleadoSerializer,
    RegistroSerializer,
    RestablecerSerializer,
    SesionSerializer,
    VerificarSerializer,
)

logger = logging.getLogger(__name__)

MENSAJE_RECUPERAR = "Si el correo está registrado, te llegará un código de 4 dígitos."


def perfil(request, usuario):
    request.user = usuario
    contexto = {
        "restaurantes": restaurantes_accesibles(usuario).order_by("nombre"),
        "restaurante_actual": restaurante_actual(request),
    }
    return PerfilSerializer(usuario, context=contexto).data


def sesion(request, usuario):
    token, _ = Token.objects.get_or_create(user=usuario)
    return {"token": token.key, "usuario": perfil(request, usuario)}


def enviar_codigo_silencioso(usuario, proposito):
    try:
        otp.enviar_codigo(usuario, proposito)
    except otp.EsperaReenvio:
        return False
    except Exception:
        logger.exception("No se pudo enviar el código %s a %s", proposito, usuario.email)
        return False
    return True


def errores_de_form(form, campos=None):
    campos = campos or {}
    return ValidationError({campos.get(campo, campo): mensajes for campo, mensajes in form.errors.items()})


class PublicoMixin:
    permission_classes = [AllowAny]
    authentication_classes = []


@extend_schema(tags=["auth"], request=TokenSerializer, responses=SesionSerializer)
class LoginView(PublicoMixin, generics.GenericAPIView):
    serializer_class = TokenSerializer

    def post(self, request):
        email = str(request.data.get("email", "")).strip()
        clave = str(request.data.get("password", ""))
        pendiente = Usuario.objects.filter(email__iexact=email, email_verificado=False).first() if email else None
        if pendiente is not None and pendiente.check_password(clave):
            if otp.segundos_para_reenviar(pendiente, CodigoVerificacion.REGISTRO) == 0:
                enviar_codigo_silencioso(pendiente, CodigoVerificacion.REGISTRO)
            return Response(
                {"detail": "Antes de entrar, confirma tu correo.", "code": "correo_sin_verificar", "email": pendiente.email},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(sesion(request, serializer.validated_data["usuario"]))


class _RegistroBase(PublicoMixin, generics.GenericAPIView):
    form_class = None

    def post(self, request):
        datos = {clave: request.data.get(clave, "") for clave in self.form_class.base_fields}
        form = self.form_class(data=datos)
        if not form.is_valid():
            raise errores_de_form(form)
        usuario = form.save()
        enviado = enviar_codigo_silencioso(usuario, CodigoVerificacion.REGISTRO)
        return Response(
            {"email": usuario.email, "codigo_enviado": enviado,
             "detail": f"Te enviamos un código de 4 dígitos a {usuario.email}."},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["auth"], request=RegistroSerializer)
class RegistroAdministradorView(_RegistroBase):
    serializer_class = RegistroSerializer
    form_class = RegistroAdministradorForm


@extend_schema(tags=["auth"], request=RegistroEmpleadoSerializer)
class RegistroEmpleadoView(_RegistroBase):
    serializer_class = RegistroEmpleadoSerializer
    form_class = RegistroEmpleadoForm


@extend_schema(tags=["auth"], request=VerificarSerializer, responses=SesionSerializer)
class VerificarView(PublicoMixin, generics.GenericAPIView):
    serializer_class = VerificarSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        usuario = Usuario.objects.filter(email__iexact=datos["email"], email_verificado=False).first()
        resultado = otp.VENCIDO
        if usuario is not None:
            resultado = otp.verificar_codigo(usuario, CodigoVerificacion.REGISTRO, datos["codigo"])
        if resultado != otp.OK:
            raise ValidationError({"codigo": [otp.MENSAJES[resultado]]}, code=resultado)
        usuario.is_active = True
        usuario.email_verificado = True
        usuario.save(update_fields=["is_active", "email_verificado"])
        return Response(sesion(request, usuario))


@extend_schema(tags=["auth"], request=EmailSerializer, responses=MensajeSerializer)
class ReenviarVerificacionView(PublicoMixin, generics.GenericAPIView):
    serializer_class = EmailSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = Usuario.objects.filter(
            email__iexact=serializer.validated_data["email"], email_verificado=False
        ).first()
        if usuario is not None:
            espera = otp.segundos_para_reenviar(usuario, CodigoVerificacion.REGISTRO)
            if espera:
                return Response(
                    {"detail": f"Espera {espera} s para pedir otro código.", "code": "espera_reenvio", "segundos": espera},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            enviar_codigo_silencioso(usuario, CodigoVerificacion.REGISTRO)
        return Response({"detail": "Si la cuenta está pendiente, te llegará un código nuevo."})


@extend_schema(tags=["auth"], request=EmailSerializer, responses=MensajeSerializer)
class RecuperarView(PublicoMixin, generics.GenericAPIView):
    serializer_class = EmailSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = Usuario.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if usuario is not None and otp.segundos_para_reenviar(usuario, CodigoVerificacion.RECUPERACION) == 0:
            enviar_codigo_silencioso(usuario, CodigoVerificacion.RECUPERACION)
        return Response({"detail": MENSAJE_RECUPERAR})


@extend_schema(tags=["auth"], request=RestablecerSerializer, responses=MensajeSerializer)
class RecuperarConfirmarView(PublicoMixin, generics.GenericAPIView):
    serializer_class = RestablecerSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        usuario = Usuario.objects.filter(email__iexact=datos["email"], is_active=True).first()
        form = RestablecerForm(usuario or Usuario(email=datos["email"]), data={
            "codigo": datos["codigo"], "new_password1": datos["password1"], "new_password2": datos["password2"],
        })
        if not form.is_valid():
            raise errores_de_form(form, {"new_password1": "password1", "new_password2": "password2"})
        resultado = otp.INCORRECTO
        if usuario is not None:
            resultado = otp.verificar_codigo(usuario, CodigoVerificacion.RECUPERACION, datos["codigo"])
        if resultado != otp.OK:
            raise ValidationError({"codigo": [otp.MENSAJES[resultado]]}, code=resultado)
        form.save()
        Token.objects.filter(user=usuario).delete()
        return Response({"detail": "Contraseña actualizada. Ya puedes iniciar sesión."})


@extend_schema(tags=["auth"], request=None, responses={204: None})
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["auth"], responses=PerfilSerializer)
class PerfilView(ConRestauranteMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(perfil(request, request.user))
