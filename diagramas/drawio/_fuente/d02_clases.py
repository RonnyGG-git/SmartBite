"""02 — Clases de Inventario: las 5 tablas reales de
sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql, sus triggers y funciones, las vistas
y las clases de otros módulos. Es un modelo de datos físico dibujado con
diagrama de clases (perfil de datos de Ambler: tablas = clases, columnas =
atributos, triggers = operaciones «trigger», vistas = «view»).

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1):
- Visibilidad en todos los miembros (9.5.4, 9.6.4): columnas +, triggers -
  (la base los dispara; no se pueden llamar), funciones que llama otro módulo
  +, función auxiliar del paquete ~. # no aplica: no hay herencia.
- Funciones que no dependen de una fila = estáticas, subrayadas (9.4.4).
- Parámetros con 'nombre: Tipo' y tipo de retorno (9.4.4, 9.6.4).
- Columnas que admiten NULL con multiplicidad [0..1]: sin multiplicidad, UML
  entiende exactamente 1 (9.5.4).
- id con el modificador {id}; codigo_unico {readOnly} (9.5.4).
- Clases de otros módulos con nombre calificado Modulo::Clase (7.4.3), no
  con «Compras» o «externo» como si fueran estereotipos.
- Referencias sin FK física: asociación con la restricción {sin FK física
  todavía}, no dependencia.
- Vistas: «view» con dependencia «derive» hacia las tablas (perfil
  estándar, cláusula 22), sin la caja punteada que no es UML.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Clases - Inventario", 1960, 1500)
d.titulo("Diagrama de clases — Inventario (Smart Bite)",
         "Modelo de datos en PostgreSQL (Neon): 5 tablas con sus triggers y funciones, 3 vistas y las clases de "
         "otros módulos a las que apuntan")


def fx(x_abs, x0, w):
    return round((x_abs - x0) / w, 4)


def fy(y_abs, y0, h):
    return round((y_abs - y0) / h, 4)


TRG = "- «trigger» "

# --- fila 1
CAT_X, CAT_Y, CAT_W = 110, 100, 330
categoria = d.clase("CategoriaInsumo", CAT_X, CAT_Y, CAT_W, [
    "+ id: BIGINT {id}",
    "+ nombre: VARCHAR(100) {único}",
    "+ creado_en: TIMESTAMPTZ",
    "+ actualizado_en: TIMESTAMPTZ",
], [TRG + "fn_marcar_actualizado_en(): trigger"])
alto_cat = d.ultima_altura

COL_DER, W_DER = 1660, 240
SUC_Y = 200
sucursal = d.clase_simple("Restaurantes::Sucursal", COL_DER, SUC_Y, W_DER, 54)

# --- fila 2
Y2 = 320
ITEM_X, ITEM_W = 110, 600
item = d.clase("ItemInventario", ITEM_X, Y2, ITEM_W, [
    "+ id: BIGINT {id}",
    "+ codigo_unico: VARCHAR(30) {readOnly, único por sucursal}",
    "+ nombre: VARCHAR(150) {único por sucursal}",
    "+ descripcion: VARCHAR(255) [0..1]",
    "+ unidad_medida: VARCHAR(20)",
    "+ stock_actual: NUMERIC(12,3) = 0 {≥ 0, solo cambia con movimientos}",
    "+ stock_minimo: NUMERIC(12,3) [0..1] {≥ 0}",
    "+ costo_unitario: NUMERIC(10,2) = 0 {≥ 0}",
    "+ fecha_vencimiento: DATE [0..1]",
    "+ dias_alerta_vencimiento: INTEGER [0..1] {≥ 0}",
    "+ activo: BOOLEAN = true",
    "+ creado_en: TIMESTAMPTZ",
    "+ actualizado_en: TIMESTAMPTZ",
], [
    TRG + "fn_item_inventario_generar_codigo(): trigger",
    TRG + "fn_item_inventario_codigo_inmutable(): trigger",
    TRG + "fn_item_inventario_proteger_stock(): trigger",
    TRG + "fn_item_inventario_validar_desactivacion(): trigger",
    TRG + "fn_item_inventario_registrar_historial(): trigger",
    TRG + "fn_marcar_actualizado_en(): trigger",
    "!+ fn_verificar_disponibilidad(items: JSONB): TABLE(item_inventario_id,",
    "!      cantidad_requerida, disponible) {query}",
])
alto_item = d.ultima_altura

MOV_X, MOV_W = 830, 640
movimiento = d.clase("MovimientoInventario", MOV_X, Y2, MOV_W, [
    "+ id: BIGINT {id}",
    "+ tipo: VARCHAR(10) {ENTRADA, SALIDA o AJUSTE}",
    "+ cantidad_movimiento: NUMERIC(12,3) [0..1] {> 0; solo ENTRADA y SALIDA}",
    "+ cantidad_objetivo: NUMERIC(12,3) [0..1] {≥ 0; solo AJUSTE}",
    "+ stock_anterior: NUMERIC(12,3)",
    "+ stock_nuevo: NUMERIC(12,3) [0..1]",
    "+ motivo: VARCHAR(255) [0..1] {obligatorio en AJUSTE}",
    "+ causa_perdida: VARCHAR(20) [0..1] {DANIO, VENCIMIENTO o EXTRAVIO; solo SALIDA}",
    "+ origen_perdida: VARCHAR(10) [0..1] {MANUAL o AUTOMATICA}",
    "+ requiere_aprobacion: BOOLEAN = false",
    "+ aprobado_en: TIMESTAMPTZ [0..1]",
    "+ creado_en: TIMESTAMPTZ",
], [
    TRG + "fn_movimiento_inventario_evitar_perdida_duplicada(): trigger",
    TRG + "fn_movimiento_inventario_aplicar(): trigger",
    TRG + "fn_movimiento_inventario_aprobar(): trigger",
    TRG + "fn_rechazar_cambio_auditoria(): trigger",
    "!+ fn_generar_perdidas_vencimiento(): INTEGER",
], restriccion="kardex: solo se agregan filas; un AJUSTE pendiente se aprueba una vez")
alto_mov = d.ultima_altura

ORD_Y = Y2 + 40
orden = d.clase_simple("Compras::OrdenCompra", COL_DER, ORD_Y, W_DER, 54)

# --- fila 3
Y3 = Y2 + max(alto_item, alto_mov) + 110
SOL_X, SOL_W = 110, 450
solicitud = d.clase("SolicitudReabastecimiento", SOL_X, Y3, SOL_W, [
    "+ id: BIGINT {id}",
    "+ cantidad_sugerida: NUMERIC(12,3) {> 0}",
    "+ estado: VARCHAR(10) = 'PENDIENTE'",
    "      {PENDIENTE, ENVIADA, ATENDIDA o CANCELADA;",
    "       una sola PENDIENTE por insumo}",
    "+ creado_en: TIMESTAMPTZ",
    "+ actualizado_en: TIMESTAMPTZ",
], [
    TRG + "fn_marcar_actualizado_en(): trigger",
    "!~ fn_generar_solicitud_si_hace_falta(p_item_inventario_id: BIGINT,",
    "!      p_stock_nuevo: NUMERIC)",
])
alto_sol = d.ultima_altura

HIS_X, HIS_W = 690, 430
historial = d.clase("ItemInventarioHistorial", HIS_X, Y3, HIS_W, [
    "+ id: BIGINT {id}",
    "+ campo: VARCHAR(50)",
    "+ valor_anterior: TEXT [0..1]",
    "+ valor_nuevo: TEXT [0..1]",
    "+ creado_en: TIMESTAMPTZ",
], [TRG + "fn_rechazar_cambio_auditoria(): trigger"], restriccion="solo se agregan filas")
alto_his = d.ultima_altura

# Usuario: alto, para que las tres asociaciones lleguen rectas
Y_U1, Y_U2 = Y2 + alto_mov - 150, Y2 + alto_mov - 60      # salidas desde MovimientoInventario
Y_U3 = Y3 + 70                                               # salida desde el historial
USU_Y = Y_U1 - 40
usuario = d.clase_simple("Cuentas::Usuario", COL_DER, USU_Y, W_DER, Y_U3 - USU_Y + 40)
alto_usu = Y_U3 - USU_Y + 40

# --- asociaciones (línea sólida; multiplicidad en cada extremo; nombre de rol donde hay dos hacia la misma clase)
X_CAT = CAT_X + CAT_W // 2
d.arista(item, categoria, ASOC_ORTO + f"exitX={fx(X_CAT, ITEM_X, ITEM_W)};exitY=0;entryX=0.5;entryY=1;",
         etiquetas=[(-1, "0..*", "left"), (1, "1", "left", "top")])
Y_MOV = Y2 + 160
d.arista(movimiento, item, ASOC_ORTO + f"exitX=0;exitY={fy(Y_MOV, Y2, alto_mov)};entryX=1;"
         f"entryY={fy(Y_MOV, Y2, alto_item)};", etiquetas=[(-1, "0..*", "right"), (1, "1", "left")])
X_SOL = SOL_X + 200
d.arista(solicitud, item, ASOC_ORTO + f"exitX={fx(X_SOL, SOL_X, SOL_W)};exitY=0;entryX={fx(X_SOL, ITEM_X, ITEM_W)};"
         "entryY=1;", etiquetas=[(-1, "0..*", "left"), (1, "1", "left", "top")])
X_HIS = 700
d.arista(historial, item, ASOC_ORTO + f"exitX={fx(X_HIS, HIS_X, HIS_W)};exitY=0;entryX={fx(X_HIS, ITEM_X, ITEM_W)};"
         "entryY=1;", etiquetas=[(-1, "0..*", "left"), (1, "1", "left", "top")])

Y_ORD = ORD_Y + 27
d.arista(movimiento, orden, ASOC_ORTO + f"exitX=1;exitY={fy(Y_ORD, Y2, alto_mov)};entryX=0;entryY=0.5;",
         etiquetas=[(-1, "0..*", "left"), (1, "compra 0..1", "right")])

# Referencias a tablas de otros módulos que todavía no tienen FK física
Y_SUC = SUC_Y + 27
X_SUC = ITEM_X + ITEM_W - 40
d.arista(item, sucursal, ASOC_ORTO + f"exitX={fx(X_SUC, ITEM_X, ITEM_W)};exitY=0;entryX=0;entryY=0.5;",
         puntos=[(X_SUC, Y_SUC)], etiquetas=[(-1, "0..*", "left", "bottom"), (1, "1", "right")])
d.texto("{sin FK física todavía}", 1250, Y_SUC - 22, 180, 18, tam=11, alin="center", color="#555555")

d.arista(movimiento, usuario, ASOC_ORTO + f"exitX=1;exitY={fy(Y_U1, Y2, alto_mov)};entryX=0;"
         f"entryY={fy(Y_U1, USU_Y, alto_usu)};", etiquetas=[(-1, "0..*", "left"), (1, "usuario 1", "right")])
d.arista(movimiento, usuario, ASOC_ORTO + f"exitX=1;exitY={fy(Y_U2, Y2, alto_mov)};entryX=0;"
         f"entryY={fy(Y_U2, USU_Y, alto_usu)};", etiquetas=[(-1, "0..*", "left"), (1, "aprobado_por 0..1", "right")])
d.texto("{sin FK física todavía}", MOV_X + MOV_W + 20, Y_U2 + 6, 150, 18, tam=11, alin="center", color="#555555")
d.arista(historial, usuario, ASOC_ORTO + f"exitX=1;exitY={fy(Y_U3, Y3, alto_his)};entryX=0;"
         f"entryY={fy(Y_U3, USU_Y, alto_usu)};", etiquetas=[(-1, "0..*", "left"), (1, "usuario 1", "right")])
d.texto("{sin FK física todavía}", 1330, Y_U3 + 4, 180, 18, tam=11, alin="center", color="#555555")

# --- vistas (fila 4): «derive» hacia las tablas de las que se calculan
Y4 = max(Y3 + max(alto_sol, alto_his), USU_Y + alto_usu) + 110
rep = d.clase("vista_reporte_inventario", 110, Y4, 420, [
    "+ id: BIGINT", "+ codigo_unico: VARCHAR(30)", "+ nombre: VARCHAR(150)", "+ categoria: VARCHAR(100)",
    "+ activo: BOOLEAN", "+ stock_actual: NUMERIC(12,3)", "+ stock_minimo: NUMERIC(12,3) [0..1]",
    "+ fecha_vencimiento: DATE [0..1]", "+ sucursal_id: BIGINT", "+ creado_en: TIMESTAMPTZ",
    "+ actualizado_en: TIMESTAMPTZ",
], estereotipo="view", color=VIOLETA, restriccion="todos los insumos (RF-30)")
alto_rep = d.ultima_altura
ctl = d.clase("vista_control_existencias", 590, Y4, 400, [
    "+ id: BIGINT", "+ codigo_unico: VARCHAR(30)", "+ nombre: VARCHAR(150)", "+ sucursal_id: BIGINT",
    "+ stock_actual: NUMERIC(12,3)", "+ stock_minimo: NUMERIC(12,3)",
], estereotipo="view", color=VIOLETA, restriccion="activo y stock_actual < stock_minimo (RF-10)")
prx = d.clase("vista_proximos_a_vencer", 1050, Y4, 420, [
    "+ id: BIGINT", "+ codigo_unico: VARCHAR(30)", "+ nombre: VARCHAR(150)", "+ sucursal_id: BIGINT",
    "+ fecha_vencimiento: DATE", "+ dias_alerta_aplicado: INTEGER",
], estereotipo="view", color=VIOLETA, restriccion="activo y vence dentro del rango de alerta (RF-23)")

# Las tres vistas se calculan de ItemInventario: varias colas que se juntan en una sola flecha (UML 7.7.4).
X_BUS, Y_BUS = 625, Y4 - 40
y_item_abajo = Y2 + alto_item
for vista, cx in ((rep, 110 + 210), (ctl, 590 + 200), (prx, 1050 + 210)):
    d.arista(vista, item, DEPENDENCIA + f"exitX=0.5;exitY=0;entryX={fx(X_BUS, ITEM_X, ITEM_W)};entryY=1;"
             "edgeStyle=orthogonalEdgeStyle;rounded=0;", puntos=[(cx, Y_BUS), (X_BUS, Y_BUS)])
d.junta(X_BUS, Y_BUS)
d.texto("«derive»", X_BUS + 6, Y_BUS - 60, 70, 18, tam=12, alin="left", color="#333333")
# vista_reporte_inventario además toma el nombre de la categoría
Y_CAT_IN = CAT_Y + 40
d.arista(rep, categoria, DEPENDENCIA + "exitX=0;exitY=0.25;entryX=0;"
         f"entryY={fy(Y_CAT_IN, CAT_Y, alto_cat)};edgeStyle=orthogonalEdgeStyle;rounded=0;",
         puntos=[(45, Y4 + 70), (45, Y_CAT_IN)])
d.texto("«derive»", 49, (Y_CAT_IN + Y4) // 2, 60, 18, tam=12, alin="left", color="#333333")

# --- leyenda (comentario)
Y5 = Y4 + alto_rep + 40
d.nota("Modelo de datos físico (perfil de datos de Ambler): cada clase sin estereotipo es una tabla; atributos = "
       "columnas con su tipo SQL; operaciones = triggers y funciones.\n"
       "Visibilidad: + columna o función que se puede usar desde fuera (otro módulo, la app); - trigger: lo dispara la "
       "base, no se puede llamar; ~ función de uso interno del paquete Inventario (la llaman los triggers de "
       "MovimientoInventario). # no aparece: no hay herencia entre tablas.\n"
       "Subrayado = estático (no depende de una fila). [0..1] = admite NULL (sin multiplicidad se entiende 1). "
       "{…} = restricción. Las columnas FK no se listan: son las asociaciones.\n"
       "Las clases grises son de otros módulos (Modulo::Clase); {sin FK física todavía} = la columna existe pero la "
       "tabla destino todavía no está en Neon. Fuente: sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql (spec 001).",
       110, Y5, 1790, 96, tam=12)

d.alto = Y5 + 130
d.guardar(*salida("02-clases-inventario"))
print("ok", Y3, Y4, d.alto)
