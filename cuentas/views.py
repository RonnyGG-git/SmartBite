from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from core.mixins import RoleRequiredMixin, SuperusuarioRequeridoMixin
from core.tenancy import limitar_opciones, restaurante_actual

from .forms import (
    RegistroAdministradorForm,
    RegistroEmpleadoForm,
    RolForm,
    RolPermisosForm,
    UsuarioCreateForm,
    UsuarioForm,
    roles_de_empleado,
)
from .models import Rol, Usuario

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


class LoginView(DjangoLoginView):
    template_name = "cuentas/login.html"
    redirect_authenticated_user = True

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
        usuario = form.save()
        login(self.request, usuario)
        messages.success(self.request, "Cuenta creada. Ahora registra tu restaurante.")
        return redirect("restaurantes:restaurante_crear")


class RegistroEmpleadoView(SoloVisitantesMixin, CreateView):
    form_class = RegistroEmpleadoForm
    template_name = "cuentas/registro.html"
    extra_context = {
        "titulo": "Entra a tu restaurante",
        "subtitulo": "Usa el código que te dio tu administrador.",
    }

    def form_valid(self, form):
        usuario = form.save()
        login(self.request, usuario)
        return redirect("cuentas:pendiente")


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
