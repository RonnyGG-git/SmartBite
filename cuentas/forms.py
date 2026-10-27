from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Permiso, Rol, Usuario


class UsuarioCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ["nombre", "email", "rol", "sucursal"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # G8: identidad, correo y rol son obligatorios para poder operar.
        for campo in ("nombre", "email", "rol"):
            self.fields[campo].required = True

    def clean_email(self):
        # Normaliza el correo: sin espacios y siempre en minúsculas, para que
        # "Admin@X.co " y "admin@x.co" no se consideren usuarios distintos.
        return self.cleaned_data["email"].strip().lower()


class UsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["nombre", "email", "rol", "sucursal", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("nombre", "email", "rol"):
            self.fields[campo].required = True

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class RolForm(forms.ModelForm):
    class Meta:
        model = Rol
        fields = ["nombre", "descripcion", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nombre"].required = True

    def clean_nombre(self):
        return self.cleaned_data["nombre"].strip()


class RolPermisosForm(forms.Form):
    permisos = forms.ModelMultipleChoiceField(
        queryset=Permiso.objects.filter(activo=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
