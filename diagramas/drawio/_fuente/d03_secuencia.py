"""03 — Secuencia: CU-INV-06 Registrar salida de inventario, con la base de
Neon (fn_movimiento_inventario_aplicar y fn_generar_solicitud_si_hace_falta
de sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql).

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1 cláusula 17):
- Marco 'sd' con el nombre de la interacción (17.2.4).
- Cabeceras con la sintaxis <nombre>[: <Tipo>] (17.3.4) y la palabra clave
  arriba; nada de texto suelto entre paréntesis.
- La respuesta vuelve siempre a quien hizo la llamada: el RAISE del trigger
  vuelve a :movimiento_inventario y de ahí a la vista (antes saltaba directo
  a la vista).
- El segundo operando del alt usa la guarda [else].
- El mensaje a sí mismo abre una activación anidada.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Secuencia - Registrar salida", 1720, 1130)
d.titulo("Diagrama de secuencia — Registrar salida de inventario (CU-INV-06)",
         "Del formulario de Django a los triggers de PostgreSQL (Neon): control de stock (RF-13, RF-14) y solicitud "
         "automática de reabastecimiento (RF-28, RF-29)")

MARCO_X, MARCO_Y, MARCO_W = 30, 96, 1660
TOP, FIN = 140, 960
d.marco_diagrama("sd Registrar salida de inventario", MARCO_X, MARCO_Y, MARCO_W, FIN - MARCO_Y + 20)

lineas = [  # (palabra clave, nombre, centro x, ancho)
    ("vista", ":item_ajustar_stock", 300, 200),
    ("table", ":movimiento_inventario", 545, 210),
    ("trigger", ":trg_movimiento_inventario_20_aplicar", 815, 270),
    ("table", ":item_inventario", 1070, 170),
    ("function", ":fn_generar_solicitud_si_hace_falta", 1320, 260),
    ("table", ":solicitud_reabastecimiento", 1565, 210),
]
JEFE, VISTA, MOV, TRG, ITEM, FN, SOL = range(7)
X = {JEFE: 100}
d.actor_de_secuencia("Jefe de Almacén", X[JEFE], TOP, FIN)
for i, (clave, nombre, cx, w) in enumerate(lineas, start=1):
    color = VIOLETA if clave in ("trigger", "function") else AZUL
    d.linea_de_vida(nombre, cx - w / 2, TOP, w, FIN - TOP, palabra_clave=clave, color=color)
    X[i] = cx

# Especificaciones de ejecución (activaciones)
d.activacion(X[VISTA], 225, 905)
d.activacion(X[VISTA], 262, 290, desplazamiento=8)      # anidada: validar el formulario
d.activacion(X[MOV], 315, 865)
d.activacion(X[TRG], 355, 825)
d.activacion(X[ITEM], 395, 430)
d.activacion(X[ITEM], 625, 650)
d.activacion(X[FN], 670, 780)
d.activacion(X[SOL], 735, 760)


def msg(origen, destino, y, texto, respuesta=False):
    x1, x2 = X[origen], X[destino]
    ajuste = 6 if x2 > x1 else -6
    d.flecha(x1 + ajuste, y, x2 - ajuste, y, RESPUESTA if respuesta else MENSAJE, texto)


msg(JEFE, VISTA, 230, "1: registrar salida(cantidad, motivo)")
# mensaje a sí mismo: sale de la activación y entra a la anidada
xv = X[VISTA] + 6
d.flecha(xv, 250, xv + 8, 268, MENSAJE + "align=left;spacingLeft=4;", "2: validar AjusteStockForm",
         puntos=[(xv + 50, 250), (xv + 50, 268)])
msg(VISTA, MOV, 320, "3: INSERT (tipo = SALIDA)")
msg(MOV, TRG, 360, "4: BEFORE INSERT")
msg(TRG, ITEM, 400, "5: SELECT stock_actual FOR UPDATE")
msg(ITEM, TRG, 428, "stock_actual", respuesta=True)

# alt: stock insuficiente / suficiente
d.fragmento("alt", MARCO_X + 20, 450, MARCO_W - 40, 470, "[stock_actual − cantidad < 0]  (RF-14)")
msg(TRG, MOV, 495, "6: RAISE 'Stock insuficiente…'", respuesta=True)
msg(MOV, VISTA, 528, "7: error check_violation (ROLLBACK)", respuesta=True)
msg(VISTA, JEFE, 560, "8: muestra el error", respuesta=True)
d.separador(MARCO_X + 20, MARCO_X + MARCO_W - 20, 585, "[else]")
msg(TRG, ITEM, 630, "9: UPDATE stock_actual = stock_nuevo  (RF-13)")
msg(TRG, FN, 675, "10: fn_generar_solicitud_si_hace_falta(item_inventario_id, stock_nuevo)")
d.fragmento("opt", 1060, 695, 590, 80, "[stock_minimo no es NULL y stock_nuevo < stock_minimo]", ancho_etiqueta=50)
msg(FN, SOL, 745, "11: INSERT (cantidad_sugerida = stock_minimo − stock_nuevo)")
msg(TRG, MOV, 820, "12: NEW con stock_anterior y stock_nuevo", respuesta=True)
msg(MOV, VISTA, 860, "13: INSERT confirmado (COMMIT)", respuesta=True)
msg(VISTA, JEFE, 900, "14: redirige al listado", respuesta=True)

# Comentarios
YN = FIN + 50
d.nota("Ejemplo (el mismo del diagrama de objetos): Leche entera con stock 10 y mínimo 5. Salida de 7 → "
       "stock 3 → solicitud PENDIENTE de 2.", 30, YN, 520, 54)
d.nota("RF-29: si el insumo ya tiene una solicitud PENDIENTE, el índice único rechaza la segunda "
       "(unique_violation), la función la ignora y el movimiento sigue.", 570, YN, 520, 54)
d.nota("Antes de este trigger corre trg_movimiento_inventario_10_evitar_perdida_duplicada (solo actúa en pérdidas "
       "por vencimiento, RF-38). Hoy la vista de Django suma y resta stock_actual en Python; se adapta en la spec 003.",
       1110, YN, 580, 54)
d.nota("Palabras clave de las cabeceras: «vista» = función de inventario/views.py (Django); «table» = tabla; "
       "«trigger» = trigger de PostgreSQL; «function» = función de PostgreSQL. Flecha llena = llamada síncrona; "
       "punteada = respuesta.", 30, YN + 66, 1660, 40)

d.alto = YN + 130
d.guardar(*salida("03-secuencia-registrar-salida"))
print("ok")
