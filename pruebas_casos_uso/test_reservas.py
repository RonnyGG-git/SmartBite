from datetime import timedelta
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from cliente.views import SESION_RESERVAS
from cuentas.models import Rol, Usuario
from operativo.forms import CrearOrdenForm
from operativo.models import Mesa, Orden, Reserva
from operativo.services import (
    cancelar_reserva,
    confirmar_llegada,
    crear_reserva,
    horarios_alternativos,
    sincronizar_reservas,
)
from restaurantes.models import Restaurante, Sucursal

from .base import CLAVE, CasoDeUsoTestCase


def _en(horas=0, minutos=0, dias=0):
    base = timezone.now().replace(second=0, microsecond=0)
    return base + timedelta(days=dias, hours=horas, minutes=minutos)


class ReservaServicioTests(CasoDeUsoTestCase):
    def reservar(self, cuando=None, personas=2, nombre="Andrés", telefono="3001234567"):
        return crear_reserva(self.sucursal, cuando or _en(dias=1), personas, nombre, telefono)

    def test_cu_ped_27_crea_reserva_confirmada_con_codigo(self):
        reserva = self.reservar()
        self.assertEqual(reserva.estado, Reserva.CONFIRMADA)
        self.assertEqual(reserva.mesa, self.mesa)
        self.assertEqual(len(reserva.codigo), 8)
        self.assertEqual(reserva.cliente.telefono, "3001234567")
        self.assertEqual(reserva.cliente.restaurante, self.restaurante)

    def test_cu_ped_27_elige_la_mesa_mas_pequena_que_alcanza(self):
        grande = Mesa.objects.create(numero=2, capacidad=8, sucursal=self.sucursal)
        self.assertEqual(self.reservar(personas=2).mesa, self.mesa)
        self.assertEqual(self.reservar(personas=6).mesa, grande)

    def test_cu_ped_27_exige_anticipacion_minima(self):
        with self.assertRaises(ValidationError) as error:
            self.reservar(cuando=_en(minutos=30))
        self.assertEqual(error.exception.code, "anticipacion")

    def test_cu_ped_27_no_permite_reservar_tan_lejos(self):
        with self.assertRaises(ValidationError) as error:
            self.reservar(cuando=_en(dias=61))
        self.assertEqual(error.exception.code, "horizonte")

    def test_cu_ped_27_rechaza_grupos_mas_grandes_que_las_mesas(self):
        with self.assertRaises(ValidationError) as error:
            self.reservar(personas=10)
        self.assertEqual(error.exception.code, "capacidad")

    def test_cu_ped_27_exige_nombre_y_telefono(self):
        with self.assertRaises(ValidationError) as error:
            self.reservar(telefono=" ")
        self.assertEqual(error.exception.code, "datos")

    def test_cu_ped_27_dos_reservas_no_se_solapan_en_la_misma_mesa(self):
        cuando = _en(dias=1)
        self.reservar(cuando=cuando)
        with self.assertRaises(ValidationError) as error:
            self.reservar(cuando=cuando + timedelta(hours=1))
        self.assertEqual(error.exception.code, "sin_mesa")
        self.assertEqual(self.reservar(cuando=cuando + Reserva.DURACION).mesa, self.mesa)

    def test_cu_ped_27_usa_otra_mesa_si_la_primera_esta_reservada(self):
        otra = Mesa.objects.create(numero=2, capacidad=4, sucursal=self.sucursal)
        cuando = _en(dias=1)
        self.reservar(cuando=cuando)
        self.assertEqual(self.reservar(cuando=cuando).mesa, otra)

    def test_cu_ped_27_mesas_inactivas_o_de_otra_sucursal_no_cuentan(self):
        Mesa.objects.create(numero=1, capacidad=4, sucursal=self.otra_sucursal)
        Mesa.objects.create(numero=3, capacidad=4, sucursal=self.sucursal, activa=False)
        cuando = _en(dias=1)
        self.reservar(cuando=cuando)
        with self.assertRaises(ValidationError):
            self.reservar(cuando=cuando)

    def test_cu_ped_27_propone_horarios_alternativos_libres(self):
        cuando = _en(dias=1)
        self.reservar(cuando=cuando)
        alternativas = horarios_alternativos(self.sucursal, cuando, 2)
        self.assertTrue(alternativas)
        for alternativa in alternativas:
            self.assertGreaterEqual(abs(alternativa - cuando), Reserva.DURACION)
        self.assertEqual(min(abs(a - cuando) for a in alternativas), Reserva.DURACION)
        self.assertEqual(alternativas, sorted(alternativas))

    def test_cu_ped_27_cancelar_libera_el_horario(self):
        cuando = _en(dias=1)
        reserva = self.reservar(cuando=cuando)
        cancelar_reserva(reserva)
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.CANCELADA)
        self.assertEqual(self.reservar(cuando=cuando).mesa, self.mesa)
        with self.assertRaises(ValidationError):
            cancelar_reserva(reserva)


