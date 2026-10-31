import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from catalogo.models import Producto

from .models import Cliente, DetalleOrden, Mesa, Orden, Reserva

MAX_CANTIDAD_POR_LINEA = 50


def obtener_cliente(restaurante, nombre, telefono=""):
    nombre = (nombre or "").strip()[:150]
    if not nombre:
        return None
    existente = Cliente.objects.filter(
        restaurante=restaurante, nombre__iexact=nombre, telefono=telefono, email=""
    ).first()
    if existente:
        return existente
    try:
        with transaction.atomic():
            return Cliente.objects.create(nombre=nombre, telefono=telefono, restaurante=restaurante)
    except IntegrityError:
        return None


def crear_orden(sucursal, lineas, origen, tipo_consumo, cliente=None, mesa=None, estado=Orden.PENDIENTE):
    cantidades = {}
    for producto_id, cantidad in lineas:
        if not isinstance(cantidad, int) or not 1 <= cantidad <= MAX_CANTIDAD_POR_LINEA:
            raise ValidationError(f"Cantidad inválida: {cantidad}.")
        cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad
    if not cantidades:
        raise ValidationError("La orden no tiene productos.")
    if tipo_consumo not in dict(Orden.TIPO_CONSUMO_CHOICES):
        raise ValidationError("Tipo de consumo inválido.")

    with transaction.atomic():
        productos = {
            p.pk: p
            for p in Producto.objects.select_for_update().filter(
                pk__in=cantidades, sucursal=sucursal, disponible=True
            )
        }
        faltan = set(cantidades) - set(productos)
        if faltan:
            raise ValidationError(f"Productos no disponibles: {sorted(faltan)}.")
        orden = Orden.objects.create(
            sucursal=sucursal, mesa=mesa, cliente=cliente, origen=origen,
            tipo_consumo=tipo_consumo, estado=estado,
        )
        DetalleOrden.objects.bulk_create(
            DetalleOrden(orden=orden, producto=productos[pk], cantidad=c, precio_unitario=productos[pk].precio)
            for pk, c in cantidades.items()
        )
    return orden


ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASO_ALTERNATIVAS = timedelta(minutes=30)


def _nuevo_codigo():
    while True:
        codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(8))
        if not Reserva.objects.filter(codigo=codigo).exists():
            return codigo


def validar_horario_reserva(fecha_hora, ahora=None):
    ahora = ahora or timezone.now()
    if fecha_hora < ahora + Reserva.ANTICIPACION:
        raise ValidationError("Reserva con al menos 1 hora de anticipación.", code="anticipacion")
    if fecha_hora > ahora + Reserva.HORIZONTE:
        raise ValidationError("Solo se puede reservar hasta 60 días antes.", code="horizonte")


def _mesas_candidatas(sucursal, num_personas):
    return Mesa.objects.filter(sucursal=sucursal, activa=True, capacidad__gte=num_personas).order_by(
        "capacidad", "numero"
    )


def mesa_libre_para_reserva(sucursal, fecha_hora, num_personas):
    ocupadas = Reserva.que_se_solapan(fecha_hora).filter(mesa__sucursal=sucursal).values("mesa_id")
    return _mesas_candidatas(sucursal, num_personas).exclude(pk__in=ocupadas).first()


def horarios_alternativos(sucursal, fecha_hora, num_personas, cantidad=3, ahora=None):
    ahora = ahora or timezone.now()
    encontrados = []
    for paso in range(1, 13):
        for signo in (1, -1):
            candidato = fecha_hora + signo * paso * PASO_ALTERNATIVAS
            try:
                validar_horario_reserva(candidato, ahora)
            except ValidationError:
                continue
            if mesa_libre_para_reserva(sucursal, candidato, num_personas) is not None:
                encontrados.append(candidato)
        if len(encontrados) >= cantidad:
            break
    return sorted(sorted(encontrados, key=lambda c: abs(c - fecha_hora))[:cantidad])


