from datetime import datetime

from django import forms
from django.utils import timezone

from operativo.models import Reserva

from .models import Retroalimentacion

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


class ReservaForm(forms.Form):
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))
    hora = forms.TimeField(label="Hora", widget=forms.TimeInput(attrs={"type": "time", "step": 900}))
    num_personas = forms.IntegerField(
        label="Personas", min_value=1, max_value=Reserva.MAX_PERSONAS, initial=2,
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )
    nombre = forms.CharField(label="Tu nombre", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    telefono = forms.CharField(
        label="Teléfono", max_length=30, widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"})
    )

    def clean(self):
        datos = super().clean()
        if datos.get("fecha") and datos.get("hora"):
            datos["fecha_hora"] = timezone.make_aware(datetime.combine(datos["fecha"], datos["hora"]))
        return datos
