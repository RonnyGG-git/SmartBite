from django.db import models

from core.models import TimestampedModel


class ProductoIngrediente(TimestampedModel):
    producto = models.ForeignKey(
        "catalogo.Producto", on_delete=models.CASCADE, related_name="ingredientes"
    )
    item_inventario = models.ForeignKey(
        "inventario.ItemInventario", on_delete=models.PROTECT, related_name="usado_en_recetas"
    )
    cantidad_requerida = models.DecimalField(max_digits=10, decimal_places=3)
    unidad_medida = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ("producto", "item_inventario")
        ordering = ["producto__nombre"]

    def __str__(self):
        return f"{self.producto.nombre} — {self.item_inventario.nombre}"
