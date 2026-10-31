from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm
from django.core.validators import RegexValidator

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
        self.sin_verificar = None

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existente = Usuario.objects.filter(email__iexact=email).first()
        if existente is not None and existente.email_verificado:
            raise forms.ValidationError("Ya existe una cuenta con ese email.")
        self.sin_verificar = existente
        return email

    def validate_unique(self):
        if self.sin_verificar is None:
            super().validate_unique()

    def preparar(self, usuario):
        usuario.is_active = False
        usuario.email_verificado = False
        if self.sin_verificar is not None:
            self.sin_verificar.delete()
            self.sin_verificar = None
        return usuario

    def save(self, commit=True):
        usuario = self.preparar(super().save(commit=False))
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
        usuario = self.preparar(UserCreationForm.save(self, commit=False))
        usuario.restaurante = self.restaurante
        if commit:
            usuario.save()
        return usuario


class LoginForm(AuthenticationForm):
    def clean(self):
        email = (self.cleaned_data.get("username") or "").strip()
        clave = self.cleaned_data.get("password")
        self.sin_verificar = None
        if email and clave:
            pendiente = Usuario.objects.filter(email__iexact=email, email_verificado=False).first()
            if pendiente is not None and pendiente.check_password(clave):
                self.sin_verificar = pendiente
                return self.cleaned_data
        return super().clean()


class CodigoForm(forms.Form):
    codigo = forms.CharField(
        label="Código de 4 dígitos",
        min_length=4,
        max_length=4,
        validators=[RegexValidator(r"^\d{4}$", "Escribe los 4 números del código.")],
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
            "pattern": r"\d{4}",
            "maxlength": "4",
            "autofocus": True,
            "data-otp": "",
        }),
    )


class RecuperarForm(forms.Form):
    email = forms.EmailField(
        label="Email de tu cuenta",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class RestablecerForm(SetPasswordForm):
    codigo = CodigoForm.base_fields["codigo"]

    field_order = ["codigo", "new_password1", "new_password2"]

    @property
    def new_password_fields(self):
        return [self["new_password1"], self["new_password2"]]
