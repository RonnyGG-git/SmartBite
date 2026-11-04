from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.filter
def moneda(valor):
    try:
        entero = int(round(float(valor)))
    except (TypeError, ValueError):
        return "—"
    return "${:,}".format(entero).replace(",", ".")


@register.simple_tag
def url_app_android():
    return settings.APP_ANDROID_URL or static("descargas/smartbite.apk")