class ReservaEstadosTests(CasoDeUsoTestCase):
    def reserva_directa(self, cuando, mesa=None):
        return Reserva.objects.create(
            mesa=mesa or self.mesa, codigo=f"T{Reserva.objects.count():07d}", fecha_hora=cuando,
            num_personas=2, nombre="Andrés", telefono="300",
        )

    def estado_mesa(self):
        return Mesa.objects.get(pk=self.mesa.pk).estado

    def test_la_mesa_pasa_a_reservada_al_abrirse_la_ventana(self):
        self.reserva_directa(_en(horas=3))
        sincronizar_reservas()
        self.assertEqual(self.estado_mesa(), Mesa.DISPONIBLE)
        self.reserva_directa(_en(minutos=20))
        sincronizar_reservas()
        self.assertEqual(self.estado_mesa(), Mesa.RESERVADA)

    def test_una_mesa_ocupada_no_pasa_a_reservada(self):
        self.crear_orden()
        self.reserva_directa(_en(minutos=20))
        sincronizar_reservas()
        self.assertEqual(self.estado_mesa(), Mesa.OCUPADA)

    def test_sin_asistencia_tras_la_tolerancia_libera_la_mesa(self):
        reserva = self.reserva_directa(_en(minutos=10))
        sincronizar_reservas()
        sincronizar_reservas(ahora=reserva.fecha_hora + Reserva.TOLERANCIA + timedelta(minutes=1))
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.NO_ASISTIO)
        self.assertEqual(self.estado_mesa(), Mesa.DISPONIBLE)

    def test_cancelar_en_la_ventana_libera_la_mesa(self):
        reserva = self.reserva_directa(_en(minutos=10))
        sincronizar_reservas()
        cancelar_reserva(reserva)
        self.assertEqual(self.estado_mesa(), Mesa.DISPONIBLE)

    def test_cu_ped_04_confirmar_llegada_ocupa_la_mesa(self):
        reserva = self.reserva_directa(_en(minutos=5))
        sincronizar_reservas()
        confirmar_llegada(reserva)
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.CUMPLIDA)
        self.assertEqual(self.estado_mesa(), Mesa.OCUPADA)

    def test_cu_ped_04_no_confirma_fuera_de_horario(self):
        reserva = self.reserva_directa(_en(horas=5))
        with self.assertRaises(ValidationError) as error:
            confirmar_llegada(reserva)
        self.assertEqual(error.exception.code, "fuera_de_horario")

    def test_comando_actualizar_reservas(self):
        reserva = self.reserva_directa(_en(minutos=-30))
        salida = StringIO()
        call_command("actualizar_reservas", stdout=salida)
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.NO_ASISTIO)
        self.assertIn("Sin asistencia: 1", salida.getvalue())


