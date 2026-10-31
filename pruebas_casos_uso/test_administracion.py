from django.urls import reverse

from cliente.models import Retroalimentacion
from cuentas.models import Permiso, Rol, Usuario
from operativo.models import Orden
from restaurantes.models import Restaurante

from .base import CLAVE, CasoDeUsoTestCase


class AdministracionTests(CasoDeUsoTestCase):

    def setUp(self):
        self.entrar_como("ADMINISTRADOR")
        self.mesero = self.usuarios["MESERO"]

    def datos_usuario(self, usuario, **cambios):
        datos = {
            "nombre": usuario.nombre, "email": usuario.email, "rol": usuario.rol_id,
            "sucursal": usuario.sucursal_id, "is_active": "on",
        }
        datos.update(cambios)
        return datos

    def test_cu_adm_01_registrar_usuario(self):
        self.client.post(reverse("cuentas:usuario_crear"), {
            "nombre": "Nueva Cajera", "email": " Nueva@SmartBite.co ", "rol": self.mesero.rol_id,
            "sucursal": self.sucursal.pk, "password1": CLAVE, "password2": CLAVE,
        })
        self.assertTrue(Usuario.objects.filter(email="nueva@smartbite.co").exists())

    def test_cu_adm_02_consultar_usuario(self):
        usuarios = self.client.get(reverse("cuentas:usuarios_list")).context["object_list"]
        self.assertIn(self.mesero, list(usuarios))
        self.entrar_como("MESERO")
        self.assertEqual(self.client.get(reverse("cuentas:usuarios_list")).status_code, 403)

    def test_cu_adm_03_actualizar_usuario(self):
        self.client.post(
            reverse("cuentas:usuario_editar", args=[self.mesero.pk]),
            self.datos_usuario(self.mesero, nombre="Mesero Renombrado"),
        )
        self.mesero.refresh_from_db()
        self.assertEqual(self.mesero.nombre, "Mesero Renombrado")

    def test_cu_adm_04_eliminar_usuario(self):
        admin = self.usuarios["ADMINISTRADOR"]
        self.client.post(reverse("cuentas:usuario_toggle_activo", args=[self.mesero.pk]))
        self.client.post(reverse("cuentas:usuario_toggle_activo", args=[admin.pk]))
        self.mesero.refresh_from_db()
        admin.refresh_from_db()
        self.assertFalse(self.mesero.is_active)
        self.assertTrue(admin.is_active)

    def test_cu_adm_05_asignar_rol(self):
        cajero = Rol.objects.get(nombre="CAJERO")
        self.client.post(
            reverse("cuentas:usuario_editar", args=[self.mesero.pk]), self.datos_usuario(self.mesero, rol=cajero.pk)
        )
        self.mesero.refresh_from_db()
        self.assertEqual(self.mesero.rol, cajero)

    def test_cu_adm_06_gestionar_permisos(self):
        self.client.post(reverse("cuentas:rol_permisos", args=[self.mesero.rol_id]), {"permisos": []})
        self.client.force_login(Usuario.objects.create_superuser("root@smartbite.co", "Root", CLAVE))
        permiso = Permiso.objects.create(nombre="ver_reportes", recurso="Reportes")
        rol = self.mesero.rol
        self.client.post(reverse("cuentas:rol_permisos", args=[rol.pk]), {"permisos": [permiso.pk]})
        self.assertTrue(self.mesero.tiene_permiso("ver_reportes"))

    def test_cu_adm_09_gestionar_informacion_del_restaurante(self):
        self.client.post(reverse("restaurantes:restaurante_crear"), {
            "nombre": "Smart Bite Sur", "nif": "900765432-1", "email": "sur@smartbite.co",
            "direccion": "Calle 50", "activo": "on",
        })
        self.assertTrue(Restaurante.objects.filter(nombre="Smart Bite Sur").exists())
        self.client.post(reverse("restaurantes:restaurante_crear"), {
            "nombre": "NIF malo", "nif": "abc", "email": "x@x.co", "direccion": "x",
        })
        self.assertFalse(Restaurante.objects.filter(nombre="NIF malo").exists())

    def test_cu_adm_10_generar_reporte_administrativo(self):
        self.crear_orden()
        self.crear_orden(estado=Orden.CANCELADA)
        por_estado = self.client.get(reverse("reportes:reportes")).context["ordenes_por_estado"]
        self.assertEqual((por_estado[Orden.PENDIENTE], por_estado[Orden.CANCELADA]), (1, 1))

    def test_cu_adm_12_consultar_ventas(self):
        self.assertEqual(self.client.get(reverse("reportes:dashboard")).status_code, 200)
        self.entrar_como("CAJERO")
        self.assertEqual(self.client.get(reverse("reportes:dashboard")).status_code, 403)

    def test_cu_adm_13_consultar_inventario(self):
        self.pan.stock_actual = 2
        self.pan.save()
        bajos = self.client.get(reverse("reportes:dashboard")).context["items_stock_bajo"]
        self.assertEqual(bajos, [self.pan])

    def test_cu_adm_14_consultar_indicadores_de_desempeno(self):
        self.crear_orden()
        contexto = self.client.get(reverse("reportes:dashboard")).context
        self.assertEqual((contexto["ordenes_hoy"], contexto["mesas_ocupadas"]), (1, 1))

    def test_cu_adm_16_revisar_sugerencias_y_denuncias(self):
        mensaje = Retroalimentacion.objects.create(tipo=Retroalimentacion.DENUNCIA, mensaje="Demora", mesa=self.mesa)
        self.assertIn(mensaje, list(self.client.get(reverse("cliente:retroalimentacion_list")).context["mensajes"]))
        self.client.post(reverse("cliente:retroalimentacion_revisar", args=[mensaje.pk]))
        mensaje.refresh_from_db()
        self.assertTrue(mensaje.revisada)
        self.entrar_como("MESERO")
        self.assertEqual(self.client.get(reverse("cliente:retroalimentacion_list")).status_code, 403)
