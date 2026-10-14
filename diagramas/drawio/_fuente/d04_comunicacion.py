"""04 — Comunicación: recibir una compra (CU-COM-13, que registra las
entradas de inventario, CU-INV-05) tal como lo hace la app Django de Ronny:
inventario/views.py::compra_recibir. UML 2.5.1, 17.9.

- Líneas de vida 'nombre: Tipo' sin subrayar; enlaces sólidos; cada mensaje
  con su número anidado, guarda [..] e iteración *[..] (17.9).
- Dos mensajes por el mismo enlace van separados por coma.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Comunicación - Recibir compra", 1720, 1270)
d.titulo("Diagrama de comunicación — Recibir una compra y registrar las entradas (CU-COM-13, CU-INV-05)",
         "Cómo lo hace la vista compra_recibir de la app Django (rama smartbite)")
d.marco_diagrama("sd Recibir una compra", 30, 96, 1660, 1050)

H = 60
C = {"vista": (430, 630), "det": (980, 180), "compra": (980, 480), "item": (980, 780),
     "mov": (980, 1060), "bd": (1500, 780)}
W = {"vista": 220, "compra": 200, "det": 200, "item": 210, "mov": 230, "bd": 180}
NOMBRE = {"vista": "«vista»\n:compra_recibir", "compra": "compra: Compra", "det": "d: DetalleCompra",
          "item": "item: ItemInventario", "mov": ":MovimientoInventario", "bd": "bd: PostgreSQL"}
ID = {}
for k, (cx, cy) in C.items():
    ID[k] = d.vertice(esc(NOMBRE[k]), cx - W[k] / 2, cy - H / 2, W[k], H,
                      f"rounded=0;whiteSpace=wrap;html=1;{GRIS if k == 'bd' else AZUL}{FUENTE}fontSize=12;")

jefe = d.actor("Jefe de Inventario", 90, C["vista"][1] - 40)
d.arista(jefe, ID["vista"], LINK + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
for a, b in [("vista", "compra"), ("vista", "det"), ("vista", "item"), ("vista", "mov"),
             ("compra", "bd"), ("item", "bd"), ("mov", "bd")]:
    d.arista(ID[a], ID[b], LINK)

# Enlace de la vista consigo misma (sus propias llamadas)
vx, vy = C["vista"][0], C["vista"][1] - H / 2
d.flecha(vx - 50, vy, vx + 50, vy, LINK, puntos=[(vx - 50, vy - 50), (vx + 50, vy - 50)])
d.flecha(vx - 20, vy - 64, vx + 26, vy - 64, "html=1;endArrow=block;endFill=1;endSize=7;strokeColor=#333333;")
d.texto("1.1: compra := get_object_or_404(Compra, pk),\n1.2: usuario_tiene_rol(usuario, ROLES_INVENTARIO)",
        vx - 300, vy - 112, 420, 40, tam=12, alin="center", color="#222222")

NL = "\n"
m = d.mensaje_en_enlace
m((140, C["vista"][1]), (C["vista"][0] - W["vista"] / 2, C["vista"][1]), "1: POST" + NL + "compras/{pk}/recibir/",
  lado=-1)
m(C["vista"], C["compra"], NL.join(["1.3 [compra.estado = PENDIENTE]:", "detalles.select_related('item'),",
                                     "1.7: estado := RECIBIDA,", "save(update_fields = ['estado'])"]), lado=1, t=0.47)
m(C["vista"], C["det"], "1.4 *[para cada detalle d]:" + NL + "item, cantidad", lado=-1, t=0.6)
m(C["vista"], C["item"], NL.join(["1.5 *[para cada detalle d]:", "stock_actual += cantidad,",
                                   "save(update_fields = ['stock_actual'])"]), lado=-1, t=0.83)
m(C["vista"], C["mov"], NL.join(["1.6 *[para cada detalle d]:", "objects.create(item, tipo = ENTRADA,",
                                  "cantidad, motivo = 'Recepción compra #pk')"]), lado=1, t=0.6)
m(C["compra"], C["bd"], "1.7.1: UPDATE estado", lado=-1)
m(C["item"], C["bd"], "1.5.1: UPDATE stock_actual", lado=-1)
m(C["mov"], C["bd"], "1.6.1: INSERT movimiento", lado=1)

YN = 1170
d.nota("1.3 a 1.7 solo pasan si la compra está PENDIENTE, y todo dentro de transaction.atomic(): se confirma "
       "junto o no se guarda nada. 1.4, 1.5 y 1.6 se repiten juntas por cada detalle (primero se suma el stock "
       "del ítem y después se crea su ENTRADA). Si la compra no está PENDIENTE, no cambia nada.",
       30, YN, 820, 66, tam=11)
d.nota("Ejemplo: una compra PENDIENTE con 10 L de leche (stock 0) deja la leche en stock 10, una ENTRADA de 10 "
       "con motivo «Recepción compra #N» y la compra RECIBIDA. bd = PostgreSQL en Neon (smartbite_app) o SQLite.",
       870, YN, 820, 66, tam=11)

d.alto = YN + 95
d.guardar(*salida("04-comunicacion-recibir-compra"))
print("ok")
