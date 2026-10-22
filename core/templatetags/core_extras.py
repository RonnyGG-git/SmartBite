from django import template

register = template.Library()


@register.filter
def moneda(valor):
    try:
        entero = int(round(float(valor)))
    except (TypeError, ValueError):
        return "—"
    return "${:,}".format(entero).replace(",", ".")
