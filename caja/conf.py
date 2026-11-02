"""Configuración de la caja. Lee de settings si existe y, si no, de variables de entorno.
Así no hace falta tocar smartbite/settings.py, que es del equipo."""
import os

from django.conf import settings


def proveedor():
    return (getattr(settings, "PASARELA_PROVEEDOR", None) or os.environ.get("PASARELA_PROVEEDOR", "SIMULADA")).upper()


def secreto_simulado():
    return getattr(settings, "SIMULADA_SECRET", None) or os.environ.get("SIMULADA_SECRET", "secreto-local-solo-para-demo")


def wompi():
    cfg = getattr(settings, "WOMPI", None)
    if cfg:
        return cfg
    return {
        "PUBLIC_KEY": os.environ.get("WOMPI_PUBLIC_KEY", ""),
        "INTEGRITY_SECRET": os.environ.get("WOMPI_INTEGRITY_SECRET", ""),
        "EVENTS_SECRET": os.environ.get("WOMPI_EVENTS_SECRET", ""),
        "CHECKOUT_URL": "https://checkout.wompi.co/p/",
    }
    


def base_url():
    """Dirección que verá el celular al escanear el QR (ej. http://192.168.1.15:8000).
    Si está vacía, se usa la dirección con la que se abrió la página."""
    return getattr(settings, "CAJA_BASE_URL", None) or os.environ.get("CAJA_BASE_URL", "")

def wompi_api_url():
    """Las llaves de prueba (pub_test_...) usan el sandbox; las de producción, la API real."""
    llave = wompi().get("PUBLIC_KEY", "") or ""
    return "https://sandbox.wompi.co/v1" if llave.startswith("pub_test_") else "https://production.wompi.co/v1"


def wompi_link():
    """Enlace de pago de Wompi (payment link) que se codifica en el QR del cliente:
    con la pasarela real el celular escanea el QR y va directo al checkout."""
    return wompi().get("WOMPI_LINK") or os.environ.get("WOMPI_LINK", "https://checkout.wompi.co/l/VPOS_YLOFY2")


def modo_prueba():
    """True si los pagos NO mueven dinero real (simulada o llaves de sandbox de Wompi)."""
    if proveedor() == "SIMULADA":
        return True
    return (wompi().get("PUBLIC_KEY", "") or "").startswith("pub_test_")    