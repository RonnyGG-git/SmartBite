from django import forms

from .models import Restaurante, Sucursal
from .validators import nif_validator, telefono_validator, url_publica_validator


class RestauranteForm(forms.ModelForm):
    class Meta:
        model = Restaurante
        fields = ["nombre", "nif", "email", "direccion", "telefono", "telefono_secundario", "logo_url", "activo"]
        widgets = {
            "nif": forms.TextInput(attrs={"placeholder": "900123456-1"}),
            "telefono": forms.TextInput(attrs={"placeholder": "+57 604 1234567"}),
            "telefono_secundario": forms.TextInput(attrs={"placeholder": "+57 300 1234567"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("nombre", "nif", "email", "direccion"):
            self.fields[campo].required = True

    nif = forms.CharField(max_length=30, validators=[nif_validator], error_messages={"invalid": nif_validator.message})

    telefono = forms.CharField(
        max_length=30,
        required=False,
        validators=[telefono_validator],
        error_messages={"invalid": telefono_validator.message},
    )
    telefono_secundario = forms.CharField(
        max_length=30,
        required=False,
        validators=[telefono_validator],
        error_messages={"invalid": telefono_validator.message},
    )

    logo_url = forms.URLField(
        required=False,
        validators=[url_publica_validator],
        error_messages={"invalid": url_publica_validator.message},
    )

    def clean_nif(self):
        return self.cleaned_data["nif"].replace(" ", "").upper()

    def clean_telefono(self):
        return self.cleaned_data["telefono"].strip()

    def clean_telefono_secundario(self):
        return self.cleaned_data["telefono_secundario"].strip()

    def clean(self):
        cleaned_data = super().clean()
        principal = cleaned_data.get("telefono")
        secundario = cleaned_data.get("telefono_secundario")
        if principal and secundario and principal == secundario:
            self.add_error(
                "telefono_secundario",
                "El teléfono secundario debe ser distinto del teléfono principal.",
            )
        return cleaned_data


class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ["restaurante", "nombre", "direccion", "telefono", "latitud", "longitud", "activo"]
        widgets = {
            "telefono": forms.TextInput(attrs={"placeholder": "+57 604 1234567"}),
            "latitud": forms.NumberInput(attrs={"step": "any", "data-mapa": "latitud"}),
            "longitud": forms.NumberInput(attrs={"step": "any", "data-mapa": "longitud"}),
        }
        help_texts = {"latitud": "Marca la sucursal en el mapa; se llena sola."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("restaurante", "nombre"):
            self.fields[campo].required = True

    telefono = forms.CharField(
        max_length=30,
        required=False,
        validators=[telefono_validator],
        error_messages={"invalid": telefono_validator.message},
    )

    def clean_telefono(self):
        return self.cleaned_data["telefono"].strip()

    def clean(self):
        cleaned_data = super().clean()
        if (cleaned_data.get("latitud") is None) != (cleaned_data.get("longitud") is None):
            self.add_error("longitud", "Indica latitud y longitud juntas, o deja las dos vacías.")
        return cleaned_data
