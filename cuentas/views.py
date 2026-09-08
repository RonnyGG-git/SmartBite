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


class LoginView(DjangoLoginView):
    template_name = "cuentas/login.html"
    redirect_authenticated_user = True


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
