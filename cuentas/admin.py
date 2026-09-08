from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Permiso, Rol, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    model = Usuario
    ordering = ["email"]
    list_display = ("email", "nombre", "rol", "sucursal", "is_active", "is_staff")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("nombre", "rol", "sucursal")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "nombre", "password1", "password2")}),
    )
    search_fields = ("email", "nombre")


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    filter_horizontal = ("permisos",)


@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "recurso", "activo")
    list_filter = ("recurso", "activo")
    search_fields = ("nombre", "recurso")
