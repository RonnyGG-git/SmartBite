from django.db import models
from django.urls import reverse

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


class ImagenProducto(models.Model):
    producto = models.OneToOneField("Producto", on_delete=models.CASCADE, primary_key=True, related_name="imagen")
    datos = models.BinaryField()


class Producto(TimestampedModel):
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=255, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    url_imagen = models.URLField(max_length=1000, blank=True)
    imagen_version = models.PositiveIntegerField(default=0, editable=False)
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

    @property
    def imagen_src(self):
        if self.imagen_version:
            return f"{reverse('catalogo:producto_imagen', args=[self.pk])}?v={self.imagen_version}"
        return self.url_imagen
