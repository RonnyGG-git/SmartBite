from rest_framework.permissions import BasePermission

from core.mixins import usuario_tiene_rol


class TieneRol(BasePermission):
    message = "Tu rol no tiene permiso para esta acción."

    def has_permission(self, request, view):
        roles = getattr(view, "roles_permitidos", None)
        if not roles:
            return bool(request.user and request.user.is_authenticated)
        return usuario_tiene_rol(request.user, roles)
