from django import forms
from django.forms import inlineformset_factory

from .models import Compra, DetalleCompra, ItemInventario, Proveedor


class ItemInventarioForm(forms.ModelForm):
    class Meta:
        model = ItemInventario
        fields = [
            "nombre", "descripcion", "unidad_medida",
            "stock_actual", "stock_minimo", "costo_unitario",
            "ubicacion", "sucursal",
        ]


class AjusteStockForm(forms.Form):
    tipo = forms.ChoiceField(choices=[("ENTRADA", "Entrada"), ("SALIDA", "Salida")])
    cantidad = forms.IntegerField(min_value=1)
    motivo = forms.CharField(max_length=255)


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "contacto", "telefono", "email", "direccion", "activo"]


class CompraForm(forms.ModelForm):
    class Meta:
        model = Compra
        fields = ["proveedor"]


DetalleCompraFormSet = inlineformset_factory(
    Compra,
    DetalleCompra,
    fields=["item", "cantidad", "costo_unitario"],
    extra=3,
    can_delete=True,
)
