import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, FormView, ListView, TemplateView, UpdateView

from core.mixins import RoleRequiredMixin, SuperusuarioRequeridoMixin
from core.tenancy import limitar_opciones, restaurante_actual

from . import otp
from .forms import (
    CodigoForm,
    LoginForm,
    RecuperarForm,
    RegistroAdministradorForm,
    RegistroEmpleadoForm,
    RestablecerForm,
    RolForm,
    RolPermisosForm,
    UsuarioCreateForm,
    UsuarioForm,
    roles_de_empleado,
)
from .models import CodigoVerificacion, Rol, Usuario

logger = logging.getLogger(__name__)

ROLES_ADMIN = ["ADMINISTRADOR"]


INICIO_POR_ROL = {
    "ADMINISTRADOR": "reportes:dashboard",
    "MESERO": "operativo:mesas_list",
    "JEFE_COCINA": "cocina:cocina",
    "CAJERO": "caja:por_cobrar",
    "JEFE_INVENTARIO": "inventario:inventario_list",
}


def inicio_de(usuario):
    if usuario.is_superuser:
        return reverse_lazy("reportes:dashboard")
    if not usuario.rol_id:
        return reverse_lazy("cuentas:pendiente")
    return reverse_lazy(INICIO_POR_ROL.get(usuario.rol.nombre, "reportes:dashboard"))


SESION_VERIFICACION = "verificacion_usuario"
SESION_RECUPERACION = "recuperacion_email"


def enviar_con_aviso(request, usuario, proposito, aviso_exito=True):
    try:
        otp.enviar_codigo(usuario, proposito)
    except otp.EsperaReenvio as espera:
        messages.error(request, f"Espera {espera.segundos} s para pedir otro código.")
        return False
    except Exception:
        logger.exception("No se pudo enviar el código %s a %s", proposito, usuario.email)
        messages.error(request, "No pudimos enviar el correo. Intenta de nuevo en un momento.")
        return False
    if aviso_exito:
        messages.success(request, f"Te enviamos un código de 4 dígitos a {usuario.email}.")
    return True


def iniciar_verificacion(request, usuario):
    request.session[SESION_VERIFICACION] = usuario.pk
    if otp.segundos_para_reenviar(usuario, CodigoVerificacion.REGISTRO) == 0:
        enviar_con_aviso(request, usuario, CodigoVerificacion.REGISTRO)
    return redirect("cuentas:verificar")


def usuario_por_verificar(request):
    pk = request.session.get(SESION_VERIFICACION)
    if pk is None:
        return None
    return Usuario.objects.filter(pk=pk, email_verificado=False).first()


class LoginView(DjangoLoginView):
    template_name = "cuentas/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        if form.sin_verificar is not None:
            messages.info(self.request, "Antes de entrar, confirma tu correo.")
            return iniciar_verificacion(self.request, form.sin_verificar)
        return super().form_valid(form)

    def get_redirect_url(self):
        destino = super().get_redirect_url()
        return "" if destino == "/" else destino

    def get_default_redirect_url(self):
        return inicio_de(self.request.user)


class LogoutView(DjangoLogoutView):
    pass


class SoloVisitantesMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(inicio_de(request.user))
        return super().dispatch(request, *args, **kwargs)


class RegistroAdministradorView(SoloVisitantesMixin, CreateView):
    form_class = RegistroAdministradorForm
    template_name = "cuentas/registro.html"
    extra_context = {
        "titulo": "Crea tu cuenta de administrador",
        "subtitulo": "Después registras tus restaurantes y les das el código a tus empleados.",
    }

    def form_valid(self, form):
        return iniciar_verificacion(self.request, form.save())


class RegistroEmpleadoView(SoloVisitantesMixin, CreateView):
    form_class = RegistroEmpleadoForm
    template_name = "cuentas/registro.html"
    extra_context = {
        "titulo": "Entra a tu restaurante",
        "subtitulo": "Usa el código que te dio tu administrador.",
    }

    def form_valid(self, form):
        return iniciar_verificacion(self.request, form.save())


