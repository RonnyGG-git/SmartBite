"""05 — Actividades: ajustar el stock de un ítem (entrada o salida,
CU-INV-05/06/08) tal como lo hace la app Django de Ronny:
inventario/views.py::item_ajustar_stock. UML 2.5.1 cláusulas 15 y 16.

- Rombos vacíos; las condiciones son guardas [..] en cada salida (15.3.4.3).
- Fusión antes de "Elegir tipo…" para la vuelta desde los errores: entra por
  arriba y por la derecha, sale por abajo.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Actividades - Ajustar stock", 1340, 1345)
d.titulo("Diagrama de actividades — Ajustar el stock de un ítem (entrada o salida)",
         "Cómo lo hace la vista item_ajustar_stock de la app Django (rama smartbite)")

TOP, ALTO = 96, 1220
d.marco_diagrama("act Ajustar el stock de un ítem", 30, TOP - 6, 1290, ALTO + 20)
d.calle("Jefe de Inventario", 50, TOP + 30, 470, ALTO - 40)
d.calle("App Django (vista item_ajustar_stock)", 520, TOP + 30, 780, ALTO - 40)

AW, AH = 250, 56
N = {}


def act(k, texto, cx, cy, w=AW, h=AH):
    N[k] = d.accion(texto, cx - w / 2, cy - h / 2, w, h)


def dec(k, cx, cy):
    N[k] = d.decision(cx - 17, cy - 17)


def f(a, b, estilo="", valor="", puntos=()):
    d.arista(N[a], N[b], FLUJO + estilo, valor, puntos=puntos)


J, V = 285, 880
N["ini"] = d.inicio(J - 13, 190)
act("abrir", "Abrir el ítem y elegir\n«Ajustar stock»", J, 260)
dec("m0", J, 330)
act("elegir", "Elegir tipo (ENTRADA o SALIDA),\ncantidad y motivo, y enviar", J, 410, 270, 60)

dec("rol", V, 410)
act("redir1", "Redirigir al listado", 1150, 410, 200, 50)
N["fin1"] = d.fin(1135, 470)
act("validar", "Validar el formulario\n(AjusteStockForm)", V, 510)
dec("valido", V, 600)
act("errores", "Mostrar el formulario\ncon los errores", 1150, 600, 200, 56)
dec("tipo", V, 690)
act("sumar", "stock_actual :=\nstock_actual + cantidad", 730, 790, 230, 56)
act("restar", "stock_actual :=\nmax(0, stock_actual − cantidad)", 1040, 790, 250, 56)
dec("m1", V, 880)
act("guardar", "Guardar stock_actual\n(item.save)", V, 960)
act("mov", "Crear el MovimientoInventario\n(tipo, cantidad, motivo)", V, 1050, 270, 56)
act("redir2", "Redirigir al listado\nde inventario", V, 1140)
act("ver", "Ver el listado (el ítem dice\n«Stock bajo» si stock_actual\n≤ stock_minimo)", J, 1140, 260, 70)
N["fin"] = d.fin(J - 15, 1210)

f("ini", "abrir")
f("abrir", "m0")
f("m0", "elegir")
f("elegir", "rol", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
f("rol", "redir1", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "[sin rol ADMINISTRADOR\nni JEFE_INVENTARIO]")
f("redir1", "fin1", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
f("rol", "validar", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", "[else]")
f("validar", "valido")
f("valido", "errores", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "[no es válido]")
f("errores", "m0", "exitX=1;exitY=0.5;entryX=1;entryY=0.5;", puntos=[(1275, 600), (1275, 330)])
f("valido", "tipo", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", "[else]")
f("tipo", "sumar", "exitX=0;exitY=0.5;entryX=0.5;entryY=0;", "[tipo = ENTRADA]")
f("tipo", "restar", "exitX=1;exitY=0.5;entryX=0.5;entryY=0;", "[tipo = SALIDA]")
f("sumar", "m1", "exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
f("restar", "m1", "exitX=0.5;exitY=1;entryX=1;entryY=0.5;")
f("m1", "guardar")
f("guardar", "mov")
f("mov", "redir2")
f("redir2", "ver", "exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
f("ver", "fin")

d.nota("«Guardar stock_actual» y «Crear el MovimientoInventario» van dentro de transaction.atomic(): se "
       "confirman juntas o no se guarda ninguna.", 560, 1215, 340, 56, tam=11)
d.nota("Una salida mayor que el stock no se rechaza: max(0, …) deja el stock en 0. No hay tipo AJUSTE ni "
       "aprobación, y no se genera ninguna solicitud de reabastecimiento.", 920, 1215, 360, 56, tam=11)

d.alto = 1345
d.guardar(*salida("05-actividades-ajustar-stock"))
print("ok")
