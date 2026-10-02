"""01 — Casos de uso de Inventario (17 CU-INV), según UML 2.5.1 cláusula 18.

Correcciones frente a la versión del 2026-09-28:
- Los módulos externos (Compras, Menú, Administración) son sistemas: antes
  tenían el mismo monigote que el Jefe de Almacén. Ahora llevan cabeza
  cuadrada y «system» (UML 18.1.4 permite otros íconos para actores no
  humanos; Ambler: «system» para actores que son sistemas).
- El sujeto lleva su nombre arriba a la izquierda y la palabra clave
  «subsystem» (Inventario es un subsistema de Smart Bite).
- Los casos extendidos muestran su compartimento 'extension points' y cada
  «extend» lleva su condición en una nota (UML 18.1.4, fig. 18.3).
- Ninguna elipse punteada: el borde punteado no tiene significado en UML.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Casos de uso - Inventario", 1560, 1500)
d.titulo("Diagrama de casos de uso — Inventario (Smart Bite)",
         "Qué puede hacer cada actor dentro del módulo de Inventario (CU-INV-01 a CU-INV-17)")

PASO = 88
FILAS = {}
y = 160
for i in range(1, 14):
    FILAS[i] = y
    # huecos bajo la fila 5 y la 11 para las notas de los dos «extend»
    y += PASO + (70 if i == 5 else 0) + (44 if i == 11 else 0)
fila = FILAS.__getitem__
COL_A, COL_B, W_A, W_B, H = 330, 820, 260, 290, 62

SUJ_X, SUJ_Y, SUJ_W = 270, 100, 920
SUJ_H = fila(13) + H + 40 - SUJ_Y
d.sujeto("Inventario", SUJ_X, SUJ_Y, SUJ_W, SUJ_H, palabra_clave="subsystem")

almacen = d.actor("Jefe de\nAlmacén", 150, (fila(1) + fila(13)) // 2)

# Columna A: los 13 casos con el Jefe de Almacén como actor
A = {}
for i, (clave, texto) in enumerate([
    ("01", "Registrar producto"), ("02", "Consultar inventario"), ("03", "Actualizar producto"),
    ("16", "Desactivar producto"), ("04", "Controlar existencias"), ("15", "Enviar solicitud de\nreabastecimiento"),
    ("05", "Registrar entrada\nde inventario"), ("06", "Registrar salida\nde inventario"),
    ("08", "Realizar ajuste\nde inventario"), ("07", "Consultar movimientos\nde inventario"),
    ("09", "Controlar productos\npróximos a vencer"), ("10", "Registrar pérdida\nde producto"),
    ("12", "Generar reporte\nde inventario"),
], start=1):
    if clave == "09":   # caso extendido: lleva su compartimento de puntos de extensión
        A[clave] = d.caso_uso(texto, COL_A - 10, fila(i) - 12, W_A + 20, H + 24,
                              puntos_extension=["producto vencido"])
    else:
        A[clave] = d.caso_uso(texto, COL_A, fila(i), W_A, H)

# Columna B: casos sin actor directo (se invocan con «include»/«extend»; 14 además lo usa Menú)
B = {
    "13": d.caso_uso("Clasificar producto\npor categoría", COL_B, fila(1), W_B, H, VIOLETA),
    "11": d.caso_uso("Consultar stock mínimo", COL_B, fila(5) - 14, W_B, H + 28, VIOLETA,
                     puntos_extension=["stock bajo el mínimo"]),
    "17": d.caso_uso("Registrar movimiento\nde inventario", COL_B, fila(8), W_B, H, VIOLETA),
    "14": d.caso_uso("Consultar stock\ndisponible", COL_B, fila(12), W_B, H, VIOLETA),
}

# Actores de sistema: monigote con cabeza cuadrada y «system» (UML 18.1.4 admite otros
# íconos para actores no humanos; Ambler: «system» para actores que son sistemas).
ACT_X = 1290
y_compras = (fila(6) + fila(7)) // 2 + H // 2 - 40
compras = d.actor("Módulo de Compras", ACT_X, y_compras, tipo="sistema")
menu = d.actor("Módulo de Menú", ACT_X, fila(12) - 70, tipo="sistema")
admin = d.actor("Módulo de\nAdministración", ACT_X, fila(13) - 20, tipo="sistema")

# Asociaciones actor – caso de uso (línea sólida, sin flecha), desde el hombro del monigote
for clave in A:
    d.arista(almacen, A[clave], ASOCIACION + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(compras, A["15"], ASOCIACION + "exitX=0;exitY=0.4;entryX=1;entryY=0.62;")
d.arista(compras, A["05"], ASOCIACION + "exitX=0;exitY=0.4;entryX=1;entryY=0.38;")
d.arista(menu, B["14"], ASOCIACION + "exitX=0;exitY=0.4;entryX=1;entryY=0.5;")
d.arista(admin, A["12"], ASOCIACION + "exitX=0;exitY=0.4;entryX=1;entryY=0.7;")

# «include»: del caso base al incluido. «extend»: del que extiende al extendido.
d.arista(A["01"], B["13"], INCLUDE, "«include»")
d.arista(A["04"], B["11"], INCLUDE + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "«include»")
# El primer «extend» pasa por un punto fijo P para que la nota se ancle justo sobre la flecha.
P = (760, fila(5) + H + 62)
d.arista(A["15"], B["11"], INCLUDE + "exitX=0.82;exitY=0.06;entryX=0.3;entryY=0.95;", "«extend»",
         puntos=[P])
d.arista(A["05"], B["17"], INCLUDE + "exitX=0.95;exitY=0.8;entryX=0.3;entryY=0;", "«include»")
d.arista(A["06"], B["17"], INCLUDE, "«include»")
d.arista(A["08"], B["17"], INCLUDE + "exitX=0.95;exitY=0.2;entryX=0.3;entryY=1;", "«include»")
d.arista(A["10"], A["09"], INCLUDE + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;labelPosition=left;align=right;"
         "spacingRight=6;", "«extend»")
d.arista(A["12"], B["14"], INCLUDE + "exitX=0.95;exitY=0.2;entryX=0.35;entryY=1;", "«include»")

# Condición y punto de extensión de cada «extend», en una nota anclada a la flecha
d.nota("condition: {el stock quedó bajo el mínimo y\nno hay una solicitud PENDIENTE del insumo}\n"
       "extension point: stock bajo el mínimo", 850, fila(5) + H + 34, 330, 62, tam=11)
d.ancla_a_punto(850, P[1], P[0], P[1])

# El segundo «extend» es vertical (de 10 a 09); su nota va a la derecha, en el hueco bajo la fila 11.
y_flecha = fila(12) - 22
d.nota("condition: {el producto ya venció}\nextension point: producto vencido",
       COL_A + W_A + 14, fila(12) - 52, 214, 46, tam=11)
d.ancla_a_punto(COL_A + W_A + 14, y_flecha, COL_A + W_A // 2, y_flecha)

# Leyenda (comentario)
y_ley = max(SUJ_Y + SUJ_H + 25, fila(13) - 20 + 80 + 60)   # debajo del nombre del último actor
d.nota("Monigote con cabeza redonda = persona. Cabeza cuadrada con «system» = sistema externo (otro módulo de "
       "Smart Bite).\n"
       "Línea sólida = asociación actor – caso de uso. Punteada con flecha abierta = «include» (del caso base al "
       "incluido, siempre ocurre) o «extend» (del que extiende al extendido, solo si se cumple la condición).\n"
       "En violeta: casos sin actor directo — 13, 11 y 17 se invocan desde otro caso; 14 además lo consulta el "
       "Módulo de Menú. Fuente: casos de uso CU-INV (LOGICA-DE-NEGOCIO.md).",
       SUJ_X, y_ley, SUJ_W + 270, 74, tam=12)

d.alto = y_ley + 110
d.guardar(*salida("01-casos-de-uso-inventario"))
print("ok", d.alto)
