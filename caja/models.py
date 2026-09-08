from django.db import models

from core.models import TimestampedModel


class MetodoPago(TimestampedModel):
    nombre = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Pago(TimestampedModel):
    orden = models.ForeignKey("operativo.Orden", on_delete=models.PROTECT, related_name="pagos")
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name="pagos")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    referencia_transaccion = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Pago #{self.pk} — Orden #{self.orden_id}"
