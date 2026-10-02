"""06 — Estados: el insumo (activo/inactivo y su nivel de stock), el
movimiento de tipo AJUSTE (con aprobación) y la solicitud de
reabastecimiento. Fuente: sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql y, para la
solicitud atendida, el cierre de órdenes de Compras (RF-77 de la spec 002).

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1, cláusula 14):
- La transición que sale de un pseudoestado inicial no lleva evento ni
  guarda, solo efecto ('/ …') (14.2.3.7). Antes decía 'registrar insumo' y la
  de la solicitud tenía una guarda [..].
- El estado compuesto Activo entra por un pseudoestado de elección: un insumo
  nuevo con mínimo configurado empieza bajo el mínimo (stock 0).
- El texto dentro de cada estado sigue la sintaxis de sus compartimentos:
  invariante {..} junto al nombre (7.6.4) y transiciones internas
  'evento [guarda] / efecto' (14.2.4.4). El 'do /' del control de
  vencimientos era una actividad continua y en realidad es un evento diario.
- Las aclaraciones que flotaban como texto suelto ahora son comentarios.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Estados - Inventario", 1900, 1140)
d.titulo("Diagrama de estados — Inventario (Smart Bite)",
         "Cómo cambian el insumo, un movimiento de tipo AJUSTE y la solicitud de reabastecimiento")

T = dict(tam=11, color="#222222", alin="center")


def tr(a, b, estilo="", puntos=()):
    d.arista(a, b, TRANSICION + estilo, puntos=puntos)


# ============================================================ Insumo
d.marco_diagrama("stm Insumo (item_inventario)", 30, 100, 820, 1000)
i0 = d.inicio(62, 180)
activo = d.estado_compuesto("Activo", 150, 150, 670, 370, internas=[
    "generar_perdidas_vencimiento() [fecha_vencimiento < hoy y stock_actual > 0]",
    "        / SALIDA automática por todo el stock, una vez por día (RF-26, RF-38)"])
tr(i0, activo, "exitX=0.5;exitY=1;entryX=0;entryY=0.3;", puntos=[(75, 276)])
d.texto("/ stock_actual := 0;\ncodigo_unico := generado\n(RF-1)", 36, 290, 110, 52, **T)

i1 = d.inicio(180, 330)
elec = d.eleccion(250, 328)
tr(i1, elec, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
suf = d.estado("Stock suficiente", 350, 250, 200, 60, invariante="stock_minimo es NULL o\nstock_actual ≥ stock_minimo")
bajo = d.estado("Bajo el mínimo", 350, 420, 200, 60, AMARILLO, invariante="stock_actual < stock_minimo")
tr(elec, suf, "exitX=0.5;exitY=0;entryX=0;entryY=0.5;edgeStyle=orthogonalEdgeStyle;")
d.texto("[else]", 205, 268, 60, 18, **T)
tr(elec, bajo, "exitX=0.5;exitY=1;entryX=0;entryY=0.5;edgeStyle=orthogonalEdgeStyle;")
d.texto("[stock_actual <\nstock_minimo]", 160, 400, 100, 34, **T)
tr(suf, bajo, "exitX=0.8;exitY=1;entryX=0.8;entryY=0;")
d.texto("movimiento [stock_nuevo < stock_minimo]\n/ generar solicitud PENDIENTE\nsi no hay otra (RF-28, RF-29)",
        520, 350, 280, 50, tam=11, color="#222222", alin="left")
tr(bajo, suf, "exitX=0.2;exitY=0;entryX=0.2;entryY=1;")
d.texto("movimiento\n[stock_nuevo ≥\nstock_minimo]", 290, 340, 100, 50, **T)

inactivo = d.estado("Inactivo", 230, 690, 420, 74, GRIS,
                    internas=["desactivar / error «ya está inactivo» (RF-7)"])
tr(activo, inactivo, "exitX=0.25;exitY=1;entryX=0.25;entryY=0;")
d.texto("desactivar\n[no está en una orden\nde compra abierta (RF-6)]", 140, 570, 190, 50, **T)
tr(inactivo, activo, "exitX=0.75;exitY=0;entryX=0.75;entryY=1;")
d.texto("reactivar", 560, 600, 90, 18, **T)
n_in = d.nota("Inactivo: fuera del control de existencias y de vencimientos (RF-33, RF-34); no disponible para "
              "Menú (RF-35); se conserva con su historial (RF-5).", 60, 860, 440, 60, tam=11)
d.ancla(n_in, inactivo)
d.nota("RF-6 lo impone el script de Compras (tarea T16, pendiente): hoy la base solo rechaza desactivar un "
       "insumo que ya está inactivo.", 520, 860, 310, 60, tam=11)
d.nota("Las transiciones de Activo a Inactivo y de vuelta salen del borde del estado compuesto: valen en "
       "cualquiera de sus subestados. Al reactivar se entra de nuevo por la elección.", 60, 940, 770, 44, tam=11)

# ============================================================ Movimiento AJUSTE
X2 = 890
d.marco_diagrama("stm Movimiento de tipo AJUSTE (movimiento_inventario)", X2, 100, 980, 440)
a0 = d.inicio(X2 + 30, 300)
el2 = d.eleccion(X2 + 150, 298)
tr(a0, el2, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.texto("/ stock_anterior :=\nstock bloqueado", X2 + 10, 330, 140, 34, **T)
pend = d.estado("Pendiente de aprobación", X2 + 330, 160, 290, 92, AMARILLO,
                invariante="requiere_aprobacion = true y\nstock_nuevo es NULL",
                internas=["modificar o borrar / error (RF-18)"])
aplic = d.estado("Aplicado", X2 + 330, 390, 290, 92, VERDE, invariante="stock_nuevo = cantidad_objetivo",
                 internas=["aprobar / error: no hay nada pendiente (RF-17)", "modificar o borrar / error (RF-18)"])
tr(el2, pend, "exitX=0.5;exitY=0;entryX=0;entryY=0.5;edgeStyle=orthogonalEdgeStyle;")
d.texto("[|cantidad_objetivo − stock| > umbral]", X2 + 40, 182, 260, 18, **T)
tr(el2, aplic, "exitX=0.5;exitY=1;entryX=0;entryY=0.5;edgeStyle=orthogonalEdgeStyle;")
d.texto("[else] / stock_nuevo :=\ncantidad_objetivo", X2 + 170, 440, 160, 34, **T)
tr(pend, aplic, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
d.texto("aprobar(aprobado_por)\n/ stock_anterior := stock del momento;\nstock_nuevo := cantidad_objetivo;\n"
        "aprobado_en := now() (RF-17)", X2 + 485, 268, 260, 66, tam=11, color="#222222", alin="left")
d.nota("umbral = app.umbral_ajuste_aprobacion; si no se configura, 20 unidades (valor a confirmar). No hay "
       "estado de rechazo: un ajuste que no se aprueba queda pendiente.", X2 + 660, 390, 300, 92, tam=11)

# ============================================================ Solicitud de reabastecimiento
Y3 = 580
d.marco_diagrama("stm Solicitud de reabastecimiento (solicitud_reabastecimiento)", X2, Y3, 980, 520)
s0 = d.inicio(X2 + 30, Y3 + 200)
pen = d.estado("PENDIENTE", X2 + 200, Y3 + 130, 330, 166, internas=[
    "vincular a una orden de compra",
    "        / se asocia la orden (Compras)",
    "orden cancelada o rechazada",
    "        / se desvincula y sigue PENDIENTE (RF-78)"])
tr(s0, pen, "exitX=1;exitY=0.5;entryX=0;entryY=0.38;")
d.texto("/ cantidad_sugerida :=\nstock_minimo − stock_nuevo", X2 + 10, Y3 + 222, 180, 34, **T)
aten = d.estado("ATENDIDA", X2 + 660, Y3 + 70, 180, 50, VERDE)
canc = d.estado("CANCELADA", X2 + 660, Y3 + 330, 180, 50, GRIS)
tr(pen, aten, "exitX=1;exitY=0.15;entryX=0;entryY=0.5;")
d.texto("orden recibida o cerrada\ncon faltantes (Compras, RF-77)", X2 + 420, Y3 + 36, 200, 34, **T)
tr(pen, canc, "exitX=1;exitY=0.85;entryX=0;entryY=0.5;")
d.texto("cancelar", X2 + 580, Y3 + 340, 70, 18, **T)
f1 = d.fin(X2 + 900, Y3 + 80)
f2 = d.fin(X2 + 900, Y3 + 340)
tr(aten, f1, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
tr(canc, f2, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
n_crea = d.nota("Nace cuando un movimiento deja el stock bajo el mínimo y no hay otra solicitud PENDIENTE del "
                "insumo (RF-28, RF-29).", X2 + 20, Y3 + 50, 170, 92, tam=11)
d.ancla(n_crea, s0)
d.nota("El estado ENVIADA existe en la tabla, pero Compras no lo usa: la solicitud sigue PENDIENTE mientras dura "
       "la compra, y así el índice único (una sola PENDIENTE por insumo) evita duplicados. Después de ATENDIDA o "
       "CANCELADA, el próximo movimiento bajo el mínimo genera una solicitud nueva.", X2 + 20, Y3 + 420, 940, 64,
       tam=11)

d.guardar(*salida("06-estados-inventario"))
print("ok")
