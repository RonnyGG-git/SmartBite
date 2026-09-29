from datetime import timedelta

from django.db import models

from core.models import TimestampedModel


class Mesa(TimestampedModel):
    DISPONIBLE, OCUPADA, RESERVADA = "DISPONIBLE", "OCUPADA", "RESERVADA"
    ESTADO_CHOICES = [(DISPONIBLE, "Disponible"), (OCUPADA, "Ocupada"), (RESERVADA, "Reservada")]

    numero = models.PositiveIntegerField()
    capacidad = models.PositiveIntegerField(default=4)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=DISPONIBLE)
    activa = models.BooleanField(default=True)
    sucursal = models.ForeignKey("restaurantes.Sucursal", on_delete=models.PROTECT, related_name="mesas")

    class Meta:
        ordering = ["numero"]
        unique_together = ("sucursal", "numero")

    def __str__(self):
        return f"Mesa {self.numero}"

    @property
    def orden_activa(self):
        return self.ordenes.exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA]).first()


class Cliente(TimestampedModel):
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    numero_documento = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Orden(TimestampedModel):
    PENDIENTE = "PENDIENTE"
    EN_PREPARACION = "EN_PREPARACION"
    LISTA = "LISTA"
    ENTREGADA = "ENTREGADA"
    CANCELADA = "CANCELADA"
    ESTADO_CHOICES = [
        (PENDIENTE, "Pendiente"),
        (EN_PREPARACION, "En preparación"),
        (LISTA, "Lista"),
        (ENTREGADA, "Entregada"),
        (CANCELADA, "Cancelada"),
    ]

    # Canal por el que entró el pedido (CU-PED-03 vs CU-PED-05)
    ORIGEN_MESERO = "MESERO"
    ORIGEN_AUTOPEDIDO = "AUTOPEDIDO"
    ORIGEN_CHOICES = [(ORIGEN_MESERO, "Mesero"), (ORIGEN_AUTOPEDIDO, "Autopedido (QR)")]

    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="ordenes")
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, related_name="ordenes", null=True, blank=True
    )
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=PENDIENTE)
    origen = models.CharField(max_length=12, choices=ORIGEN_CHOICES, default=ORIGEN_MESERO)
    # CU-PED-23: el Chef fija un aproximado al iniciar la preparación
    tiempo_estimado_min = models.PositiveSmallIntegerField(null=True, blank=True)
    preparacion_iniciada_en = models.DateTimeField(null=True, blank=True)
    # CU-PED-14 Solicitar cuenta: el Mesero envía el total a caja (CU-PED-15)
    cuenta_solicitada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Orden #{self.pk} — Mesa {self.mesa.numero}"

    @property
    def listo_estimado_en(self):
        """Hora aproximada en que estará listo (None si el Chef no la fijó)."""
        if self.tiempo_estimado_min is None or self.preparacion_iniciada_en is None:
            return None
        return self.preparacion_iniciada_en + timedelta(minutes=self.tiempo_estimado_min)

    @property
    def total(self):
        return sum((d.subtotal for d in self.detalles.all()), 0)

    @property
    def es_final(self):
        return self.estado in (self.ENTREGADA, self.CANCELADA)


class DetalleOrden(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="+")
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario
