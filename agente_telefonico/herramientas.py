import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rapidfuzz import fuzz

from catalogo.models import Producto
from operativo.models import Cliente, Orden
from operativo.services import MAX_CANTIDAD_POR_LINEA, crear_orden

from .models import Llamada
from .notificaciones import notificar_cocina
from .texto import forma_canonica

logger = logging.getLogger(__name__)

UMBRAL_COINCIDENCIA = 78
MARGEN_AMBIGUEDAD = 4


def ultimos_digitos(telefono, cantidad=10):
    digitos = "".join(c for c in telefono or "" if c.isdigit())
    return digitos[-cantidad:]


def _producto_a_dict(producto):
    return {
        "id": producto.pk,
        "nombre": producto.nombre,
        "precio": producto.precio,
        "categoria": producto.categoria.nombre,
        "disponible": producto.disponible,
        "descripcion": producto.descripcion,
    }


class Herramientas:
    def __init__(self, llamada):
        self.llamada = llamada
        self.sucursal = llamada.sucursal

    def _productos(self):
        return Producto.objects.filter(sucursal=self.sucursal).select_related("categoria")

    def consultar_menu(self, categoria=None):
        productos = self._productos().filter(disponible=True)
        if categoria:
            productos = productos.filter(categoria__nombre__iexact=categoria)
        return [_producto_a_dict(p) for p in productos.order_by("categoria__nombre", "nombre")]

    def categorias(self):
        return sorted(set(self._productos().filter(disponible=True).values_list("categoria__nombre", flat=True)))

    def productos_agotados(self):
        return [_producto_a_dict(p) for p in self._productos() if not self.consultar_disponibilidad(p.pk, 1)["disponible"]]

    def buscar_producto(self, nombre):
        consulta = forma_canonica(nombre)
        if not consulta:
            return {"estado": "NO_ENCONTRADO", "consulta": nombre}
        puntuados = sorted(
            ((fuzz.token_set_ratio(consulta, forma_canonica(p.nombre)), p) for p in self._productos()),
            key=lambda par: (-par[0], len(par[1].nombre)),
        )
        if not puntuados or puntuados[0][0] < UMBRAL_COINCIDENCIA:
            return {"estado": "NO_ENCONTRADO", "consulta": nombre}
        exacto = [p for _, p in puntuados if forma_canonica(p.nombre) == consulta]
        if exacto:
            return {"estado": "ENCONTRADO", "producto": _producto_a_dict(exacto[0])}
        mejor_puntaje, mejor = puntuados[0]
        empatados = [p for s, p in puntuados if mejor_puntaje - s <= MARGEN_AMBIGUEDAD]
        if len(empatados) > 1:
            return {"estado": "AMBIGUO", "consulta": nombre, "opciones": [_producto_a_dict(p) for p in empatados[:4]]}
        return {"estado": "ENCONTRADO", "producto": _producto_a_dict(mejor)}

    def consultar_disponibilidad(self, producto_id, cantidad):
        producto = self._productos().prefetch_related("ingredientes__item_inventario").filter(pk=producto_id).first()
        if producto is None:
            return {"disponible": False, "motivo": "NO_EXISTE"}
        if not producto.disponible:
            return {"disponible": False, "motivo": "NO_DISPONIBLE"}
        if getattr(settings, "AGENTE_VALIDAR_STOCK", True):
            for ingrediente in producto.ingredientes.all():
                requerido = ingrediente.cantidad_requerida * cantidad
                if ingrediente.activo and ingrediente.item_inventario.stock_actual < requerido:
                    return {"disponible": False, "motivo": "SIN_STOCK"}
        return {"disponible": True, "motivo": ""}

    def ingredientes(self, producto_id):
        producto = self._productos().filter(pk=producto_id).prefetch_related("ingredientes__item_inventario").first()
        if producto is None:
            return []
        return [i.item_inventario.nombre for i in producto.ingredientes.all() if i.activo]

    def consultar_cliente(self, telefono):
        digitos = ultimos_digitos(telefono)
        if len(digitos) < 7:
            return None
        cliente = (
            Cliente.objects.filter(restaurante=self.sucursal.restaurante, telefono__endswith=digitos)
            .order_by("-actualizado_en")
            .first()
        )
        if cliente is None:
            return None
        return {"id": cliente.pk, "nombre": cliente.nombre, "telefono": cliente.telefono}

    def crear_cliente(self, datos):
        nombre = (datos.get("nombre") or "").strip()[:150]
        telefono = ultimos_digitos(datos.get("telefono"), 13)
        if not nombre:
            raise ValidationError("El cliente necesita un nombre.")
        restaurante = self.sucursal.restaurante
        existente = Cliente.objects.filter(restaurante=restaurante, nombre__iexact=nombre, telefono=telefono).first()
        if existente:
            return existente
        try:
            with transaction.atomic():
                return Cliente.objects.create(nombre=nombre, telefono=telefono, restaurante=restaurante)
        except IntegrityError:
            return None

    def _guardar_items(self, items):
        self.llamada.items = items
        self.llamada.resumen_leido = False
        self.llamada.save(update_fields=["items", "resumen_leido", "actualizado_en"])

    def agregar_producto_borrador(self, producto_id, cantidad):
        items = dict(self.llamada.items)
        return self._fijar_cantidad(items, producto_id, items.get(str(producto_id), 0) + cantidad)

    def modificar_producto_borrador(self, producto_id, cantidad):
        items = dict(self.llamada.items)
        if str(producto_id) not in items:
            return {"ok": False, "error": "NO_EN_PEDIDO"}
        return self._fijar_cantidad(items, producto_id, cantidad)

    def _fijar_cantidad(self, items, producto_id, cantidad):
        if not isinstance(cantidad, int) or not 1 <= cantidad <= MAX_CANTIDAD_POR_LINEA:
            return {"ok": False, "error": "CANTIDAD_INVALIDA"}
        disponibilidad = self.consultar_disponibilidad(producto_id, cantidad)
        if not disponibilidad["disponible"]:
            return {"ok": False, "error": disponibilidad["motivo"]}
        items[str(producto_id)] = cantidad
        self._guardar_items(items)
        return {"ok": True, "cantidad": cantidad}

    def eliminar_producto_borrador(self, producto_id):
        items = dict(self.llamada.items)
        if items.pop(str(producto_id), None) is None:
            return {"ok": False, "error": "NO_EN_PEDIDO"}
        self._guardar_items(items)
        return {"ok": True}

    def agregar_observacion(self, texto):
        actual = self.llamada.observaciones
        self.llamada.observaciones = (f"{actual}; {texto}" if actual else texto)[:300]
        self.llamada.resumen_leido = False
        self.llamada.save(update_fields=["observaciones", "resumen_leido", "actualizado_en"])
        return {"ok": True}

    def calcular_total_pedido(self):
        productos = {str(p.pk): p for p in self._productos().filter(pk__in=list(self.llamada.items))}
        lineas = []
        for producto_id, cantidad in self.llamada.items.items():
            producto = productos.get(producto_id)
            if producto is None:
                continue
            lineas.append({
                "producto_id": producto.pk,
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "precio_unitario": producto.precio,
                "subtotal": producto.precio * cantidad,
            })
        subtotal = sum((linea["subtotal"] for linea in lineas), Decimal("0"))
        impuestos = Decimal("0")
        cargos = Decimal("0")
        return {
            "lineas": lineas, "subtotal": subtotal, "impuestos": impuestos, "cargos": cargos,
            "total": subtotal + impuestos + cargos,
        }

    def cancelar_borrador_pedido(self):
        self.llamada.items = {}
        self.llamada.observaciones = ""
        self.llamada.resumen_leido = False
        self.llamada.save(update_fields=["items", "observaciones", "resumen_leido", "actualizado_en"])
        return {"ok": True}

    def confirmar_pedido(self, confirmacion_cliente):
        if confirmacion_cliente is not True:
            return {"ok": False, "error": "SIN_CONFIRMACION"}
        with transaction.atomic():
            llamada = Llamada.objects.select_for_update().get(pk=self.llamada.pk)
            self.llamada = llamada
            if llamada.orden_id:
                return {"ok": True, "pedido_id": llamada.orden_id, "duplicado": True, "aviso_cocina": True}
            if not llamada.abierta:
                return {"ok": False, "error": "LLAMADA_CERRADA"}
            if not llamada.items:
                return {"ok": False, "error": "PEDIDO_VACIO"}
            if not llamada.resumen_leido:
                return {"ok": False, "error": "RESUMEN_NO_LEIDO"}
            if not llamada.nombre_cliente or llamada.tipo_consumo not in dict(Orden.TIPO_CONSUMO_CHOICES):
                return {"ok": False, "error": "DATOS_INCOMPLETOS"}
            cliente = llamada.cliente or self.crear_cliente(
                {"nombre": llamada.nombre_cliente, "telefono": llamada.telefono_contacto}
            )
            try:
                orden = crear_orden(
                    sucursal=llamada.sucursal,
                    lineas=[(int(pk), cantidad) for pk, cantidad in llamada.items.items()],
                    origen=Orden.ORIGEN_TELEFONO,
                    tipo_consumo=llamada.tipo_consumo,
                    cliente=cliente,
                    estado=Orden.POR_CONFIRMAR,
                )
            except ValidationError as error:
                return {"ok": False, "error": "PRODUCTO_NO_DISPONIBLE", "detalle": error.messages[0]}
            llamada.orden = orden
            llamada.cliente = cliente
            llamada.save(update_fields=["orden", "cliente", "actualizado_en"])
        aviso_cocina = True
        try:
            notificar_cocina(orden)
        except Exception:
            logger.exception("No se pudo notificar a cocina la orden %s", orden.pk)
            aviso_cocina = False
            llamada.error = f"Orden #{orden.pk} registrada; falló la notificación a cocina."
            llamada.save(update_fields=["error", "actualizado_en"])
        return {"ok": True, "pedido_id": orden.pk, "duplicado": False, "aviso_cocina": aviso_cocina}

    def consultar_estado_pedido(self, pedido_id):
        telefono = ultimos_digitos(self.llamada.telefono_contacto or self.llamada.telefono_origen)
        orden = (
            Orden.objects.filter(pk=pedido_id, sucursal__restaurante=self.sucursal.restaurante)
            .select_related("cliente")
            .first()
        )
        if orden is None or len(telefono) < 7:
            return {"encontrado": False}
        telefonos = {ultimos_digitos(orden.cliente.telefono) if orden.cliente else ""}
        origen = Llamada.objects.filter(orden=orden).first()
        if origen:
            telefonos |= {ultimos_digitos(origen.telefono_origen), ultimos_digitos(origen.telefono_contacto)}
        if telefono not in telefonos:
            return {"encontrado": False}
        return {"encontrado": True, "pedido_id": orden.pk, "estado": orden.estado, "estado_texto": orden.get_estado_display()}
