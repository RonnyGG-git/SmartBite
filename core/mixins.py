from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


def usuario_tiene_rol(usuario, roles):
    """True si el usuario es superusuario o su rol está en `roles`.
    Misma regla que usan RoleRequiredMixin y rol_requerido, para decidir en
    templates/vistas qué acciones mostrar sin duplicar la condición."""
    if not usuario.is_authenticated:
        return False
    return usuario.is_superuser or (bool(usuario.rol_id) and usuario.rol.nombre in roles)


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Reemplaza a RutaProtegida.jsx: restringe una vista a una lista de roles.

    Uso:
        class ProductoListView(RoleRequiredMixin, ListView):
            roles_permitidos = ["ADMINISTRADOR", "JEFE_INVENTARIO"]
    """

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


def rol_requerido(*roles_permitidos):
    """Versión para vistas basadas en función, equivalente a RoleRequiredMixin."""
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
