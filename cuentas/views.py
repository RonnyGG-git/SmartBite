from django.contrib import messages
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import RolForm, RolPermisosForm, UsuarioCreateForm, UsuarioForm
from .models import Rol, Usuario

ROLES_ADMIN = ["ADMINISTRADOR"]


# Pantalla de inicio por rol: "/" (dashboard) es solo del Administrador, así que
# mandar a todos allí daba 403 a los demás roles justo después de loguearse.
INICIO_POR_ROL = {
    "ADMINISTRADOR": "reportes:dashboard",
    "MESERO": "operativo:mesas_list",
    "JEFE_COCINA": "cocina:cocina",
    "CAJERO": "caja:por_cobrar",
    "JEFE_INVENTARIO": "inventario:inventario_list",
}


class LoginView(DjangoLoginView):
    template_name = "cuentas/login.html"
    redirect_authenticated_user = True

    def get_redirect_url(self):
        # `next=/` solo aparece porque el usuario pegó la raíz; se ignora para
        # caer en la pantalla propia de su rol. Cualquier otro `next` se respeta.
        destino = super().get_redirect_url()
        return "" if destino == "/" else destino

    def get_default_redirect_url(self):
        usuario = self.request.user
        if usuario.is_superuser:
            return reverse_lazy("reportes:dashboard")
        nombre_rol = usuario.rol.nombre if usuario.rol_id else None
        return reverse_lazy(INICIO_POR_ROL.get(nombre_rol, "reportes:dashboard"))


class LogoutView(DjangoLogoutView):
    pass


class UsuarioListView(RoleRequiredMixin, ListView):
    model = Usuario
    roles_permitidos = ROLES_ADMIN
    template_name = "cuentas/usuarios_list.html"
    context_object_name = "usuarios"


class UsuarioCreateView(RoleRequiredMixin, CreateView):
    model = Usuario
    form_class = UsuarioCreateForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Usuario"}
    success_url = reverse_lazy("cuentas:usuarios_list")


class UsuarioUpdateView(RoleRequiredMixin, UpdateView):
    model = Usuario
    form_class = UsuarioForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Usuario"}
    success_url = reverse_lazy("cuentas:usuarios_list")


class UsuarioDeleteView(RoleRequiredMixin, DeleteView):
    model = Usuario
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("cuentas:usuarios_list")


@require_POST
def usuario_toggle_activo(request, pk):
    if not (request.user.is_superuser or (request.user.rol_id and request.user.rol.nombre in ROLES_ADMIN)):
        return redirect("cuentas:usuarios_list")
    usuario = get_object_or_404(Usuario, pk=pk)
    # H8: nadie puede desactivarse a sí mismo; evita dejar la cuenta
    # administrativa sin ningún administrador activo en la sucursal.
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta")
        return redirect("cuentas:usuarios_list")
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])
    return redirect("cuentas:usuarios_list")


class RolListView(RoleRequiredMixin, ListView):
    model = Rol
    roles_permitidos = ROLES_ADMIN
    template_name = "cuentas/roles_list.html"
    context_object_name = "roles"


class RolCreateView(RoleRequiredMixin, CreateView):
    model = Rol
    form_class = RolForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nuevo Rol"}
    success_url = reverse_lazy("cuentas:roles_list")


class RolUpdateView(RoleRequiredMixin, UpdateView):
    model = Rol
    form_class = RolForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Rol"}
    success_url = reverse_lazy("cuentas:roles_list")


class RolDeleteView(RoleRequiredMixin, DeleteView):
    model = Rol
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("cuentas:roles_list")


def rol_permisos(request, pk):
    if not (request.user.is_superuser or (request.user.rol_id and request.user.rol.nombre in ROLES_ADMIN)):
        return redirect("cuentas:roles_list")
    rol = get_object_or_404(Rol, pk=pk)
    if request.method == "POST":
        form = RolPermisosForm(request.POST)
        if form.is_valid():
            rol.permisos.set(form.cleaned_data["permisos"])
            return redirect("cuentas:roles_list")
    else:
        form = RolPermisosForm(initial={"permisos": rol.permisos.all()})
    return render(request, "cuentas/rol_permisos.html", {"rol": rol, "form": form})
