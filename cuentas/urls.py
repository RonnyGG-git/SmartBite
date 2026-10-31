from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("registro/", views.RegistroAdministradorView.as_view(), name="registro_admin"),
    path("registro/empleado/", views.RegistroEmpleadoView.as_view(), name="registro_empleado"),
    path("pendiente/", views.PendienteView.as_view(), name="pendiente"),
    path("verificar/", views.verificar_correo, name="verificar"),
    path("verificar/reenviar/", views.reenviar_verificacion, name="verificar_reenviar"),
    path("recuperar/", views.RecuperarView.as_view(), name="recuperar"),
    path("recuperar/codigo/", views.recuperar_codigo, name="recuperar_codigo"),
    path("recuperar/reenviar/", views.reenviar_recuperacion, name="recuperar_reenviar"),

    path("usuarios/", views.UsuarioListView.as_view(), name="usuarios_list"),
    path("usuarios/nuevo/", views.UsuarioCreateView.as_view(), name="usuario_crear"),
    path("usuarios/<int:pk>/editar/", views.UsuarioUpdateView.as_view(), name="usuario_editar"),
    path("usuarios/<int:pk>/eliminar/", views.UsuarioDeleteView.as_view(), name="usuario_eliminar"),
    path("usuarios/<int:pk>/estado/", views.usuario_toggle_activo, name="usuario_toggle_activo"),

    path("roles/", views.RolListView.as_view(), name="roles_list"),
    path("roles/nuevo/", views.RolCreateView.as_view(), name="rol_crear"),
    path("roles/<int:pk>/editar/", views.RolUpdateView.as_view(), name="rol_editar"),
    path("roles/<int:pk>/eliminar/", views.RolDeleteView.as_view(), name="rol_eliminar"),
    path("roles/<int:pk>/permisos/", views.rol_permisos, name="rol_permisos"),
]
