import base64
import hashlib
import hmac
from functools import wraps
from xml.etree import ElementTree

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden


def numero_limpio(valor):
    return (valor or "").replace("whatsapp:", "").strip()


def _url_firmada(request):
    base = settings.TWILIO_WEBHOOK_BASE
    return f"{base}{request.get_full_path()}" if base else request.build_absolute_uri()


def firma_esperada(url, parametros, token):
    contenido = url + "".join(f"{clave}{parametros[clave]}" for clave in sorted(parametros))
    resumen = hmac.new(token.encode("utf-8"), contenido.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(resumen).decode("ascii")


def firma_valida(request):
    token = settings.TWILIO_AUTH_TOKEN
    recibida = request.headers.get("X-Twilio-Signature", "")
    if not token or not recibida:
        return False
    return hmac.compare_digest(firma_esperada(_url_firmada(request), request.POST.dict(), token), recibida)


def twilio_requerido(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not firma_valida(request):
            return HttpResponseForbidden("Firma no válida.")
        return vista(request, *args, **kwargs)

    return envoltura


def _twiml(raiz):
    return HttpResponse(ElementTree.tostring(raiz, encoding="utf-8", xml_declaration=True), content_type="text/xml")


def _decir(padre, texto):
    elemento = ElementTree.SubElement(
        padre, "Say", {"language": settings.AGENTE_IDIOMA_VOZ, "voice": settings.AGENTE_VOZ}
    )
    elemento.text = texto


def twiml_voz(texto, accion="", finalizar=False, transferir_a=""):
    raiz = ElementTree.Element("Response")
    if finalizar or not accion:
        _decir(raiz, texto)
        if transferir_a:
            ElementTree.SubElement(raiz, "Dial").text = transferir_a
        else:
            ElementTree.SubElement(raiz, "Hangup")
        return _twiml(raiz)
    escucha = ElementTree.SubElement(raiz, "Gather", {
        "input": "speech",
        "language": settings.AGENTE_IDIOMA_VOZ,
        "speechTimeout": "auto",
        "action": accion,
        "method": "POST",
        "actionOnEmptyResult": "true",
    })
    _decir(escucha, texto)
    return _twiml(raiz)


def twiml_mensaje(texto=""):
    raiz = ElementTree.Element("Response")
    if texto:
        ElementTree.SubElement(raiz, "Message").text = texto
    return _twiml(raiz)