def verificar_correo(request):
    usuario = usuario_por_verificar(request)
    if usuario is None:
        return redirect("cuentas:login")
    form = CodigoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        resultado = otp.verificar_codigo(usuario, CodigoVerificacion.REGISTRO, form.cleaned_data["codigo"])
        if resultado == otp.OK:
            usuario.is_active = True
            usuario.email_verificado = True
            usuario.save(update_fields=["is_active", "email_verificado"])
            request.session.pop(SESION_VERIFICACION, None)
            login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            if usuario.rol_id and usuario.rol.nombre == "ADMINISTRADOR":
                messages.success(request, "Correo confirmado. Ahora registra tu restaurante.")
                return redirect("restaurantes:restaurante_crear")
            messages.success(request, "Correo confirmado.")
            return redirect(inicio_de(usuario))
        form.add_error("codigo", otp.MENSAJES[resultado])
    return render(request, "cuentas/verificar.html", {
        "form": form,
        "email": usuario.email,
        "espera": otp.segundos_para_reenviar(usuario, CodigoVerificacion.REGISTRO),
        "url_reenviar": reverse("cuentas:verificar_reenviar"),
    })


@require_POST
def reenviar_verificacion(request):
    usuario = usuario_por_verificar(request)
    if usuario is None:
        return redirect("cuentas:login")
    enviar_con_aviso(request, usuario, CodigoVerificacion.REGISTRO)
    return redirect("cuentas:verificar")


def usuario_a_recuperar(email):
    return Usuario.objects.filter(email__iexact=email, is_active=True).first() if email else None


class RecuperarView(SoloVisitantesMixin, FormView):
    form_class = RecuperarForm
    template_name = "cuentas/recuperar.html"

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        self.request.session[SESION_RECUPERACION] = email
        usuario = usuario_a_recuperar(email)
        if usuario is not None and otp.segundos_para_reenviar(usuario, CodigoVerificacion.RECUPERACION) == 0:
            try:
                otp.enviar_codigo(usuario, CodigoVerificacion.RECUPERACION)
            except Exception:
                logger.exception("No se pudo enviar el código de recuperación a %s", email)
        messages.info(self.request, "Si el correo está registrado, te llegará un código de 4 dígitos.")
        return redirect("cuentas:recuperar_codigo")


def recuperar_codigo(request):
    if request.user.is_authenticated:
        return redirect(inicio_de(request.user))
    email = request.session.get(SESION_RECUPERACION)
    if not email:
        return redirect("cuentas:recuperar")
    usuario = usuario_a_recuperar(email)
    form = RestablecerForm(usuario or Usuario(email=email), request.POST or None)
    if request.method == "POST" and form.is_valid():
        resultado = otp.INCORRECTO
        if usuario is not None:
            resultado = otp.verificar_codigo(usuario, CodigoVerificacion.RECUPERACION, form.cleaned_data["codigo"])
        if resultado == otp.OK:
            form.save()
            request.session.pop(SESION_RECUPERACION, None)
            messages.success(request, "Contraseña actualizada. Ya puedes iniciar sesión.")
            return redirect("cuentas:login")
        form.add_error("codigo", otp.MENSAJES[resultado])
    espera = otp.segundos_para_reenviar(usuario, CodigoVerificacion.RECUPERACION) if usuario else 0
    return render(request, "cuentas/recuperar_codigo.html", {
        "form": form,
        "email": email,
        "espera": espera,
        "url_reenviar": reverse("cuentas:recuperar_reenviar"),
    })


@require_POST
def reenviar_recuperacion(request):
    email = request.session.get(SESION_RECUPERACION)
    if not email:
        return redirect("cuentas:recuperar")
    usuario = usuario_a_recuperar(email)
    if usuario is not None:
        if enviar_con_aviso(request, usuario, CodigoVerificacion.RECUPERACION, aviso_exito=False):
            messages.info(request, "Si el correo está registrado, te llegará un código nuevo.")
    else:
        messages.info(request, "Si el correo está registrado, te llegará un código nuevo.")
    return redirect("cuentas:recuperar_codigo")


