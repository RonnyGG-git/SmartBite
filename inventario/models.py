from django.db import models

from core.models import TimestampedModel

UNIDADES_MEDIDA = [
    ("kg", "Kilogramo"), ("g", "Gramo"), ("L", "Litro"),
    ("ml", "Mililitro"), ("unidad", "Unidad"),
    ("caja", "Caja"), ("paquete", "Paquete"),
]


class Proveedor(TimestampedModel):
    nombre = models.CharField(max_length=150)
    contacto = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ItemInventario(TimestampedModel):
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=255, blank=True)
    unidad_medida = models.CharField(max_length=20, choices=UNIDADES_MEDIDA, default="unidad")
    stock_actual = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=0)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ubicacion = models.CharField(max_length=150, blank=True)
    sucursal = models.ForeignKey(
        "restaurantes.Sucursal", on_delete=models.PROTECT, related_name="items_inventario"
    )

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def stock_bajo(self):
        return self.stock_actual <= self.stock_minimo


class MovimientoInventario(TimestampedModel):
    ENTRADA, SALIDA = "ENTRADA", "SALIDA"
    TIPO_CHOICES = [(ENTRADA, "Entrada"), (SALIDA, "Salida")]

    item = models.ForeignKey(ItemInventario, on_delete=models.CASCADE, related_name="movimientos")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    cantidad = models.PositiveIntegerField()
    motivo = models.CharField(max_length=255)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.tipo} {self.cantidad} — {self.item.nombre}"


class Compra(TimestampedModel):
    PENDIENTE, RECIBIDA, ANULADA = "PENDIENTE", "RECIBIDA", "ANULADA"
    ESTADO_CHOICES = [(PENDIENTE, "Pendiente"), (RECIBIDA, "Recibida"), (ANULADA, "Anulada")]

    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="compras")
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=PENDIENTE)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Compra #{self.pk} — {self.proveedor.nombre}"

    @property
    def total(self):
        return sum((d.subtotal for d in self.detalles.all()), 0)


class DetalleCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="detalles")
    item = models.ForeignKey(ItemInventario, on_delete=models.PROTECT, related_name="detalles_compra")
    cantidad = models.PositiveIntegerField()
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.cantidad * self.costo_unitario

    def __str__(self):
        return f"{self.item.nombre} x{self.cantidad}"