def crear_reserva(sucursal, fecha_hora, num_personas, nombre, telefono, ahora=None):
    validar_horario_reserva(fecha_hora, ahora)
    nombre = (nombre or "").strip()[:150]
    telefono = (telefono or "").strip()[:30]
    if not nombre or not telefono:
        raise ValidationError("Indica tu nombre y tu teléfono.", code="datos")
    if not 1 <= num_personas <= Reserva.MAX_PERSONAS:
        raise ValidationError("Número de personas no válido.", code="personas")
    capacidad = Mesa.objects.filter(sucursal=sucursal, activa=True).aggregate(m=Max("capacidad"))["m"] or 0
    if num_personas > capacidad:
        raise ValidationError(
            f"Este restaurante no tiene mesas para {num_personas} personas.", code="capacidad"
        )
    with transaction.atomic():
        list(_mesas_candidatas(sucursal, num_personas).select_for_update())
        mesa = mesa_libre_para_reserva(sucursal, fecha_hora, num_personas)
        if mesa is None:
            raise ValidationError("No hay mesas libres a esa hora.", code="sin_mesa")
        return Reserva.objects.create(
            mesa=mesa,
            cliente=obtener_cliente(sucursal.restaurante, nombre, telefono),
            codigo=_nuevo_codigo(),
            fecha_hora=fecha_hora,
            num_personas=num_personas,
            nombre=nombre,
            telefono=telefono,
        )


def _liberar_mesa_si_reservada(mesa_id, ahora):
    mesa = Mesa.objects.select_for_update().get(pk=mesa_id)
    if mesa.estado == Mesa.RESERVADA and not Reserva.en_ventana(ahora).filter(mesa_id=mesa_id).exists():
        mesa.estado = Mesa.DISPONIBLE
        mesa.save(update_fields=["estado"])


def _cerrar_reserva(reserva, estado, ahora):
    with transaction.atomic():
        bloqueada = Reserva.objects.select_for_update().get(pk=reserva.pk)
        if bloqueada.estado != Reserva.CONFIRMADA:
            raise ValidationError("La reserva ya no está confirmada.", code="cerrada")
        bloqueada.estado = estado
        bloqueada.save(update_fields=["estado", "actualizado_en"])
        if estado != Reserva.CUMPLIDA:
            _liberar_mesa_si_reservada(bloqueada.mesa_id, ahora)
    reserva.estado = estado
    return reserva


def cancelar_reserva(reserva, ahora=None):
    return _cerrar_reserva(reserva, Reserva.CANCELADA, ahora or timezone.now())


def confirmar_llegada(reserva, ahora=None):
    ahora = ahora or timezone.now()
    with transaction.atomic():
        mesa = Mesa.objects.select_for_update().get(pk=reserva.mesa_id)
        if mesa.orden_activa is not None:
            raise ValidationError("La mesa todavía tiene una orden activa.", code="mesa_ocupada")
        if ahora > reserva.fecha_hora + Reserva.TOLERANCIA or ahora < reserva.fecha_hora - Reserva.VENTANA:
            raise ValidationError("La reserva está fuera de su horario.", code="fuera_de_horario")
        _cerrar_reserva(reserva, Reserva.CUMPLIDA, ahora)
        mesa.estado = Mesa.OCUPADA
        mesa.save(update_fields=["estado"])
    return reserva


def sincronizar_reservas(reservas=None, ahora=None):
    ahora = ahora or timezone.now()
    reservas = Reserva.objects.all() if reservas is None else reservas
    confirmadas = reservas.filter(estado=Reserva.CONFIRMADA)
    with transaction.atomic():
        for reserva in confirmadas.filter(fecha_hora__lt=ahora - Reserva.TOLERANCIA).select_for_update():
            reserva.estado = Reserva.NO_ASISTIO
            reserva.save(update_fields=["estado", "actualizado_en"])
            _liberar_mesa_si_reservada(reserva.mesa_id, ahora)
        en_ventana = confirmadas.filter(
            fecha_hora__lte=ahora + Reserva.VENTANA, fecha_hora__gte=ahora - Reserva.TOLERANCIA
        ).values("mesa_id")
        Mesa.objects.filter(pk__in=en_ventana, estado=Mesa.DISPONIBLE, activa=True).update(estado=Mesa.RESERVADA)
