from rest_framework.permissions import BasePermission

from core.mixins import usuario_tiene_rol


class TieneRol(BasePermission):
    """Permiso por defecto de la API: la misma regla que RoleRequiredMixin.

    Cada vista declara `roles_permitidos` (las mismas listas que usa su vista
    web, por ejemplo inventario.views.ROLES_LECTURA). Sin lista, alcanza con
    estar autenticado. Así un rol no puede hacer por la API lo que no puede
    hacer en la web.
    """

    message = "Tu rol no tiene permiso para esta acción."

    def has_permission(self, request, view):
        roles = getattr(view, "roles_permitidos", None)
        if not roles:
            return bool(request.user and request.user.is_authenticated)
        return usuario_tiene_rol(request.user, roles)
