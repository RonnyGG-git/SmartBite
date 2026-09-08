from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),

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
