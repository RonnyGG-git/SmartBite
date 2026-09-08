from django.db import models

from core.models import TimestampedModel


class Restaurante(TimestampedModel):
    nombre = models.CharField(max_length=150)
    nif = models.CharField("NIF", max_length=30, unique=True)
    email = models.EmailField()
    direccion = models.CharField(max_length=255)
    telefono = models.CharField(max_length=30, blank=True)
    telefono_secundario = models.CharField(max_length=30, blank=True)
    logo_url = models.URLField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Sucursal(TimestampedModel):
    restaurante = models.ForeignKey(Restaurante, on_delete=models.CASCADE, related_name="sucursales")
    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
