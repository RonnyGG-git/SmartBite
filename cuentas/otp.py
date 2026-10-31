import hashlib
import hmac
import math
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import CodigoVerificacion

VIGENCIA = timedelta(minutes=10)
ESPERA_REENVIO = timedelta(seconds=60)
MAX_INTENTOS = 5

OK, INCORRECTO, VENCIDO, BLOQUEADO = "ok", "incorrecto", "vencido", "bloqueado"

MENSAJES = {
    INCORRECTO: "El código no es correcto.",
    VENCIDO: "El código venció o ya se usó. Pide uno nuevo.",
    BLOQUEADO: "Demasiados intentos con este código. Pide uno nuevo.",
}

ASUNTOS = {
    CodigoVerificacion.REGISTRO: "Tu código para activar Smart Bite",
    CodigoVerificacion.RECUPERACION: "Tu código para cambiar la contraseña de Smart Bite",
}


class EsperaReenvio(Exception):
    def __init__(self, segundos):
        super().__init__(segundos)
        self.segundos = segundos


def _huella(usuario_id, codigo):
    mensaje = f"{usuario_id}:{codigo}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), mensaje, hashlib.sha256).hexdigest()


def segundos_para_reenviar(usuario, proposito):
    ultimo = CodigoVerificacion.objects.filter(usuario=usuario, proposito=proposito).first()
    if ultimo is None:
        return 0
    restante = (ultimo.creado_en + ESPERA_REENVIO - timezone.now()).total_seconds()
    return max(0, math.ceil(restante))


def enviar_codigo(usuario, proposito):
    espera = segundos_para_reenviar(usuario, proposito)
    if espera:
        raise EsperaReenvio(espera)
    codigo = f"{secrets.randbelow(10000):04d}"
    contexto = {
        "usuario": usuario,
        "codigo": codigo,
        "minutos": int(VIGENCIA.total_seconds() // 60),
        "registro": proposito == CodigoVerificacion.REGISTRO,
    }
    send_mail(
        ASUNTOS[proposito],
        render_to_string("cuentas/correo/codigo.txt", contexto),
        None,
        [usuario.email],
        html_message=render_to_string("cuentas/correo/codigo.html", contexto),
    )
    CodigoVerificacion.objects.filter(usuario=usuario, proposito=proposito, usado=False).update(usado=True)
    CodigoVerificacion.objects.create(
        usuario=usuario,
        proposito=proposito,
        huella=_huella(usuario.pk, codigo),
        expira_en=timezone.now() + VIGENCIA,
    )
    return codigo


def verificar_codigo(usuario, proposito, codigo):
    registro = CodigoVerificacion.objects.filter(usuario=usuario, proposito=proposito, usado=False).first()
    if registro is None or registro.expira_en <= timezone.now():
        return VENCIDO
    if registro.intentos >= MAX_INTENTOS:
        return BLOQUEADO
    if hmac.compare_digest(registro.huella, _huella(usuario.pk, codigo)):
        registro.usado = True
        registro.save(update_fields=["usado", "actualizado_en"])
        return OK
    registro.intentos += 1
    registro.save(update_fields=["intentos", "actualizado_en"])
    return BLOQUEADO if registro.intentos >= MAX_INTENTOS else INCORRECTO
