from django.db import models

from core.models import TimestampedModel


class Categoria(TimestampedModel):
    nombre = models.CharField(max_length=100)
    restaurante = models.ForeignKey(
        "restaurantes.Restaurante", on_delete=models.CASCADE, related_name="categorias", null=True, blank=True
    )

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["restaurante", "nombre"], name="unique_categoria_por_restaurante"),
        ]

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
        constraints = [
            models.UniqueConstraint(
                fields=["nombre", "sucursal"],
                name="unique_producto_nombre_por_sucursal",
            ),
        ]

    def __str__(self):
        return self.nombre
