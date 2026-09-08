from django import forms

from .models import ProductoIngrediente


class ProductoIngredienteForm(forms.ModelForm):
    class Meta:
        model = ProductoIngrediente
        fields = ["producto", "item_inventario", "cantidad_requerida", "unidad_medida", "activo"]
