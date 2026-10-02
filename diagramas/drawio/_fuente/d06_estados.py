"""06 — Estados según la app Django de Ronny (rama smartbite): la Compra
(campo estado: PENDIENTE, RECIBIDA, ANULADA; vistas compra_crear,
compra_recibir y compra_anular) y el nivel de stock de un ItemInventario
(propiedad stock_bajo). UML 2.5.1 cláusula 14.

- La transición que sale del inicial no lleva evento ni guarda (14.2.3.7):
  en el ítem va a una elección y las guardas están en sus salidas.
- Los pedidos que la vista ignora (recibir o anular una compra que ya no está
  PENDIENTE) son transiciones internas: el objeto no cambia de estado.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Estados - Inventario", 1520, 820)
d.titulo("Diagrama de estados — Compra y nivel de stock de un ítem (Smart Bite)",
         "Los estados que maneja hoy la app Django (rama smartbite)")


def tr(a, b, estilo="", valor="", puntos=()):
    d.arista(a, b, TRANSICION + estilo, valor, puntos=puntos)


# ---------------- Compra ----------------
d.marco_diagrama("stm Compra", 30, 100, 690, 600)
i0 = d.inicio(90, 190)
pend = d.estado("PENDIENTE", 240, 170, 220, 66)
rec = d.estado("RECIBIDA", 60, 470, 290, 96, VERDE,
               internas=["recibir / (no cambia nada)", "anular / (no cambia nada)"])
anu = d.estado("ANULADA", 400, 470, 290, 96, GRIS,
               internas=["recibir / (no cambia nada)", "anular / (no cambia nada)"])
tr(i0, pend, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.texto("/ guardar la compra y\nsus detalles (compra_crear)", 70, 230, 170, 36, tam=11, alin="center")
tr(pend, rec, "exitX=0.3;exitY=1;entryX=0.6;entryY=0;")
d.texto("recibir / sumar cada cantidad al\nstock de su ítem y crear una\nENTRADA por detalle", 40, 330, 230, 52,
        tam=11, alin="center")
tr(pend, anu, "exitX=0.7;exitY=1;entryX=0.4;entryY=0;")
d.texto("anular / (el stock\nno cambia)", 470, 340, 150, 36, tam=11, alin="center")
d.nota("RECIBIDA y ANULADA no tienen salida: ninguna vista las cambia. Recibir o anular otra vez no hace "
       "nada (la vista solo actúa si la compra está PENDIENTE).", 60, 600, 630, 56, tam=11)

# ---------------- Nivel de stock del ítem ----------------
d.marco_diagrama("stm ItemInventario (nivel de stock)", 750, 100, 740, 600)
i1 = d.inicio(800, 190)
elec = d.eleccion(1080, 188)
normal = d.estado("Stock normal", 800, 360, 260, 70, invariante="stock_actual > stock_minimo")
bajo = d.estado("Stock bajo", 1190, 360, 260, 70, AMARILLO, invariante="stock_actual ≤ stock_minimo")
tr(i1, elec, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.texto("/ crear el ítem con el stock_actual\ny el stock_minimo del formulario", 830, 140, 240, 36, tam=11,
        alin="center")
tr(elec, normal, "exitX=0;exitY=1;entryX=0.6;entryY=0;", "[else]")
tr(elec, bajo, "exitX=1;exitY=1;entryX=0.4;entryY=0;", "[stock_actual ≤ stock_minimo]")
tr(normal, bajo, "exitX=1;exitY=0.3;entryX=0;entryY=0.3;")
d.texto("salida, editar\n[stock_actual ≤ stock_minimo]", 1030, 326, 200, 36, tam=11, alin="center")
tr(bajo, normal, "exitX=0;exitY=0.75;entryX=1;entryY=0.75;")
d.texto("entrada, recibir compra, editar\n[stock_actual > stock_minimo]", 1030, 432, 200, 36, tam=11,
        alin="center")
d.nota("Eventos: entrada y salida = formulario de ajuste (item_ajustar_stock); recibir compra = compra_recibir; "
       "editar = formulario del ítem (item_editar), que deja cambiar stock_actual y stock_minimo a mano.\n"
       "El nivel no se guarda: es la propiedad stock_bajo, y el listado muestra «Stock bajo» o «Normal». "
       "No hay estado activo/inactivo: el modelo no tiene ese campo.", 780, 560, 690, 90, tam=11)

d.alto = 740
d.guardar(*salida("06-estados-inventario"))
print("ok")
