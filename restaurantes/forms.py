from django import forms

from .models import Restaurante, Sucursal


class RestauranteForm(forms.ModelForm):
    class Meta:
        model = Restaurante
        fields = ["nombre", "nif", "email", "direccion", "telefono", "telefono_secundario", "logo_url", "activo"]


class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ["restaurante", "nombre", "direccion", "telefono", "activo"]
