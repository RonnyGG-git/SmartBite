"""03 — Secuencia: registrar una salida de inventario (CU-INV-06) tal como lo
hace la app Django de Ronny: inventario/views.py::item_ajustar_stock,
inventario/forms.py::AjusteStockForm y core/mixins.py::usuario_tiene_rol.
UML 2.5.1 cláusula 17.

- 'break' para los dos casos que cortan el flujo (sin rol, formulario
  inválido): se ejecutan en lugar del resto (17.6.3).
- 'critical' = transaction.atomic(): el UPDATE y el INSERT van juntos.
- Mensajes de creación (punteados, a la cabecera) para el formulario y el
  movimiento; las respuestas vuelven a quien llamó.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Secuencia - Registrar salida", 1540, 1150)
d.titulo("Diagrama de secuencia — Registrar salida de inventario (CU-INV-06)",
         "Cómo lo hace la vista item_ajustar_stock de la app Django (rama smartbite)")

MARCO_X, MARCO_Y, MARCO_W = 30, 96, 1480
TOP, FIN = 140, 985
d.marco_diagrama("sd Registrar salida de inventario", MARCO_X, MARCO_Y, MARCO_W, FIN - MARCO_Y + 20)

JEFE, VISTA, FORM, ITEM, MOV, BD = range(6)
X = {JEFE: 100, VISTA: 330, FORM: 680, ITEM: 920, MOV: 1150, BD: 1380}
W = {VISTA: 210, FORM: 190, ITEM: 190, MOV: 210, BD: 190}
Y_FORM, Y_MOV = 418, 802          # alturas de los mensajes de creación

d.actor_de_secuencia("Jefe de Inventario", X[JEFE], TOP, FIN)
d.linea_de_vida(":item_ajustar_stock", X[VISTA] - W[VISTA] / 2, TOP, W[VISTA], FIN - TOP, palabra_clave="vista")
d.linea_de_vida(":AjusteStockForm", X[FORM] - W[FORM] / 2, Y_FORM - 26, W[FORM], FIN - Y_FORM + 26)
d.linea_de_vida("item: ItemInventario", X[ITEM] - W[ITEM] / 2, TOP, W[ITEM], FIN - TOP)
d.linea_de_vida(":MovimientoInventario", X[MOV] - W[MOV] / 2, Y_MOV - 26, W[MOV], FIN - Y_MOV + 26)
d.linea_de_vida("bd: PostgreSQL", X[BD] - W[BD] / 2, TOP, W[BD], FIN - TOP, color=GRIS)

# Activaciones
d.activacion(X[VISTA], 237, 950)
d.activacion(X[VISTA], 264, 288, desplazamiento=8)
d.activacion(X[VISTA], 304, 328, desplazamiento=8)
d.activacion(X[FORM], 470, 505)
d.activacion(X[ITEM], 630, 760)
d.activacion(X[BD], 698, 728)
d.activacion(X[MOV], Y_MOV + 26, 900)
d.activacion(X[BD], 845, 872)


def msg(origen, destino, y, texto, estilo=MENSAJE):
    x1, x2 = X[origen], X[destino]
    ajuste = 6 if x2 > x1 else -6
    d.flecha(x1 + ajuste, y, x2 - ajuste, y, estilo, texto)


def propio(y, texto):
    xv = X[VISTA] + 6
    d.flecha(xv, y, xv + 8, y + 18, MENSAJE + "align=left;spacingLeft=4;", texto,
             puntos=[(xv + 50, y), (xv + 50, y + 18)])


msg(JEFE, VISTA, 242, "1: POST ajustar/ (tipo = SALIDA, cantidad, motivo)")
propio(260, "2: item = get_object_or_404(ItemInventario, pk)")
propio(300, "3: usuario_tiene_rol(usuario, ROLES_INVENTARIO)")

d.fragmento("break", MARCO_X + 20, 340, MARCO_W - 40, 50,
            "[el usuario no es ADMINISTRADOR ni JEFE_INVENTARIO]", ancho_etiqueta=64)
msg(VISTA, JEFE, 376, "redirige al listado", RESPUESTA)

# Creación del formulario: punteada hacia la cabecera
d.flecha(X[VISTA] + 6, Y_FORM, X[FORM] - W[FORM] / 2, Y_FORM, RESPUESTA, "4: AjusteStockForm(request.POST)")
msg(VISTA, FORM, 475, "5: is_valid()")
msg(FORM, VISTA, 502, "True", RESPUESTA)

d.fragmento("break", MARCO_X + 20, 520, MARCO_W - 40, 50, "[el formulario no es válido]", ancho_etiqueta=64)
msg(VISTA, JEFE, 556, "muestra el formulario con los errores", RESPUESTA)

d.fragmento("critical", MARCO_X + 20, 590, MARCO_W - 40, 330, "transaction.atomic()", ancho_etiqueta=74)
msg(VISTA, ITEM, 640, "6: stock_actual = max(0, stock_actual − cantidad)")
msg(VISTA, ITEM, 680, "7: save(update_fields=['stock_actual'])")
msg(ITEM, BD, 703, "8: UPDATE stock_actual")
msg(BD, ITEM, 726, "ok", RESPUESTA)
msg(ITEM, VISTA, 752, "guardado", RESPUESTA)
d.flecha(X[VISTA] + 6, Y_MOV, X[MOV] - W[MOV] / 2, Y_MOV, RESPUESTA,
         "9: MovimientoInventario.objects.create(item, tipo = SALIDA, cantidad, motivo)")
msg(MOV, BD, 850, "10: INSERT movimiento")
msg(BD, MOV, 870, "ok", RESPUESTA)
msg(MOV, VISTA, 896, "movimiento", RESPUESTA)
msg(VISTA, JEFE, 945, "11: redirige al listado de inventario", RESPUESTA)

YN = FIN + 45
d.nota("Ejemplo (el mismo del diagrama de objetos): Leche entera con stock 10 y mínimo 5. Salida de 7 → "
       "stock 3; como 3 ≤ 5, el listado la marca «Stock bajo». No se genera ninguna solicitud de reabastecimiento.",
       30, YN, 450, 70, tam=11)
d.nota("Si la salida supera el stock, no se rechaza: max(0, …) deja stock_actual en 0 y el movimiento igual "
       "guarda la cantidad pedida. El movimiento no guarda qué usuario lo registró.", 495, YN, 440, 70, tam=11)
d.nota("critical = transaction.atomic(): el UPDATE y el INSERT se confirman juntos o no se guarda ninguno. "
       "bd = PostgreSQL en Neon (base smartbite_app) cuando el .env define DATABASE_URL; si no, SQLite.",
       950, YN, 560, 70, tam=11)

d.alto = YN + 100
d.guardar(*salida("03-secuencia-registrar-salida"))
print("ok")
