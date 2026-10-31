from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from core.models import TimestampedModel


class TransicionOrdenInvalida(ValidationError):
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

    @property
    def reserva_en_ventana(self):
        return Reserva.en_ventana().filter(mesa=self).order_by("fecha_hora").first()


class Cliente(TimestampedModel):
    nombre = models.CharField(max_length=150)
    restaurante = models.ForeignKey(
        "restaurantes.Restaurante", on_delete=models.CASCADE, related_name="clientes", null=True, blank=True
    )
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    numero_documento = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["nombre"]
        unique_together = [("nombre", "telefono", "email")]

    def __str__(self):
        return self.nombre


class Orden(TimestampedModel):
    POR_CONFIRMAR = "POR_CONFIRMAR"
    PENDIENTE = "PENDIENTE"
    EN_PREPARACION = "EN_PREPARACION"
    LISTA = "LISTA"
    ENTREGADA = "ENTREGADA"
    CANCELADA = "CANCELADA"
    ESTADO_CHOICES = [
        (POR_CONFIRMAR, "Por confirmar"),
        (PENDIENTE, "Pendiente"),
        (EN_PREPARACION, "En preparación"),
        (LISTA, "Lista"),
        (ENTREGADA, "Entregada"),
        (CANCELADA, "Cancelada"),
    ]

    TRANSICIONES_VALIDAS = {
        POR_CONFIRMAR: [PENDIENTE, CANCELADA],
        PENDIENTE: [EN_PREPARACION, CANCELADA],
        EN_PREPARACION: [LISTA, CANCELADA],
        LISTA: [ENTREGADA, CANCELADA],
        ENTREGADA: [],
        CANCELADA: [],
    }
    ORIGEN_MESERO = "MESERO"
    ORIGEN_AUTOPEDIDO = "AUTOPEDIDO"
    ORIGEN_TELEFONO = "AGENTE_TELEFONICO"
    ORIGEN_CHOICES = [
        (ORIGEN_MESERO, "Mesero"),
        (ORIGEN_AUTOPEDIDO, "Autopedido (QR)"),
        (ORIGEN_TELEFONO, "Agente telefónico"),
    ]

    EN_RESTAURANTE = "EN_RESTAURANTE"
    PARA_LLEVAR = "PARA_LLEVAR"
    TIPO_CONSUMO_CHOICES = [(EN_RESTAURANTE, "Comer en el restaurante"), (PARA_LLEVAR, "Para llevar")]

    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="ordenes", null=True, blank=True)
    sucursal = models.ForeignKey(
        "restaurantes.Sucursal", on_delete=models.PROTECT, related_name="ordenes", null=True, blank=True
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, related_name="ordenes", null=True, blank=True
    )
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=PENDIENTE)
    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default=ORIGEN_MESERO)
    tipo_consumo = models.CharField(max_length=15, choices=TIPO_CONSUMO_CHOICES, default=EN_RESTAURANTE)
    tiempo_estimado_min = models.PositiveSmallIntegerField(null=True, blank=True)
    preparacion_iniciada_en = models.DateTimeField(null=True, blank=True)
    cuenta_solicitada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Orden #{self.pk} — {self.ubicacion}"

    def save(self, *args, **kwargs):
        if self.sucursal_id is None and self.mesa_id is not None:
            self.sucursal_id = Mesa.objects.values_list("sucursal_id", flat=True).get(pk=self.mesa_id)
        super().save(*args, **kwargs)

    @property
    def ubicacion(self):
        if self.mesa_id:
            return f"Mesa {self.mesa.numero}"
        return f"{self.get_origen_display()} · {self.get_tipo_consumo_display()}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.insumos_faltantes = {}

    def puede_cambiar_a(self, estado_destino):
        return estado_destino in self.TRANSICIONES_VALIDAS.get(self.estado, [])

    @property
    def transiciones_disponibles(self):
        return list(self.TRANSICIONES_VALIDAS.get(self.estado, []))

    def cambiar_estado(self, nuevo_estado, **campos_extra):
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

        self.estado = nuevo_estado
        for campo, valor in campos_extra.items():
            setattr(self, campo, valor)
        return self

    def _aplicar_efectos_de_entrada(self, nuevo_estado):
        if nuevo_estado == self.EN_PREPARACION:
            if self.mesa_id:
                self.mesa.estado = Mesa.OCUPADA
                self.mesa.save(update_fields=["estado"])
            from inventario.services import descontar_insumos_por_receta

            return descontar_insumos_por_receta(self)["faltantes"]

        if nuevo_estado in (self.ENTREGADA, self.CANCELADA) and self.mesa_id:
            self.mesa.estado = Mesa.DISPONIBLE
            self.mesa.save(update_fields=["estado"])

        return {}

    @property
    def listo_estimado_en(self):
        if self.tiempo_estimado_min is None or self.preparacion_iniciada_en is None:
            return None
        return self.preparacion_iniciada_en + timedelta(minutes=self.tiempo_estimado_min)

    @property
    def total(self):
        return sum((d.subtotal for d in self.detalles.all()), 0)

    @property
    def es_final(self):
        return self.estado in (self.ENTREGADA, self.CANCELADA)

    @property
    def total_pagado(self):
        return sum((p.monto for p in self.pagos.all()), 0)

    @property
    def pagada(self):
        return self.pagos.exists() and self.total_pagado >= self.total

    @property
    def cobrable(self):
        if self.es_final or self.pagada:
            return False
        if self.mesa_id:
            return self.estado == self.LISTA
        return self.estado in (self.POR_CONFIRMAR, self.PENDIENTE, self.EN_PREPARACION, self.LISTA)


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


class Reserva(TimestampedModel):
    CONFIRMADA = "CONFIRMADA"
    CUMPLIDA = "CUMPLIDA"
    CANCELADA = "CANCELADA"
    NO_ASISTIO = "NO_ASISTIO"
    ESTADO_CHOICES = [
        (CONFIRMADA, "Confirmada"),
        (CUMPLIDA, "Cumplida"),
        (CANCELADA, "Cancelada"),
        (NO_ASISTIO, "No asistió"),
    ]

    ANTICIPACION = timedelta(hours=1)
    HORIZONTE = timedelta(days=60)
    DURACION = timedelta(hours=2)
    VENTANA = timedelta(minutes=30)
    TOLERANCIA = timedelta(minutes=15)
    MAX_PERSONAS = 30

    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="reservas")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, related_name="reservas", null=True, blank=True)
    codigo = models.CharField(max_length=12, unique=True)
    fecha_hora = models.DateTimeField()
    num_personas = models.PositiveSmallIntegerField()
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=CONFIRMADA)

    class Meta:
        ordering = ["fecha_hora"]
        indexes = [models.Index(fields=["estado", "fecha_hora"])]

    def __str__(self):
        return f"Reserva {self.codigo} — {self.mesa}"

    @property
    def fin(self):
        return self.fecha_hora + self.DURACION

    @property
    def es_final(self):
        return self.estado != self.CONFIRMADA

    @classmethod
    def en_ventana(cls, ahora=None):
        ahora = ahora or timezone.now()
        return cls.objects.filter(
            estado=cls.CONFIRMADA,
            fecha_hora__lte=ahora + cls.VENTANA,
            fecha_hora__gte=ahora - cls.TOLERANCIA,
        )

    @classmethod
    def que_se_solapan(cls, fecha_hora):
        return cls.objects.filter(
            estado=cls.CONFIRMADA,
            fecha_hora__gt=fecha_hora - cls.DURACION,
            fecha_hora__lt=fecha_hora + cls.DURACION,
        )
