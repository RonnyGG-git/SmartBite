from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Permiso, Rol, Usuario


class UsuarioCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ["nombre", "email", "rol", "sucursal"]


class UsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["nombre", "email", "rol", "sucursal", "is_active"]


class RolForm(forms.ModelForm):
    class Meta:
        model = Rol
        fields = ["nombre", "descripcion", "activo"]


class RolPermisosForm(forms.Form):
    permisos = forms.ModelMultipleChoiceField(
        queryset=Permiso.objects.filter(activo=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
