from django import forms

from .models import Retroalimentacion

# Tope por línea del autopedido: evita pedidos absurdos por error de dedo
MAX_CANTIDAD_POR_PRODUCTO = 20


class RetroalimentacionForm(forms.ModelForm):
    class Meta:
        model = Retroalimentacion
        fields = ["tipo", "mensaje", "nombre", "contacto"]
        widgets = {
            "tipo": forms.RadioSelect,
            "mensaje": forms.Textarea(attrs={"rows": 5, "maxlength": 1000, "placeholder": "Cuéntanos qué pasó o qué mejorarías"}),
            "nombre": forms.TextInput(attrs={"autocomplete": "name"}),
            "contacto": forms.TextInput(attrs={"autocomplete": "email"}),
        }
        labels = {"tipo": "¿Qué quieres enviarnos?", "nombre": "Tu nombre (opcional)", "contacto": "Contacto (opcional)"}


def leer_cantidades(post, productos):
    """Devuelve [(producto, cantidad)] con las cantidades > 0 enviadas en el
    POST como `cant_<id>`. Solo considera los productos permitidos (los de la
    sucursal de la mesa y disponibles) — cualquier otro id se ignora."""
    seleccion = []
    for producto in productos:
        crudo = post.get(f"cant_{producto.pk}", "").strip()
        if not crudo:
            continue
        try:
            cantidad = int(crudo)
        except ValueError:
            continue
        if cantidad <= 0:
            continue
        seleccion.append((producto, min(cantidad, MAX_CANTIDAD_POR_PRODUCTO)))
    return seleccion