class ReservaClienteTests(CasoDeUsoTestCase):
    def elegir_sucursal(self):
        self.client.get(reverse("cliente:sucursal", args=[self.sucursal.pk]))

    def datos(self, cuando=None, personas=2):
        cuando = timezone.localtime(cuando or _en(dias=1))
        return {
            "fecha": cuando.strftime("%Y-%m-%d"), "hora": cuando.strftime("%H:%M"),
            "num_personas": personas, "nombre": "Andrés", "telefono": "3001234567",
        }

    def test_cu_ped_27_sin_restaurante_elegido_vuelve_al_directorio(self):
        respuesta = self.client.get(reverse("cliente:reservar"))
        self.assertRedirects(respuesta, reverse("cliente:restaurantes"))

    def test_cu_ped_27_cliente_reserva_y_ve_su_codigo(self):
        self.elegir_sucursal()
        self.assertEqual(self.client.get(reverse("cliente:reservar")).status_code, 200)
        respuesta = self.client.post(reverse("cliente:reservar"), self.datos())
        reserva = Reserva.objects.get()
        self.assertRedirects(respuesta, reverse("cliente:reserva", args=[reserva.codigo]))
        self.assertIn(reserva.codigo, self.client.session[SESION_RESERVAS])
        pagina = self.client.get(reverse("cliente:reserva", args=[reserva.codigo.lower()]))
        self.assertContains(pagina, reserva.codigo)
        self.assertContains(pagina, "Cancelar reserva")

    def test_cu_ped_27_sin_mesa_libre_muestra_alternativas(self):
        self.elegir_sucursal()
        cuando = _en(dias=1)
        self.client.post(reverse("cliente:reservar"), self.datos(cuando))
        respuesta = self.client.post(reverse("cliente:reservar"), self.datos(cuando))
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertContains(respuesta, "No hay mesas libres a esa hora.")
        self.assertTrue(respuesta.context["alternativas"])

    def test_cu_ped_27_fecha_pasada_se_rechaza(self):
        self.elegir_sucursal()
        respuesta = self.client.post(reverse("cliente:reservar"), self.datos(_en(horas=-2)))
        self.assertContains(respuesta, "anticipación")
        self.assertFalse(Reserva.objects.exists())

    def test_cu_ped_27_cliente_cancela_con_su_codigo(self):
        reserva = crear_reserva(self.sucursal, _en(dias=1), 2, "Andrés", "300")
        self.client.post(reverse("cliente:cancelar_reserva", args=[reserva.codigo]))
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.CANCELADA)

    def test_codigo_inexistente_da_404(self):
        self.assertEqual(self.client.get(reverse("cliente:reserva", args=["NOEXISTE"])).status_code, 404)

    def test_qr_de_mesa_reservada_no_la_asigna(self):
        Reserva.objects.create(
            mesa=self.mesa, codigo="QRTEST01", fecha_hora=_en(minutos=10), num_personas=2, nombre="A", telefono="1"
        )
        respuesta = self.escanear_qr(tipo=None)
        self.assertRedirects(respuesta, reverse("cliente:menu"))
        self.assertEqual(Mesa.objects.get(pk=self.mesa.pk).estado, Mesa.RESERVADA)


class ReservaMeseroTests(CasoDeUsoTestCase):
    def reserva_en_ventana(self):
        return Reserva.objects.create(
            mesa=self.mesa, codigo="MESERO01", fecha_hora=_en(minutos=10), num_personas=2, nombre="Andrés", telefono="1"
        )

    def test_cu_ped_04_mesero_ve_y_confirma_la_reserva(self):
        reserva = self.reserva_en_ventana()
        self.entrar_como("MESERO")
        mesas = self.client.get(reverse("operativo:mesas_list"))
        self.assertContains(mesas, "MESERO01")
        self.assertContains(mesas, "Confirmar llegada")
        respuesta = self.client.post(reverse("operativo:confirmar_reserva", args=[reserva.pk]))
        self.assertRedirects(
            respuesta, f"{reverse('operativo:crear_orden')}?mesaId={self.mesa.pk}", fetch_redirect_response=False
        )
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.CUMPLIDA)
        self.assertIn(self.mesa, CrearOrdenForm().fields["mesa"].queryset)
        self.client.post(reverse("operativo:crear_orden"), {"mesa": self.mesa.pk})
        self.assertEqual(Orden.objects.get().mesa, self.mesa)

    def test_mesa_reservada_no_se_ofrece_para_nueva_orden(self):
        self.reserva_en_ventana()
        sincronizar_reservas()
        self.assertNotIn(self.mesa, CrearOrdenForm().fields["mesa"].queryset)

    def test_mesa_con_orden_activa_no_se_ofrece_para_nueva_orden(self):
        self.crear_orden()
        self.assertNotIn(self.mesa, CrearOrdenForm().fields["mesa"].queryset)

    def test_mesero_cancela_una_reserva(self):
        reserva = self.reserva_en_ventana()
        self.entrar_como("MESERO")
        self.client.post(reverse("operativo:cancelar_reserva", args=[reserva.pk]))
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.CANCELADA)

    def test_otro_restaurante_no_ve_ni_toca_la_reserva(self):
        reserva = self.reserva_en_ventana()
        ajeno = Restaurante.objects.create(nombre="Ajeno", nif="900000000-9", email="a@a.co", direccion="x")
        Sucursal.objects.create(restaurante=ajeno, nombre="Única")
        mesero = Usuario.objects.create_user(
            email="ajeno@a.co", nombre="Ajeno", password=CLAVE, rol=Rol.objects.get(nombre="MESERO"), restaurante=ajeno
        )
        self.client.force_login(mesero)
        self.assertNotContains(self.client.get(reverse("operativo:mesas_list")), "MESERO01")
        self.assertEqual(self.client.post(reverse("operativo:confirmar_reserva", args=[reserva.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("operativo:cancelar_reserva", args=[reserva.pk])).status_code, 404)
        self.assertEqual(Reserva.objects.get(pk=reserva.pk).estado, Reserva.CONFIRMADA)
