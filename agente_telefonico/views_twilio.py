from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from restaurantes.geo import leer_coordenadas

from .canal_twilio import numero_limpio, twilio_requerido, twiml_mensaje, twiml_voz
from .conversacion import Agente, iniciar_llamada
from .interprete import SALUDOS
from .models import LineaTelefonica, Llamada
from .texto import normalizar

MAX_CARACTERES = 500
ESTADOS_TERMINADOS = {"completed", "busy", "failed", "no-answer", "canceled"}


def _linea(numero):
    return LineaTelefonica.objects.select_related("sucursal__restaurante").filter(numero=numero_limpio(numero)).first()


def _webhook(vista):
    return csrf_exempt(require_POST(twilio_requerido(vista)))


def _accion_turno():
    return reverse("agente_telefonico:twilio_voz_turno")


def _responder_voz(respuesta):
    return twiml_voz(
        respuesta.texto, accion=_accion_turno(), finalizar=respuesta.finalizar, transferir_a=respuesta.transferir_a
    )


@_webhook
def voz_entrante(request):
    linea = _linea(request.POST.get("To"))
    if linea is None:
        return twiml_voz("Este número no está configurado. Gracias por llamar.", finalizar=True)
    llamada, _ = iniciar_llamada(
        linea.sucursal, request.POST.get("CallSid", ""), canal=Llamada.CANAL_TELEFONO,
        telefono_origen=numero_limpio(request.POST.get("From")), linea=linea,
    )
    return _responder_voz(Agente(llamada).iniciar())


@_webhook
def voz_turno(request):
    llamada = Llamada.objects.select_related("sucursal__restaurante", "linea").filter(
        identificador=request.POST.get("CallSid", ""), canal=Llamada.CANAL_TELEFONO
    ).first()
    if llamada is None:
        return twiml_voz("No encontré esta llamada. Por favor llámanos de nuevo.", finalizar=True)
    return _responder_voz(Agente(llamada).procesar(request.POST.get("SpeechResult", "")[:MAX_CARACTERES]))


@_webhook
def voz_estado(request):
    if request.POST.get("CallStatus") in ESTADOS_TERMINADOS:
        llamada = Llamada.objects.filter(
            identificador=request.POST.get("CallSid", ""), canal=Llamada.CANAL_TELEFONO
        ).first()
        if llamada is not None:
            Agente(llamada).colgar()
    return twiml_mensaje()


def _sesion_abierta(numero, linea):
    sesion = (
        Llamada.objects.select_related("sucursal__restaurante", "linea")
        .filter(canal=Llamada.CANAL_WHATSAPP, telefono_origen=numero, linea=linea, estado=Llamada.ACTIVA)
        .order_by("-actualizado_en")
        .first()
    )
    if sesion is None:
        return None
    if sesion.actualizado_en < timezone.now() - timedelta(minutes=settings.AGENTE_SESION_WHATSAPP_MIN):
        Agente(sesion).colgar()
        return None
    return sesion


def _texto_whatsapp(respuesta, saludo=""):
    texto = f"{saludo}\n\n{respuesta.texto}" if saludo else respuesta.texto
    if respuesta.transferir_a:
        texto = f"{texto}\n\nEscríbele o llama al {respuesta.transferir_a}."
    return texto


@_webhook
def whatsapp(request):
    linea = _linea(request.POST.get("To"))
    if linea is None:
        return twiml_mensaje("Este número todavía no está configurado.")
    numero = numero_limpio(request.POST.get("From"))[:20]
    mensaje = request.POST.get("MessageSid", "")
    texto = request.POST.get("Body", "").strip()[:MAX_CARACTERES]
    ubicacion = leer_coordenadas(request.POST.get("Latitude"), request.POST.get("Longitude"))
    if not texto and not ubicacion:
        return twiml_mensaje("Por ahora solo puedo leer mensajes de texto y ubicaciones.")

    sesion = _sesion_abierta(numero, linea)
    if sesion is not None:
        if mensaje and sesion.ultimo_mensaje == mensaje:
            return twiml_mensaje()
        sesion.ultimo_mensaje = mensaje[:64]
        sesion.save(update_fields=["ultimo_mensaje", "actualizado_en"])
        return twiml_mensaje(_texto_whatsapp(Agente(sesion).procesar(texto, ubicacion=ubicacion)))

    sesion, creada = iniciar_llamada(
        linea.sucursal, f"wa-{mensaje}"[:64], canal=Llamada.CANAL_WHATSAPP, telefono_origen=numero, linea=linea
    )
    if not creada:
        return twiml_mensaje()
    sesion.ultimo_mensaje = mensaje[:64]
    sesion.save(update_fields=["ultimo_mensaje", "actualizado_en"])
    agente = Agente(sesion)
    saludo = agente.iniciar()
    if saludo.finalizar or (not ubicacion and set(normalizar(texto).split()) <= SALUDOS):
        return twiml_mensaje(saludo.texto)
    return twiml_mensaje(_texto_whatsapp(agente.procesar(texto, ubicacion=ubicacion), saludo=saludo.texto))
