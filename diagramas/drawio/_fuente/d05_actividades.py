"""05 — Actividades: Registrar un movimiento de inventario (CU-INV-17, con
las entradas, salidas y ajustes de CU-INV-05/06/08) y Aprobar un ajuste
pendiente (RF-17). Fuente: los triggers de movimiento_inventario en
sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql.

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1, cláusulas 15-16):
- Rombos vacíos: la condición va como guarda [..] en cada flujo de salida
  (15.3.4.3, 15.2.4), no escrita dentro del rombo.
- Flujos con punta abierta (15.2.4).
- La aprobación del Administrador es otra actividad: el ajuste grande se
  confirma (COMMIT) sin tocar el stock y el Administrador lo aprueba después,
  en otra transacción. Antes el flujo del Jefe esperaba al Administrador.
  Se unen con una señal: enviar señal (pentágono convexo) en la primera y
  aceptar evento (pentágono cóncavo) en la segunda (16.3.4, 16.10.4).
- La fusión del principio ya no tiene la entrada y la salida del mismo lado.
- Cada actividad va en su marco 'act' con sus particiones (calles).
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Actividades - Registrar movimiento", 2460, 1960)
d.titulo("Diagrama de actividades — Registrar un movimiento de inventario y aprobar un ajuste (CU-INV-17, RF-17)",
         "Entrada, salida o ajuste: quién hace cada paso y qué valida la base de datos (RF-12 a RF-20, RF-28, RF-29, "
         "RF-38); un ajuste grande lo aprueba el Administrador en otra actividad")

nodos = {}
AW, AH = 180, 56


def act(clave, texto, cx, cy, w=AW, h=AH, color=AZUL):
    nodos[clave] = d.accion(texto, cx - w / 2, cy - h / 2, w, h, color)


def rombo(clave, cx, cy):
    nodos[clave] = d.decision(cx - 17, cy - 17)


def fin(clave, cx, cy):
    nodos[clave] = d.fin(cx - 15, cy - 15)


def f(a, b, estilo="", guarda="", puntos=()):
    d.arista(nodos[a], nodos[b], FLUJO + estilo, guarda, puntos=puntos)


# ============================================================ actividad 1
TOP, BAJO = 100, 1830
d.marco_diagrama("act Registrar un movimiento de inventario", 30, TOP, 1500, BAJO - TOP + 20)
LT = TOP + 40
for nombre, x, w in [("Jefe de Almacén", 50, 330), ("Django (vista)", 380, 320),
                     ("Base de datos (PostgreSQL en Neon)", 700, 810)]:
    d.calle(nombre, x, LT, w, BAJO - LT)

J, DJ = 215, 540
c1, c2, c3, c4, c5 = 800, 965, 1130, 1280, 1430

# --- Jefe de Almacén
nodos["ini"] = d.inicio(J - 13, 200)
act("elegir", "Elegir el insumo y el\ntipo de movimiento", J, 275)
rombo("d_tipo", J, 360)
act("cantidad", "Indicar cantidad y motivo\n(en una pérdida, la causa)", 135, 445, 160, 58)
act("objetivo", "Indicar cantidad\nobjetivo y motivo", 300, 445, 140, 58)
rombo("m1", J, 540)
act("corregir", "Corregir los datos", J, 640, 160, 50)

# --- Django
act("validar", "Validar el formulario", DJ, 540)
rombo("d_valido", DJ, 640)
act("insert", "INSERT en\nmovimiento_inventario", DJ, 740)
act("commit", "Confirmar (COMMIT) y\nvolver al listado", DJ, 1700)
fin("fin", DJ, 1790)

# --- Base de datos
rombo("d_dup", c3, 740)
act("rech_dup", "Rechazar: pérdida por\nvencimiento repetida (RF-38)", 1405, 740, 190, 56, ROJO)
fin("fin_dup", 1405, 820)
act("bloquear", "Bloquear el insumo\n(SELECT … FOR UPDATE)", c3, 840)
rombo("d_tipo_bd", c3, 930)
rombo("d_alcanza", c2, 930)
act("rech_stock", "Rechazar: stock\ninsuficiente (RF-14)", c1, 930, 150, 56, ROJO)
fin("fin_stock", c1, 1010)
act("salida", "stock_nuevo :=\nstock − cantidad", c2, 1040, 130, 54)
act("entrada", "stock_nuevo :=\nstock + cantidad", c3, 1040, 130, 54)
rombo("d_umbral", c4, 930)
act("ajuste", "stock_nuevo :=\ncantidad_objetivo", c4, 1040, 130, 54)
act("pendiente", "Marcar\nrequiere_aprobacion;\nel stock no cambia (RF-17)", c5, 1040, 150, 64, AMARILLO)
nodos["senal"] = d.enviar_senal("Ajuste pendiente\nde aprobación", c5 - 75, 1120, 150, 50)
rombo("m2", c3, 1140)
act("actualizar", "Actualizar stock_actual y guardar\nstock_anterior y stock_nuevo\n(RF-12, RF-13, RF-18)", c3,
    1230, 230, 64)
rombo("d_minimo", c3, 1330)
rombo("d_ya_hay", c3, 1430)
act("crear", "Crear solicitud de\nreabastecimiento\nPENDIENTE (RF-28)", c3, 1530, 180, 64, VERDE)
rombo("m3", c3, 1620)
rombo("m4", c3, 1700)

# --- flujos de la actividad 1
f("ini", "elegir")
f("elegir", "d_tipo")
f("d_tipo", "cantidad", "exitX=0;exitY=0.5;entryX=0.5;entryY=0;", "[ENTRADA o SALIDA]")
f("d_tipo", "objetivo", "exitX=1;exitY=0.5;entryX=0.5;entryY=0;", "[AJUSTE]")
f("cantidad", "m1", "exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
f("objetivo", "m1", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", puntos=[(300, 510), (J, 510)])
f("m1", "validar", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
f("validar", "d_valido")
f("d_valido", "corregir", "exitX=0;exitY=0.5;entryX=1;entryY=0.5;", "[datos inválidos]")
f("corregir", "m1", "exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
f("d_valido", "insert", "", "[datos válidos]")
f("insert", "d_dup", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(nodos["d_dup"], nodos["rech_dup"], FLUJO + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;",
         etiquetas=[(0, "[pérdida por vencimiento\nya registrada hoy]", "center", "bottom")])
f("rech_dup", "fin_dup")
f("d_dup", "bloquear", "", "[else]")
f("bloquear", "d_tipo_bd")
f("d_tipo_bd", "d_alcanza", "exitX=0;exitY=0.5;entryX=1;entryY=0.5;", "[SALIDA]")
f("d_alcanza", "rech_stock", "exitX=0;exitY=0.5;entryX=1;entryY=0.5;", "[stock <\ncantidad]")
f("rech_stock", "fin_stock")
f("d_alcanza", "salida", "", "[else]")
f("d_tipo_bd", "entrada", "", "[ENTRADA]")
f("d_tipo_bd", "d_umbral", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "[AJUSTE]")
f("d_umbral", "ajuste", "", "[diferencia ≤ umbral]")
f("d_umbral", "pendiente", "exitX=1;exitY=0.5;entryX=0.5;entryY=0;", "[diferencia > umbral]", puntos=[(c5, 930)])
f("pendiente", "senal")
f("salida", "m2", "exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
f("entrada", "m2")
f("ajuste", "m2", "exitX=0.5;exitY=1;entryX=1;entryY=0.5;")
f("m2", "actualizar")
f("actualizar", "d_minimo")
f("d_minimo", "d_ya_hay", "", "[stock_nuevo < stock_minimo]")
f("d_minimo", "m3", "exitX=0;exitY=0.5;entryX=0;entryY=0.5;", "[else]", puntos=[(c2, 1330), (c2, 1620)])
f("d_ya_hay", "crear", "", "[no hay solicitud PENDIENTE]")
f("d_ya_hay", "m3", "exitX=1;exitY=0.5;entryX=1;entryY=0.5;", "[ya hay una PENDIENTE:\nno se crea otra (RF-29)]",
  puntos=[(c4, 1430), (c4, 1620)])
f("crear", "m3")
f("m3", "m4")
f("senal", "m4", "exitX=0.5;exitY=1;entryX=1;entryY=0.5;", puntos=[(c5, 1700)])
f("m4", "commit", "exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
f("commit", "fin")

d.nota("En rojo, la base rechaza el movimiento: la vista de Django muestra el mensaje y no se registra nada "
       "(ROLLBACK). Hoy la vista solo registra ENTRADA y SALIDA y suma o resta el stock en Python; se adapta en la "
       "spec 003.", 60, 1700, 300, 110, tam=11)

# ============================================================ actividad 2
X2, TOP2, BAJO2 = 1570, 100, 1000
d.marco_diagrama("act Aprobar un ajuste pendiente", X2, TOP2, 860, BAJO2 - TOP2 + 20)
LT2 = TOP2 + 40
for nombre, x, w in [("Administrador", X2 + 20, 260), ("Django (vista)", X2 + 280, 240),
                     ("Base de datos (PostgreSQL en Neon)", X2 + 520, 320)]:
    d.calle(nombre, x, LT2, w, BAJO2 - LT2)
A, D, B = X2 + 150, X2 + 400, X2 + 680

nodos["ini2"] = d.inicio(A - 13, 200)
nodos["acepta"] = d.aceptar_evento("Ajuste pendiente\nde aprobación", A - 90, 255, 180, 50)
act("revisar", "Revisar el ajuste\npendiente", A, 370, 170, 54)
rombo("d_aprueba", A, 460)
fin("fin_pend", A, 560)
d.texto("Queda pendiente: el\nesquema no tiene rechazo", A - 95, 582, 190, 36, tam=11, alin="center")
act("aprobar", "UPDATE aprobado_por", D, 460, 190, 50)
act("bloquear2", "Bloquear el insumo y tomar\nel stock del momento", B, 460, 230, 56)
act("fijar", "stock_anterior := stock del momento;\nstock_nuevo := cantidad_objetivo;\n"
    "aprobado_en := now()", B, 560, 260, 64)
act("actualizar2", "Actualizar stock_actual (RF-17)", B, 660, 230, 50)
act("solicitud2", "Generar solicitud si hace falta\n(los mismos pasos de la\nactividad anterior)", B, 770, 230,
    64)
d.texto("⋔", B + 96, 784, 16, 18, tam=14, alin="center")      # acción de llamada a comportamiento
act("commit2", "Confirmar (COMMIT)", D, 770, 180, 50)
fin("fin2", D, 860)

f("ini2", "acepta")
f("acepta", "revisar")
f("revisar", "d_aprueba")
f("d_aprueba", "fin_pend", "", "[no lo aprueba]")
f("d_aprueba", "aprobar", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "[lo aprueba]")
f("aprobar", "bloquear2", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
f("bloquear2", "fijar")
f("fijar", "actualizar2")
f("actualizar2", "solicitud2")
f("solicitud2", "commit2", "exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
f("commit2", "fin2")

# ============================================================ notas
d.nota("La señal «Ajuste pendiente de aprobación» une las dos actividades: la primera la envía (pentágono "
       "convexo) y termina; la segunda espera ese evento (pentágono cóncavo). Son dos transacciones distintas.",
       X2, 1080, 860, 70, tam=12)
d.nota("Notación: rombo = decisión o fusión, con la condición como guarda [..] en cada salida; [else] = cualquier "
       "otro caso; ● = inicio; ◉ = fin de la actividad; ⋔ = la acción llama a otra actividad. Umbral = "
       "app.umbral_ajuste_aprobacion (20 si no se configura).", X2, 1170, 860, 70, tam=12)

d.guardar(*salida("05-actividades-registrar-movimiento"))
print("ok")
