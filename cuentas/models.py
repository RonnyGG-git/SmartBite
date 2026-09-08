from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from core.models import TimestampedModel

ROLES_SISTEMA = [
    ("ADMINISTRADOR", "Administrador"),
    ("JEFE_INVENTARIO", "Jefe de Inventario"),
    ("JEFE_COCINA", "Jefe de Cocina"),
    ("MESERO", "Mesero"),
    ("CAJERO", "Cajero"),
]


class Permiso(TimestampedModel):
    """Catálogo de permisos granulares (equivalente a los `authorities` del JWT
    actual, ej. CREAR_PRODUCTO, ACTUALIZAR_STOCK)."""

    nombre = models.CharField(max_length=100, unique=True)
    recurso = models.CharField(max_length=100, help_text="Módulo al que pertenece, ej: Productos")
    descripcion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["recurso", "nombre"]

    def __str__(self):
        return self.nombre


class Rol(TimestampedModel):
    nombre = models.CharField(max_length=30, choices=ROLES_SISTEMA, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    permisos = models.ManyToManyField(Permiso, related_name="roles", blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.get_nombre_display()


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nombre, password=None, **extra_fields):
        if not email:
            raise ValueError("El usuario debe tener un email")
        email = self.normalize_email(email)
        usuario = self.model(email=email, nombre=nombre, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, nombre, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, nombre, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Reemplaza el usuario del backend actual + lo guardado en localStorage
    (token/rol/email/usuarioId/sucursalId) por un modelo real con sesión de Django."""

    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=150)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="usuarios", null=True, blank=True)
    sucursal = models.ForeignKey(
        "restaurantes.Sucursal", on_delete=models.SET_NULL, related_name="usuarios", null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.email})"

    def tiene_permiso(self, nombre_permiso):
        if self.is_superuser:
            return True
        return self.rol_id and self.rol.permisos.filter(nombre=nombre_permiso, activo=True).exists()