class PendienteView(LoginRequiredMixin, TemplateView):
    template_name = "cuentas/pendiente.html"

    def get(self, request, *args, **kwargs):
        if request.user.rol_id or request.user.is_superuser:
            return redirect(inicio_de(request.user))
        return super().get(request, *args, **kwargs)


def usuarios_del_restaurante(request, usuarios=None):
    usuarios = Usuario.objects.all() if usuarios is None else usuarios
    if request.user.is_superuser:
        return usuarios
    actual = restaurante_actual(request)
    if actual is None:
        return usuarios.none()
    return usuarios.filter(
        Q(restaurante=actual) | Q(sucursal__restaurante=actual) | Q(restaurantes_administrados=actual)
    ).distinct()


class UsuariosDelRestauranteMixin:
    def get_queryset(self):
        return usuarios_del_restaurante(self.request, super().get_queryset())

    def get_form(self, form_class=None):
        form = limitar_opciones(super().get_form(form_class), self.request)
        if not self.request.user.is_superuser:
            form.fields["rol"].queryset = roles_de_empleado()
        return form

    def form_valid(self, form):
        if form.instance.pk is None and form.instance.restaurante_id is None:
            form.instance.restaurante = restaurante_actual(self.request)
        return super().form_valid(form)


class UsuarioListView(UsuariosDelRestauranteMixin, RoleRequiredMixin, ListView):
    model = Usuario
    roles_permitidos = ROLES_ADMIN
    template_name = "cuentas/usuarios_list.html"
    context_object_name = "usuarios"


class UsuarioCreateView(UsuariosDelRestauranteMixin, RoleRequiredMixin, CreateView):
    model = Usuario
    form_class = UsuarioCreateForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Usuario"}
    success_url = reverse_lazy("cuentas:usuarios_list")


class UsuarioUpdateView(UsuariosDelRestauranteMixin, RoleRequiredMixin, UpdateView):
    model = Usuario
    form_class = UsuarioForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Usuario"}
    success_url = reverse_lazy("cuentas:usuarios_list")


class UsuarioDeleteView(UsuariosDelRestauranteMixin, RoleRequiredMixin, DeleteView):
    model = Usuario
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("cuentas:usuarios_list")


@require_POST
def usuario_toggle_activo(request, pk):
    if not (request.user.is_superuser or (request.user.rol_id and request.user.rol.nombre in ROLES_ADMIN)):
        return redirect("cuentas:usuarios_list")
    usuario = get_object_or_404(usuarios_del_restaurante(request), pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta")
        return redirect("cuentas:usuarios_list")
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])
    return redirect("cuentas:usuarios_list")


class RolListView(SuperusuarioRequeridoMixin, ListView):
    model = Rol
    template_name = "cuentas/roles_list.html"
    context_object_name = "roles"


class RolCreateView(SuperusuarioRequeridoMixin, CreateView):
    model = Rol
    form_class = RolForm
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Rol"}
    success_url = reverse_lazy("cuentas:roles_list")


class RolUpdateView(SuperusuarioRequeridoMixin, UpdateView):
    model = Rol
    form_class = RolForm
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Rol"}
    success_url = reverse_lazy("cuentas:roles_list")


class RolDeleteView(SuperusuarioRequeridoMixin, DeleteView):
    model = Rol
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("cuentas:roles_list")


def rol_permisos(request, pk):
    if not request.user.is_superuser:
        return redirect("cuentas:usuarios_list")
    rol = get_object_or_404(Rol, pk=pk)
    if request.method == "POST":
        form = RolPermisosForm(request.POST)
        if form.is_valid():
            rol.permisos.set(form.cleaned_data["permisos"])
            return redirect("cuentas:roles_list")
    else:
        form = RolPermisosForm(initial={"permisos": rol.permisos.all()})
    return render(request, "cuentas/rol_permisos.html", {"rol": rol, "form": form})
