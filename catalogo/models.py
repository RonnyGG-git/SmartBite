from django.db import models

from core.models import TimestampedModel


class Categoria(TimestampedModel):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Producto(TimestampedModel):
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=255, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    url_imagen = models.URLField(blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    sucursal = models.ForeignKey(
        "restaurantes.Sucursal", on_delete=models.PROTECT, related_name="productos"
    )
    disponible = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
