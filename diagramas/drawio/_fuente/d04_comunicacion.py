"""04 — Comunicación: CU-INV-08 Realizar ajuste de inventario, con la
aprobación del Administrador cuando la diferencia supera el umbral (RF-15,
RF-16, RF-17). Fuente: fn_movimiento_inventario_aplicar y
fn_movimiento_inventario_aprobar de sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql.

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1, 17.9):
- Marco 'sd' con el nombre de la interacción (tabla 17.3).
- Las líneas de vida no se subrayan en UML 2 (fig. 17.26); el subrayado es
  de los objetos del diagrama de objetos.
- Cada mensaje va pegado a su enlace con su flecha corta, incluidos 1 y 2
  (antes flotaban sobre los actores).
- '1.1.1.4.1 / 2.1.1.4.1' no es sintaxis UML: dos mensajes sobre el mismo
  enlace se separan con coma (fig. 17.26).
- Lo que el trigger escribe en la fila nueva (NEW) es un mensaje a
  :movimiento_inventario, no un lazo sobre el propio trigger.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Comunicación - Ajuste con aprobación", 2240, 1260)
d.titulo("Diagrama de comunicación — Realizar ajuste de inventario con aprobación (CU-INV-08)",
         "Un AJUSTE fija el stock en una cantidad objetivo con motivo (RF-15, RF-16); si la diferencia supera el "
         "umbral, no toca el stock hasta que lo aprueba el Administrador (RF-17)")

d.marco_diagrama("sd Realizar ajuste de inventario con aprobación", 30, 96, 2180, 1000)

H = 60
C = {
    "v_ajuste": (380, 220), "v_aprob": (380, 940),
    "mov": (650, 580),
    "aplicar": (1100, 220), "aprobar": (1100, 940),
    "item": (1500, 580),
    "fn": (1880, 580), "sol": (1880, 940),
}
W = {"v_ajuste": 200, "v_aprob": 200, "mov": 220, "aplicar": 280, "aprobar": 260, "item": 170, "fn": 280, "sol": 240}
CLAVE = {"v_ajuste": "vista", "v_aprob": "vista", "mov": "table", "aplicar": "trigger", "aprobar": "trigger",
         "item": "table", "fn": "function", "sol": "table"}
NOMBRE = {
    "v_ajuste": ":VistaAjuste", "v_aprob": ":VistaAprobacion", "mov": ":movimiento_inventario",
    "aplicar": ":trg_movimiento_inventario_20_aplicar", "aprobar": ":trg_movimiento_inventario_aprobar",
    "item": ":item_inventario", "fn": ":fn_generar_solicitud_si_hace_falta", "sol": ":solicitud_reabastecimiento",
}
ID = {}
for k, (cx, cy) in C.items():
    color = VIOLETA if CLAVE[k] in ("trigger", "function") else AZUL
    ID[k] = d.vertice(f"«{CLAVE[k]}»<br>{esc(NOMBRE[k])}", cx - W[k] / 2, cy - H / 2, W[k], H,
                      f"rounded=0;whiteSpace=wrap;html=1;{color}{FUENTE}fontSize=12;")

jefe = d.actor("Jefe de Almacén", 70, C["v_ajuste"][1] - 40)
admin = d.actor("Administrador", 70, C["v_aprob"][1] - 40)
d.arista(jefe, ID["v_ajuste"], LINK + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(admin, ID["v_aprob"], LINK + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
for a, b in [("v_ajuste", "mov"), ("v_aprob", "mov"), ("mov", "aplicar"), ("mov", "aprobar"),
             ("aplicar", "item"), ("aprobar", "item"), ("aplicar", "fn"), ("aprobar", "fn"), ("fn", "sol")]:
    d.arista(ID[a], ID[b], LINK)

# Cada mensaje del lado libre de su enlace (lado = +1/-1) y a la altura t (0..1) del enlace.
NL = "\n"
m = d.mensaje_en_enlace
ACT_J, ACT_A = (110, C["v_ajuste"][1]), (110, C["v_aprob"][1])
m(ACT_J, (C["v_ajuste"][0] - 100, C["v_ajuste"][1]), "1: registrar ajuste(" + NL + "cantidad_objetivo, motivo)",
  lado=-1)
m(ACT_A, (C["v_aprob"][0] - 100, C["v_aprob"][1]), "2: aprobar ajuste(" + NL + "movimiento)", lado=1)
m(C["v_ajuste"], C["mov"], "1.1: INSERT" + NL + "(tipo = AJUSTE)", lado=1)
m(C["v_aprob"], C["mov"], "2.1: UPDATE" + NL + "aprobado_por", lado=-1)
m(C["mov"], C["aplicar"], "1.1.1: BEFORE INSERT", lado=1, t=0.35)
m(C["aplicar"], C["mov"], NL.join(["1.1.1.3 [diferencia > umbral]:", "requiere_aprobacion := true,",
                                    "stock_nuevo := NULL"]), lado=1, t=0.6)
m(C["mov"], C["aprobar"], "2.1.1: BEFORE UPDATE", lado=-1, t=0.35)
m(C["aprobar"], C["mov"], NL.join(["2.1.1.3: stock_anterior := stock del momento,", "stock_nuevo := cantidad_objetivo,",
                                    "aprobado_en := now()"]), lado=-1, t=0.6)
m(C["aplicar"], C["item"], NL.join(["1.1.1.1: SELECT stock_actual FOR UPDATE,", "1.1.1.2 [diferencia ≤ umbral]:",
                                     "UPDATE stock_actual = cantidad_objetivo"]), lado=1)
m(C["aprobar"], C["item"], NL.join(["2.1.1.1: SELECT stock_actual FOR UPDATE,", "2.1.1.2: UPDATE stock_actual",
                                     "= cantidad_objetivo"]), lado=-1)
m(C["aplicar"], C["fn"], NL.join(["1.1.1.4 [diferencia ≤ umbral]:", "fn_generar_solicitud_si_hace_falta(",
                                   "item_inventario_id, cantidad_objetivo)"]), lado=-1, t=0.6)
m(C["aprobar"], C["fn"], NL.join(["2.1.1.4: fn_generar_solicitud_si_hace_falta(",
                                   "item_inventario_id, cantidad_objetivo)"]), lado=1, t=0.6)
m(C["fn"], C["sol"], NL.join(["1.1.1.4.1 [cantidad_objetivo", "< stock_minimo]: INSERT PENDIENTE,",
                               "2.1.1.4.1 [cantidad_objetivo", "< stock_minimo]: INSERT PENDIENTE"]), lado=-1)

YN = 1120
d.nota("umbral = app.umbral_ajuste_aprobacion; si no se configura, 20 unidades (valor de negocio a confirmar "
       "con el Administrador).", 30, YN, 560, 50)
d.nota("Un ajuste se aprueba una sola vez. El esquema no tiene rechazo: un ajuste que no se aprueba queda "
       "pendiente y no cambia el stock.", 620, YN, 560, 50)
d.nota("«vista» = vista de Django que llega con la spec 003 (hoy Django solo registra ENTRADA y SALIDA). "
       "Numeración decimal: 1.1.1 ocurre dentro de 1.1; [ ] = guarda; dos mensajes en un mismo enlace van "
       "separados por coma.", 1210, YN, 1000, 50)

d.alto = YN + 80
d.guardar(*salida("04-comunicacion-ajuste-con-aprobacion"))
print("ok")
