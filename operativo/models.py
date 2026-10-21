from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction

from core.models import TimestampedModel


class TransicionOrdenInvalida(ValidationError):
    """Se pidió un cambio de estado que la máquina de estados no permite.

    Hereda de ValidationError para que la API REST la mapee a 400 sin
    tratamiento especial, y fija `code="transicion_invalida"` para que el
    cliente pueda distinguirla de otros errores de validación.
    """

    def __init__(self, mensaje, orden=None, **kwargs):
        self.orden = orden
        kwargs.setdefault("code", "transicion_invalida")
        super().__init__(mensaje, **kwargs)


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
        unique_together = [("nombre", "telefono", "email")]

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

    TRANSICIONES_VALIDAS = {
        PENDIENTE: [EN_PREPARACION, CANCELADA],
        EN_PREPARACION: [LISTA, CANCELADA],
        LISTA: [ENTREGADA, CANCELADA],
        ENTREGADA: [],
        CANCELADA: [],
    }
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Lo deja `cambiar_estado` al descontar la receta. Vive en la
        # instancia (no es columna) porque es un reporte de esa operación,
        # no un dato que deba sobrevivir a otra lectura de la orden.
        self.insumos_faltantes = {}

    def puede_cambiar_a(self, estado_destino):
        return estado_destino in self.TRANSICIONES_VALIDAS.get(self.estado, [])

    @property
    def transiciones_disponibles(self):
        """Estados a los que esta orden puede pasar desde su estado actual."""
        return list(self.TRANSICIONES_VALIDAS.get(self.estado, []))

    def cambiar_estado(self, nuevo_estado, **campos_extra):
        """Única puerta de entrada para cambiar el estado de una orden.

        Concentra aquí toda la regla —y no en las vistas— lo que toca al
        entrar: estado de la mesa y descuento de insumos por receta. Así una
        orden no puede quedar con la mesa liberada pero el inventario
        descontado, ni al revés.

        Todo ocurre en una sola transacción con la fila bloqueada
        (`select_for_update`): si dos cajeros o dos chefs actúan sobre la
        misma orden a la vez, el segundo ve el estado ya actualizado y su
        transición se rechaza en vez de sobrescribir al primero.

        `campos_extra` se guarda en la misma operación (por ejemplo
        `tiempo_estimado_min` al iniciar la preparación).

        Lanza TransicionOrdenInvalida si la transición no está permitida;
        en ese caso no se persiste nada.
        """
        with transaction.atomic():
            orden = Orden.objects.select_for_update().get(pk=self.pk)

            if not orden.puede_cambiar_a(nuevo_estado):
                raise TransicionOrdenInvalida(
                    f"La orden #{orden.pk} no puede pasar de {orden.estado} a {nuevo_estado}.",
                    orden=orden,
                )

            orden.estado = nuevo_estado
            for campo, valor in campos_extra.items():
                setattr(orden, campo, valor)
            orden.save(update_fields=["estado", *campos_extra, "actualizado_en"])

            self.insumos_faltantes = orden._aplicar_efectos_de_entrada(nuevo_estado)

        # Refleja en la instancia del caller lo que quedó en la BD.
        self.estado = nuevo_estado
        for campo, valor in campos_extra.items():
            setattr(self, campo, valor)
        return self

    def _aplicar_efectos_de_entrada(self, nuevo_estado):
        """Ajusta mesa e inventario al entrar a `nuevo_estado`.

        Se invoca dentro de la transacción de `cambiar_estado` y devuelve los
        insumos que faltaron para poder preparar la orden.
        """
        # La mesa se ocupa cuando la orden entra a preparación y se
        # libera al cerrarse (entregada o cancelada).
        if nuevo_estado == self.EN_PREPARACION:
            self.mesa.estado = Mesa.OCUPADA
            self.mesa.save(update_fields=["estado"])
            # Descontar lo que consume la receta, una sola vez: solo al
            # entrar a EN_PREPARACION, nunca al seguir advanceando.
            # Import local: `inventario.services` no importa operativo, pero
            # así el orden de carga de apps de Django nunca depende de cuál
            # de las dos se importe primero.
            from inventario.services import descontar_insumos_por_receta

            return descontar_insumos_por_receta(self)["faltantes"]

        if nuevo_estado in (self.ENTREGADA, self.CANCELADA):
            self.mesa.estado = Mesa.DISPONIBLE
            self.mesa.save(update_fields=["estado"])

        return {}

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


class DetalleOrden(TimestampedModel):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="+")
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario
