from django.core.exceptions import ValidationError
from django.db import models, transaction

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
    # Campos que ya exige la migración 0002 (antes existían solo en la BD).
    activo = models.BooleanField(default=True)
    categoria = models.CharField(max_length=50, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def ajustar_stock(self, tipo, cantidad, motivo):
        """Ajusta el stock y deja el movimiento registrado, todo en una transacción.

        ENTRADA suma; SALIDA y PERDIDA restan con piso en 0 (nunca deja stock
        negativo, porque la merma o el consumo no pueden inventar unidades).
        Devuelve el MovimientoInventario creado.

        Es la única puerta de entrada al stock: la usan tanto el formulario de
        ajuste como `inventario.services.descontar_insumos_por_receta`, para
        que una orden en marcha no pueda descuadrar el inventario a medias.
        """
        validos = dict(MovimientoInventario.TIPO_CHOICES)
        if tipo not in validos:
            raise ValidationError(
                {"tipo": f"Tipo de movimiento inválido: {tipo!r}."},
                code="tipo_movimiento_invalido",
            )
        if cantidad is None or cantidad <= 0:
            raise ValidationError(
                {"cantidad": "La cantidad debe ser un entero positivo."},
                code="cantidad_invalida",
            )

        with transaction.atomic():
            # select_for_update serializa ajustes concurrentes sobre el mismo
            # ítem: dos cajeros ajustando a la vez no pueden pisarse.
            item = ItemInventario.objects.select_for_update().get(pk=self.pk)
            if tipo == MovimientoInventario.ENTRADA:
                item.stock_actual += cantidad
            else:  # SALIDA y PERDIDA restan igual, con piso en cero.
                item.stock_actual = max(0, item.stock_actual - cantidad)
            item.save(update_fields=["stock_actual"])
            movimiento = MovimientoInventario.objects.create(
                item=item, tipo=tipo, cantidad=cantidad, motivo=motivo
            )

        self.stock_actual = item.stock_actual
        return movimiento

    @property
    def stock_bajo(self):
        return self.stock_actual <= self.stock_minimo


class MovimientoInventario(TimestampedModel):
    ENTRADA, SALIDA, PERDIDA = "ENTRADA", "SALIDA", "PERDIDA"
    TIPO_CHOICES = [(ENTRADA, "Entrada"), (SALIDA, "Salida"), (PERDIDA, "Pérdida")]

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
