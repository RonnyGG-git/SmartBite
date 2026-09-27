"""Datos mínimos compartidos por los tests de las apps (no se usa en producción)."""

from decimal import Decimal

from catalogo.models import Categoria, Producto
from cuentas.models import ROLES_SISTEMA, Rol, Usuario
from operativo.models import Mesa
from restaurantes.models import Restaurante, Sucursal


def crear_escenario():
    """Un restaurante con dos sucursales, una mesa en la primera y un platillo
    disponible en cada sucursal. Devuelve un dict con todo lo creado."""
    restaurante = Restaurante.objects.create(nombre="La Ceiba", nif="900123456", email="hola@laceiba.co", direccion="Cra 7 # 12-30")
    centro = Sucursal.objects.create(restaurante=restaurante, nombre="Centro")
    norte = Sucursal.objects.create(restaurante=restaurante, nombre="Norte")
    categoria = Categoria.objects.create(nombre="Platos fuertes")
    bandeja = Producto.objects.create(nombre="Bandeja paisa", precio=Decimal("32000"), categoria=categoria, sucursal=centro)
    ajiaco = Producto.objects.create(nombre="Ajiaco", precio=Decimal("28000"), categoria=categoria, sucursal=norte)
    mesa = Mesa.objects.create(numero=4, sucursal=centro)
    return {"centro": centro, "norte": norte, "categoria": categoria, "bandeja": bandeja, "ajiaco": ajiaco, "mesa": mesa}


def crear_usuario(rol_nombre, email=None):
    rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
    assert rol_nombre in dict(ROLES_SISTEMA)
    return Usuario.objects.create_user(email=email or f"{rol_nombre.lower()}@test.co", nombre=rol_nombre.title(), password="x", rol=rol)
