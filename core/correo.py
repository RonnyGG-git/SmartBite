import json
import logging
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

URL_BREVO = "https://api.brevo.com/v3/smtp/email"

logger = logging.getLogger(__name__)


class BrevoBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        enviados = 0
        for mensaje in email_messages:
            try:
                self._enviar(mensaje)
                enviados += 1
            except Exception:
                logger.exception("Brevo no pudo enviar el correo a %s", mensaje.to)
                if not self.fail_silently:
                    raise
        return enviados

    def _enviar(self, mensaje):
        nombre, correo = parseaddr(mensaje.from_email)
        cuerpo = {
            "sender": {"email": correo, "name": nombre or "Smart Bite"},
            "to": [{"email": parseaddr(destino)[1]} for destino in mensaje.to],
            "subject": mensaje.subject,
            "textContent": mensaje.body,
        }
        html = next(
            (contenido for contenido, tipo in getattr(mensaje, "alternatives", []) if tipo == "text/html"),
            None,
        )
        if html:
            cuerpo["htmlContent"] = html
        peticion = urllib.request.Request(
            URL_BREVO,
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={
                "api-key": settings.BREVO_API_KEY,
                "accept": "application/json",
                "content-type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(peticion, timeout=15) as respuesta:
            return respuesta.status
