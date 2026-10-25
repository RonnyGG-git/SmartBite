import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

pedido_telefonico_registrado = Signal()


def notificar_cocina(orden):
    logger.info("Orden telefónica #%s enviada a cocina (sucursal %s)", orden.pk, orden.sucursal_id)
    pedido_telefonico_registrado.send(sender=orden.__class__, orden=orden)
