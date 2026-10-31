from django.test import TestCase
from django.urls import reverse

from cuentas.models import Usuario


class SuperusuarioReportesTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_superuser("super@smartbite.test", "Super", "Clave-Larga-123")
        self.client.force_login(self.usuario)

    def test_dashboard_responde(self):
        self.assertEqual(self.client.get(reverse("reportes:dashboard")).status_code, 200)

    def test_reportes_responde(self):
        self.assertEqual(self.client.get(reverse("reportes:reportes")).status_code, 200)
