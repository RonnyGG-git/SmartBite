"""01 — Casos de uso de Inventario según el código de la app Django de Ronny
(rama smartbite): inventario/views.py, inventario/urls.py, reportes/views.py,
cocina/views.py y docs/PARIDAD-CASOS-DE-USO.md. UML 2.5.1 cláusula 18.

Solo se dibujan los casos que el código implementa (completos o en parte);
los que no existen van en una nota. Actores = roles del código:
JEFE_INVENTARIO, ADMINISTRADOR (puede todo lo del Jefe: ROLES_INVENTARIO lo
incluye) y JEFE_COCINA (solo lectura de inventario y faltantes en cocina).
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Casos de uso - Inventario", 1560, 1420)
d.titulo("Diagrama de casos de uso — Inventario (Smart Bite)",
         "Lo que la app Django (rama smartbite) permite hacer hoy en Inventario, según su código")

PASO = 88
fila = lambda i: 160 + (i - 1) * PASO  # noqa: E731
COL_A, COL_B, W_A, W_B, H = 330, 820, 260, 290, 62

SUJ_X, SUJ_Y, SUJ_W = 270, 100, 920
SUJ_H = fila(10) + H + 40 - SUJ_Y
d.sujeto("Inventario", SUJ_X, SUJ_Y, SUJ_W, SUJ_H, palabra_clave="subsystem")

jefe = d.actor("Jefe de\nInventario", 170, fila(4) + 20)
admin = d.actor("Administrador", 60, fila(9) + 20)

# Columna A: casos con actor directo
A = {}
for i, (clave, texto) in enumerate([
    ("01", "Registrar producto"), ("03", "Actualizar producto"), ("02", "Consultar inventario"),
    ("07", "Consultar movimientos\nde inventario"), ("05", "Registrar entrada\nde inventario"),
    ("06", "Registrar salida\nde inventario"), ("08", "Realizar ajuste\nde inventario"),
    ("10", "Registrar pérdida\nde producto"), ("04", "Controlar existencias"),
    ("12", "Generar reporte\nde inventario"),
], start=1):
    A[clave] = d.caso_uso(texto, COL_A, fila(i), W_A, H)

# Columna B: el que usa el Jefe de Cocina y los que se invocan con «include»
B = {
    "14": d.caso_uso("Consultar stock\ndisponible", COL_B, fila(2), W_B, H),
    "17": d.caso_uso("Registrar movimiento\nde inventario", COL_B, (fila(6) + fila(7)) // 2, W_B, H, VIOLETA),
    "11": d.caso_uso("Consultar stock mínimo", COL_B, fila(9), W_B, H, VIOLETA),
}

cocina = d.actor("Jefe de Cocina", 1290, fila(2) + 10)
compras = d.actor("Módulo de Compras", 1290, fila(5) - 10, tipo="sistema")

# Asociaciones
for clave in ["01", "03", "02", "07", "05", "06", "08", "10", "04"]:
    d.arista(jefe, A[clave], ASOCIACION + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(admin, A["12"], ASOCIACION + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(cocina, A["02"], ASOCIACION + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
d.arista(cocina, B["14"], ASOCIACION + "exitX=0;exitY=0.4;entryX=1;entryY=0.5;")
d.arista(compras, A["05"], ASOCIACION + "exitX=0;exitY=0.4;entryX=1;entryY=0.35;")

# El Administrador puede hacer todo lo del Jefe de Inventario (generalización entre actores)
d.arista(admin, jefe, GENERALIZACION + "exitX=0.5;exitY=0;entryX=0;entryY=0.45;")

# «include»: del caso base al incluido
d.arista(A["05"], B["17"], INCLUDE + "exitX=0.95;exitY=0.75;entryX=0.25;entryY=0.05;", "«include»")
d.arista(A["06"], B["17"], INCLUDE + "exitX=1;exitY=0.5;entryX=0;entryY=0.35;", "«include»")
d.arista(A["08"], B["17"], INCLUDE + "exitX=1;exitY=0.5;entryX=0;entryY=0.65;", "«include»")
d.arista(A["10"], B["17"], INCLUDE + "exitX=0.95;exitY=0.25;entryX=0.25;entryY=0.95;", "«include»")
d.arista(A["04"], B["11"], INCLUDE + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "«include»")
d.arista(A["12"], A["04"], INCLUDE + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;labelPosition=right;align=left;"
         "spacingLeft=6;", "«include»")

# Comentarios
y_n = SUJ_Y + SUJ_H + 25
d.nota("Entrada, salida, ajuste y pérdida usan el mismo formulario de ajuste (item_ajustar_stock, tipo ENTRADA o "
       "SALIDA), que suma o resta stock_actual y crea el MovimientoInventario. La recepción de una compra también "
       "registra ENTRADAS.\n"
       "En parte: «Registrar pérdida» es una salida con motivo (no hay tipo pérdida); «Generar reporte» es el "
       "listado de stock bajo del panel del Administrador; «Consultar stock disponible» son los insumos faltantes "
       "que ve cocina en cada orden y el stock en recetas.",
       SUJ_X, y_n, 640, 120, tam=11)
d.nota("No están en el código: Controlar productos próximos a vencer (CU-INV-09), Clasificar producto por "
       "categoría (CU-INV-13), Desactivar producto (CU-INV-16). Enviar solicitud de reabastecimiento (CU-INV-15) "
       "tampoco: el Jefe crea una compra a mano.",
       SUJ_X + 660, y_n, 530, 120, tam=11)
d.nota("Cabeza redonda = persona (rol del sistema: JEFE_INVENTARIO, ADMINISTRADOR, JEFE_COCINA). Cabeza cuadrada "
       "con «system» = otro módulo de Smart Bite. Flecha con triángulo hueco = generalización: el Administrador "
       "puede todo lo del Jefe de Inventario. En violeta: casos sin actor directo, se invocan con «include». "
       "Fuente: inventario/views.py, reportes/views.py, cocina/views.py y docs/PARIDAD-CASOS-DE-USO.md.",
       SUJ_X, y_n + 135, 1190, 58, tam=11)

d.alto = y_n + 215
d.guardar(*salida("01-casos-de-uso-inventario"))
print("ok", d.alto)
