from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


def usuario_tiene_rol(usuario, roles):
    if not usuario.is_authenticated:
        return False
    return usuario.is_superuser or (bool(usuario.rol_id) and usuario.rol.nombre in roles)


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    roles_permitidos = []

    def test_func(self):
        usuario = self.request.user
        if not usuario.is_authenticated:
            return False
        if usuario.is_superuser:
            return True
        if not self.roles_permitidos:
            return True
        return bool(usuario.rol_id) and usuario.rol.nombre in self.roles_permitidos


class SuperusuarioRequeridoMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


def rol_requerido(*roles_permitidos):
    from functools import wraps
    from django.contrib.auth.decorators import login_required
    from django.core.exceptions import PermissionDenied

    def decorador(vista):
        @login_required
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            usuario = request.user
            permitido = (
                usuario.is_superuser
                or not roles_permitidos
                or (usuario.rol_id and usuario.rol.nombre in roles_permitidos)
            )
            if not permitido:
                raise PermissionDenied("No tienes permisos para acceder a esta sección.")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
