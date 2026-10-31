from django import forms
from django.contrib.auth.forms import UserCreationForm

from restaurantes.models import Restaurante

from .models import Permiso, Rol, Usuario

ROL_ADMINISTRADOR = "ADMINISTRADOR"


def roles_de_empleado():
    return Rol.objects.exclude(nombre=ROL_ADMINISTRADOR)


class UsuarioCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ["nombre", "email", "rol", "sucursal"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("nombre", "email", "rol"):
            self.fields[campo].required = True

    def clean_email(self):
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


class RegistroAdministradorForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ["nombre", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nombre"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese email.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.rol, _ = Rol.objects.get_or_create(nombre=ROL_ADMINISTRADOR)
        if commit:
            usuario.save()
        return usuario


class RegistroEmpleadoForm(RegistroAdministradorForm):
    codigo = forms.CharField(
        label="Código del restaurante", max_length=20,
        help_text="Te lo da el administrador de tu restaurante.",
    )

    field_order = ["codigo", "nombre", "email", "password1", "password2"]

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()
        restaurante = Restaurante.objects.filter(codigo_acceso=codigo, activo=True).first()
        if restaurante is None:
            raise forms.ValidationError("El código no es válido. Pídele el código actual a tu administrador.")
        self.restaurante = restaurante
        return codigo

    def save(self, commit=True):
        usuario = UserCreationForm.save(self, commit=False)
        usuario.restaurante = self.restaurante
        if commit:
            usuario.save()
        return usuario
