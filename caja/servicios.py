"""Lógica de negocio de cobros. Las vistas solo llaman a estas funciones; si algún día
`caja` se extrae como servicio aparte, este módulo es la frontera."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from operativo.models import Mesa, Orden
from .facturacion import emitir_factura

from .models import AuditoriaCobro, EventoPasarela, Pago
from .pasarelas import obtener_pasarela

CERO = Decimal("0")
VENCIMIENTO_PENDIENTE = timedelta(minutes=30)  # un cobro con tarjeta sin respuesta deja de reservar saldo


class CobroInvalido(Exception):
    pass


def _suma(qs, campo="monto"):
    return qs.aggregate(t=Sum(campo))["t"] or CERO


def saldo_pendiente(orden):
    """Lo que falta por pagar: total - pagos APROBADOS (la propina no abona)."""
    return orden.total - _suma(orden.pagos.filter(estado=Pago.APROBADO))


def saldo_disponible(orden):
    """Saldo cobrable ahora: descuenta también cobros con tarjeta en curso."""
    vigentes = orden.pagos.filter(estado=Pago.PENDIENTE, creado_en__gte=timezone.now() - VENCIMIENTO_PENDIENTE)
    return saldo_pendiente(orden) - _suma(vigentes)


def auditar(accion, orden, *, pago=None, usuario=None, ip=None, detalle=""):
    AuditoriaCobro.objects.create(
        accion=accion, orden=orden, pago=pago, usuario=usuario, ip=ip, detalle=detalle[:255],
        monto=pago.monto if pago else CERO, propina=pago.propina if pago else CERO,
    )


def _validar(orden, monto, propina):
    if orden.estado == Orden.CANCELADA:
        raise CobroInvalido("La orden está cancelada.")
    if monto <= 0:
        raise CobroInvalido("El monto debe ser mayor que cero.")
    if propina < 0:
        raise CobroInvalido("La propina no puede ser negativa.")
    disponible = saldo_disponible(orden)
    if monto > disponible:
        raise CobroInvalido(f"El monto supera el saldo por cobrar (${disponible:,.0f}).")


def _cerrar_si_pagada(orden):
    if saldo_pendiente(orden) <= 0 and orden.total > 0 and orden.estado != Orden.ENTREGADA:
        orden.estado = Orden.ENTREGADA
        orden.save(update_fields=["estado"])
        orden.mesa.estado = Mesa.DISPONIBLE
        orden.mesa.save(update_fields=["estado"])
        emitir_factura(orden)


def registrar_pago_manual(orden_id, *, metodo, monto, propina=CERO, referencia="", usuario=None, ip=None):
    """Efectivo, transferencia, etc. Queda APROBADO de inmediato."""
    with transaction.atomic():
        orden = Orden.objects.select_for_update().get(pk=orden_id)  # evita cobrar dos veces en paralelo
        _validar(orden, monto, propina)
        pago = Pago.objects.create(
            orden=orden, metodo_pago=metodo, monto=monto, propina=propina, estado=Pago.APROBADO,
            referencia_transaccion=referencia, cobrado_por=usuario,
        )
        auditar(AuditoriaCobro.COBRO, orden, pago=pago, usuario=usuario, ip=ip, detalle=f"Método: {metodo.nombre}")
        _cerrar_si_pagada(orden)
    return pago


def iniciar_cobro_tarjeta(orden_id, *, metodo, monto, propina=CERO, usuario=None, ip=None, pasarela=None, origen=""):
    """Crea un pago PENDIENTE con referencia única; la pasarela lo confirma por webhook."""
    pasarela = pasarela or obtener_pasarela()
    with transaction.atomic():
        orden = Orden.objects.select_for_update().get(pk=orden_id)
        _validar(orden, monto, propina)
        pago = Pago.objects.create(
            orden=orden, metodo_pago=metodo, monto=monto, propina=propina, estado=Pago.PENDIENTE,
            cobrado_por=usuario, proveedor=pasarela.nombre,
            referencia_pasarela=f"SB-{orden.pk}-{uuid.uuid4().hex[:10]}",
        )
        auditar(AuditoriaCobro.PASARELA_INICIADA, orden, pago=pago, usuario=usuario, ip=ip,
                detalle=f"{pasarela.nombre} · {origen}" if origen else pasarela.nombre)
        return pago, pasarela


def _payload(cuerpo):
    try:
        return json.loads(cuerpo)
    except ValueError:
        return {}


def procesar_evento(pasarela, cuerpo, cabeceras):
    """Procesa un webhook. Idempotente: un mismo evento cambia el estado una sola vez.
    Lanza FirmaInvalida si el evento no es auténtico."""
    evento = pasarela.leer_evento(cuerpo, cabeceras)
    return aplicar_evento(pasarela, evento, _payload(cuerpo))


def aplicar_evento(pasarela, evento, payload):
    """Aplica un evento YA verificado (llegó firmado por webhook o se consultó a la pasarela)."""
    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint: si es duplicado no rompe la transacción externa
                registro = EventoPasarela.objects.create(
                    proveedor=pasarela.nombre, evento_id=evento.evento_id, payload=payload
                )
        except IntegrityError:
            return "duplicado"

        pago = (
            Pago.objects.select_for_update()
            .filter(referencia_pasarela=evento.referencia, proveedor=pasarela.nombre).first()
        )
        if pago is None:
            registro.resultado = "pago no encontrado"
            registro.save(update_fields=["resultado"])
            return registro.resultado

        orden = Orden.objects.select_for_update().get(pk=pago.orden_id)

        if pago.estado != Pago.PENDIENTE:
            resultado = f"ignorado: el pago ya estaba {pago.estado}"
        elif evento.monto_centavos != int(pago.total_cobrado * 100):
            auditar(AuditoriaCobro.ALERTA, orden, pago=pago, detalle=(
                f"Monto del evento ({evento.monto_centavos}) distinto al esperado ({int(pago.total_cobrado * 100)})"
            ))
            resultado = "alerta: monto no coincide"
        elif evento.estado == "APROBADO":
            pago.estado = Pago.APROBADO
            pago.id_transaccion_pasarela = evento.id_transaccion
            pago.referencia_transaccion = evento.id_transaccion
            pago.save(update_fields=["estado", "id_transaccion_pasarela", "referencia_transaccion", "actualizado_en"])
            auditar(AuditoriaCobro.PASARELA_APROBADA, orden, pago=pago, detalle=evento.id_transaccion)
            _cerrar_si_pagada(orden)
            resultado = "aprobado"
        elif evento.estado == "RECHAZADO":
            pago.estado = Pago.RECHAZADO
            pago.id_transaccion_pasarela = evento.id_transaccion
            pago.save(update_fields=["estado", "id_transaccion_pasarela", "actualizado_en"])
            auditar(AuditoriaCobro.PASARELA_RECHAZADA, orden, pago=pago, detalle=evento.id_transaccion)
            resultado = "rechazado"
        else:
            resultado = "sin cambios"

        registro.resultado = resultado
        registro.save(update_fields=["resultado"])
        return resultado


def sincronizar_pago(pago, id_transaccion, pasarela=None):
    """Plan B si el webhook no llegó (túnel caído, red lenta...): al volver el cliente de la
    pasarela se le pregunta directamente a ella por la transacción. Solo se acepta si la
    referencia es la de ESTE pago y el monto coincide (lo valida `aplicar_evento`)."""
    if pago.estado != Pago.PENDIENTE or not id_transaccion or not pago.proveedor:
        return pago
    try:
        pasarela = pasarela or obtener_pasarela(pago.proveedor)
    except KeyError:
        return pago
    evento = pasarela.consultar_transaccion(id_transaccion)
    if evento is not None and evento.referencia == pago.referencia_pasarela:
        aplicar_evento(pasarela, evento, {
            "origen": "consulta_api", "transaccion": evento.id_transaccion, "estado": evento.estado,
        })
    pago.refresh_from_db()
    return pago