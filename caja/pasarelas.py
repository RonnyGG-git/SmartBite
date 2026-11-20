import hashlib
import hmac
import json
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote, urlencode
from django.urls import reverse

from . import conf


class FirmaInvalida(Exception):
    pass


@dataclass
class EventoPago:
    evento_id: str
    id_transaccion: str
    referencia: str
    estado: str
    monto_centavos: int


def a_centavos(valor):
    return int((Decimal(valor) * 100).to_integral_value())

def url_absoluta(request, ruta):
    base = conf.base_url()
    return base.rstrip("/") + ruta if base else request.build_absolute_uri(ruta)


class PasarelaPago:
    nombre = ""

    def url_checkout(self, request, pago, retorno=None):
        raise NotImplementedError

    def consultar_transaccion(self, id_transaccion):
        return None

    def leer_evento(self, cuerpo: bytes, cabeceras) -> EventoPago:
        raise NotImplementedError


def _checksum_wompi(evento, propiedades, secreto):
    texto = ""
    for ruta in propiedades:
        valor = evento["data"]
        for parte in ruta.split("."):
            valor = valor[parte]
        texto += str(valor)
    texto += str(evento["timestamp"]) + secreto
    return hashlib.sha256(texto.encode()).hexdigest()


ESTADOS_WOMPI = {"APPROVED": "APROBADO", "DECLINED": "RECHAZADO", "VOIDED": "RECHAZADO", "ERROR": "RECHAZADO"}


class WompiPasarela(PasarelaPago):
    nombre = "WOMPI"

    def url_checkout(self, request, pago, retorno=None):
        cfg = conf.wompi()
        centavos = a_centavos(pago.total_cobrado)
        moneda = "COP"
        firma = hashlib.sha256(
            f"{pago.referencia_pasarela}{centavos}{moneda}{cfg['INTEGRITY_SECRET']}".encode()
        ).hexdigest()
        if retorno is None:
            retorno = (
                url_absoluta(request, reverse("caja:retorno_pago"))
                + "?" + urlencode({"ref": pago.referencia_pasarela})
            )
        params = {
            "public-key": cfg["PUBLIC_KEY"],
            "currency": moneda,
            "amount-in-cents": centavos,
            "reference": pago.referencia_pasarela,
            "signature:integrity": firma,
            "redirect-url": retorno,
        }
        return f"{cfg['CHECKOUT_URL']}?{urlencode(params)}"
    
    def consultar_transaccion(self, id_transaccion):
        url = f"{conf.wompi_api_url()}/transactions/{quote(str(id_transaccion), safe='')}"
        try:
            with urllib.request.urlopen(url, timeout=8) as respuesta:
                tx = json.loads(respuesta.read())["data"]
            return EventoPago(
                evento_id=f"{tx['id']}:{tx['status']}", id_transaccion=tx["id"],
                referencia=tx.get("reference", ""), estado=ESTADOS_WOMPI.get(tx["status"], "PENDIENTE"),
                monto_centavos=int(tx["amount_in_cents"]),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def leer_evento(self, cuerpo, cabeceras):
        try:
            datos = json.loads(cuerpo)
            firma = datos["signature"]
            esperado = _checksum_wompi(datos, firma["properties"], conf.wompi()["EVENTS_SECRET"])
            recibido = (firma.get("checksum") or cabeceras.get("X-Event-Checksum", "")).upper()
            tx = datos["data"]["transaction"]
        except (ValueError, KeyError, TypeError) as exc:
            raise FirmaInvalida("Evento mal formado") from exc
        if not hmac.compare_digest(esperado.upper(), recibido):
            raise FirmaInvalida("Checksum no coincide")
        return EventoPago(
            evento_id=f"{tx['id']}:{tx['status']}",
            id_transaccion=tx["id"],
            referencia=tx.get("reference", ""),
            estado=ESTADOS_WOMPI.get(tx["status"], "PENDIENTE"),
            monto_centavos=int(tx["amount_in_cents"]),
        )


class SimuladaPasarela(PasarelaPago):
    nombre = "SIMULADA"

    def url_checkout(self, request, pago, retorno=None):
        return reverse("caja:pasarela_simulada", args=[pago.referencia_pasarela])

    def construir_evento(self, pago, estado_wompi):
        tx_id = f"sim-{pago.referencia_pasarela}"
        evento = {
            "event": "transaction.updated",
            "data": {"transaction": {
                "id": tx_id, "status": estado_wompi,
                "amount_in_cents": a_centavos(pago.total_cobrado),
                "reference": pago.referencia_pasarela,
            }},
            "timestamp": 1700000000,
            "signature": {"properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"]},
        }
        evento["signature"]["checksum"] = _checksum_wompi(
            evento, evento["signature"]["properties"], conf.secreto_simulado()
        )
        return json.dumps(evento).encode()

    def leer_evento(self, cuerpo, cabeceras):
        try:
            datos = json.loads(cuerpo)
            esperado = _checksum_wompi(datos, datos["signature"]["properties"], conf.secreto_simulado())
            tx = datos["data"]["transaction"]
            recibido = datos["signature"]["checksum"]
        except (ValueError, KeyError, TypeError) as exc:
            raise FirmaInvalida("Evento mal formado") from exc
        if not hmac.compare_digest(esperado, recibido):
            raise FirmaInvalida("Checksum no coincide")
        return EventoPago(
            evento_id=f"{tx['id']}:{tx['status']}", id_transaccion=tx["id"], referencia=tx["reference"],
            estado=ESTADOS_WOMPI.get(tx["status"], "PENDIENTE"), monto_centavos=int(tx["amount_in_cents"]),
        )


PROVEEDORES = {"WOMPI": WompiPasarela, "SIMULADA": SimuladaPasarela}


def obtener_pasarela(nombre=None):
    return PROVEEDORES[(nombre or conf.proveedor()).upper()]()