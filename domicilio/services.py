import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.tenancy import restaurantes_accesibles
from operativo.models import Orden
from operativo.services import crear_orden, obtener_cliente

from .models import Domicilio

ESTADO_POR_ORDEN = {
    Orden.POR_CONFIRMAR: Domicilio.SOLICITADO,
    Orden.PENDIENTE: Domicilio.CONFIRMADO,
    Orden.EN_PREPARACION: Domicilio.EN_COCINA,
    Orden.LISTA: Domicilio.LISTO_PARA_RECOGER,
    Orden.ENTREGADA: Domicilio.ENTREGADO,
    Orden.CANCELADA: Domicilio.CANCELADO,
}


def sincronizar_con_orden(orden):
    """Lleva el estado del domicilio al paso que corresponde según la orden.

    Cuando la orden ya está LISTA y el domicilio va en ruta (ASIGNADO / EN_CAMINO),
    no se retrocede: esos pasos los marca el domiciliario.
    """
    domicilio = Domicilio.objects.select_for_update().filter(orden_id=orden.pk).first()
    if domicilio is None:
        return None
    nuevo = ESTADO_POR_ORDEN.get(orden.estado)
    if nuevo is None or domicilio.estado == nuevo:
        return domicilio
    if nuevo == Domicilio.LISTO_PARA_RECOGER and domicilio.estado in Domicilio.EN_RUTA:
        return domicilio
    domicilio.estado = nuevo
    campos = ["estado", "actualizado_en"]
    if nuevo == Domicilio.ENTREGADO and domicilio.entregado_en is None:
        domicilio.entregado_en = timezone.now()
        campos.append("entregado_en")
    domicilio.save(update_fields=campos)
    return domicilio


def _nuevo_codigo():
    return f"{secrets.randbelow(10000):04d}"


def crear_pedido_domicilio(usuario, sucursal, lineas, direccion, nombre="", telefono=""):
    if direccion.usuario_id != usuario.pk:
        raise ValidationError("Esa dirección no es tuya.", code="direccion_ajena")
    with transaction.atomic():
        cliente = obtener_cliente(sucursal.restaurante, nombre or usuario.nombre, telefono)
        orden = crear_orden(
            sucursal, lineas, Orden.ORIGEN_APP, Orden.DOMICILIO, cliente=cliente, estado=Orden.POR_CONFIRMAR,
        )
        domicilio = Domicilio.objects.create(
            orden=orden,
            cliente=usuario,
            direccion=direccion.direccion,
            referencia=direccion.referencia,
            latitud=direccion.latitud,
            longitud=direccion.longitud,
            telefono=telefono,
            codigo_entrega=_nuevo_codigo(),
        )
    return domicilio


def _bloquear(domicilio):
    return Domicilio.objects.select_for_update().select_related("orden").get(pk=domicilio.pk)


def puede_repartir(domiciliario, domicilio):
    restaurante_id = domicilio.orden.sucursal.restaurante_id
    return restaurantes_accesibles(domiciliario).filter(pk=restaurante_id).exists()


def tomar(domicilio, domiciliario):
    with transaction.atomic():
        d = _bloquear(domicilio)
        if not puede_repartir(domiciliario, d):
            raise ValidationError("Ese domicilio es de otro restaurante.", code="otro_restaurante")
        if d.domiciliario_id is not None:
            raise ValidationError("Otro domiciliario ya tomó este pedido.", code="ya_tomado")
        if d.estado != Domicilio.LISTO_PARA_RECOGER:
            raise ValidationError("El pedido todavía no está listo para recoger.", code="no_listo")
        d.domiciliario = domiciliario
        d.estado = Domicilio.ASIGNADO
        d.asignado_en = timezone.now()
        d.save(update_fields=["domiciliario", "estado", "asignado_en", "actualizado_en"])
    return d


def _del_domiciliario(d, domiciliario):
    if d.domiciliario_id != domiciliario.pk:
        raise ValidationError("Este domicilio no está asignado a ti.", code="no_asignado")


def recoger(domicilio, domiciliario):
    with transaction.atomic():
        d = _bloquear(domicilio)
        _del_domiciliario(d, domiciliario)
        if d.estado != Domicilio.ASIGNADO:
            raise ValidationError("Solo se recoge un pedido asignado.", code="no_asignado_aun")
        d.estado = Domicilio.EN_CAMINO
        d.recogido_en = timezone.now()
        d.save(update_fields=["estado", "recogido_en", "actualizado_en"])
    return d


def actualizar_ubicacion(domicilio, domiciliario, lat, lng):
    with transaction.atomic():
        d = _bloquear(domicilio)
        _del_domiciliario(d, domiciliario)
        if d.estado not in Domicilio.EN_RUTA:
            raise ValidationError("Solo se comparte la ubicación mientras el pedido va en ruta.", code="fuera_de_ruta")
        d.lat_actual, d.lng_actual, d.ubicacion_en = lat, lng, timezone.now()
        d.save(update_fields=["lat_actual", "lng_actual", "ubicacion_en", "actualizado_en"])
    return d


def confirmar_entrega(domicilio, domiciliario, codigo):
    fallo = None
    with transaction.atomic():
        d = _bloquear(domicilio)
        _del_domiciliario(d, domiciliario)
        if d.estado != Domicilio.EN_CAMINO:
            raise ValidationError("Primero marca el pedido como recogido.", code="no_en_camino")
        if d.codigo_bloqueado:
            raise ValidationError(
                "Demasiados intentos con el código. Pide al restaurante que confirme la entrega.", code="codigo_bloqueado"
            )
        if secrets.compare_digest(str(codigo), d.codigo_entrega):
            d.orden.cambiar_estado(Orden.ENTREGADA)
            d.refresh_from_db()
        else:
            # El intento fallido se guarda antes de avisar, para que cuente aunque se lance el error.
            d.intentos_codigo += 1
            d.save(update_fields=["intentos_codigo", "actualizado_en"])
            restantes = d.MAX_INTENTOS_CODIGO - d.intentos_codigo
            fallo = ValidationError(
                {"codigo": ValidationError(f"El código no coincide. Te quedan {restantes} intentos.", code="codigo_incorrecto")}
            )
    if fallo is not None:
        raise fallo
    return d


def cancelar_por_cliente(domicilio, usuario):
    with transaction.atomic():
        d = _bloquear(domicilio)
        if d.cliente_id != usuario.pk:
            raise ValidationError("Ese pedido no es tuyo.", code="ajeno")
        if d.estado != Domicilio.SOLICITADO:
            raise ValidationError(
                "El restaurante ya confirmó tu pedido; para cancelarlo comunícate con ellos.", code="ya_confirmado"
            )
        d.orden.cambiar_estado(Orden.CANCELADA)
        d.refresh_from_db()
    return d
