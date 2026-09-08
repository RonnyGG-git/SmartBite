from django import template

register = template.Library()


@register.filter
def moneda(valor):
    """Formatea un número como moneda: 15000 -> '$15.000' (equivalente a
    Number(x).toLocaleString("es-CO") usado en el frontend React)."""
    try:
        entero = int(round(float(valor)))
    except (TypeError, ValueError):
        return "—"
    return "${:,}".format(entero).replace(",", ".")
