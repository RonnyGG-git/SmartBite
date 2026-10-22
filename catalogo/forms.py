from django import forms

from .models import Categoria, Producto


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        repetida = Categoria.objects.filter(restaurante=self.instance.restaurante, nombre__iexact=nombre)
        if repetida.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una categoría con ese nombre en tu restaurante.")
        return nombre


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["nombre", "descripcion", "precio", "url_imagen", "categoria", "sucursal", "disponible"]
