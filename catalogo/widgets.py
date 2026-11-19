from django import forms


class SelectorImagen(forms.FileInput):
    template_name = "catalogo/widgets/selector_imagen.html"
    imagen_actual = ""

    def get_context(self, name, value, attrs):
        contexto = super().get_context(name, value, attrs)
        contexto["widget"]["imagen_actual"] = self.imagen_actual
        return contexto
