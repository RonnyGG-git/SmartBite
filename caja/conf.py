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
    return getattr(settings, "CAJA_BASE_URL", None) or os.environ.get("CAJA_BASE_URL", "")

def wompi_api_url():
    llave = wompi().get("PUBLIC_KEY", "") or ""
    return "https://sandbox.wompi.co/v1" if llave.startswith("pub_test_") else "https://production.wompi.co/v1"


def wompi_link():
    return wompi().get("WOMPI_LINK") or os.environ.get("WOMPI_LINK", "https://checkout.wompi.co/l/VPOS_YLOFY2")


def modo_prueba():
    if proveedor() == "SIMULADA":
        return True
    return (wompi().get("PUBLIC_KEY", "") or "").startswith("pub_test_")    