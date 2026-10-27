from django import forms

from .models import ConsultaAsistente


class ConsultaForm(forms.Form):
    """Una sola pregunta en lenguaje natural: "¿qué puedo cocinar?"."""

    texto = forms.CharField(
        label="¿Qué estás buscando?",
        max_length=300,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Ej: algo dulce y facil de hacer en menos de 30 minutos",
            }
        ),
        help_text="Puedes pedir por sabor, dificultad, tiempo o ingredientes.",
    )

    def clean_texto(self):
        # Un espacio no es una consulta: sin esto "   " llegaría al motor y
        # devolvería una lista vacía sin explicarle nada al usuario.
        texto = " ".join(self.cleaned_data["texto"].split())
        if not texto:
            raise forms.ValidationError("Escribe qué quieres buscar.")
        return texto
