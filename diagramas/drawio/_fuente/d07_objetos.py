"""07 — Objetos: los datos de Inventario después de los escenarios de los
diagramas de comunicación (recibir la compra de 10 L de leche) y de secuencia
(salida de 7), con los modelos de la app Django de Ronny (rama smartbite):
inventario/models.py. UML 2.5.1, 9.8.4.

- Cada slot es un atributo del diagrama de clases (creado_en viene de
  core::TimestampedModel; '/' = propiedad calculada).
- Las FK (proveedor, compra, item, sucursal) son asociaciones en el diagrama
  de clases: acá van como enlaces (línea sólida), no como slots *_id.
- Los valores encadenan: stock 0 + ENTRADA 10 − SALIDA 7 = 3; total = subtotal.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Objetos - Inventario", 1730, 900)
d.titulo("Diagrama de objetos — Inventario (Smart Bite)",
         "Los datos después de recibir la compra de leche (diagrama de comunicación) y de la salida de 7 "
         "(diagrama de secuencia)")

O = dict(objeto=True, tam=12)

prov = d.clase("lacteos : Proveedor", 40, 120, 260, [
    'id = 2', 'nombre = "Lácteos del Valle"', 'activo = true'], **O)
alto_prov = d.ultima_altura
compra = d.clase("c3 : Compra", 470, 120, 290, [
    'id = 3', 'estado = "RECIBIDA"', '/total = 45.00', 'creado_en = 2026-10-01 08:30'], color=VERDE, **O)
alto_compra = d.ultima_altura
det = d.clase("d1 : DetalleCompra", 470, 420, 290, [
    'id = 5', 'cantidad = 10', 'costo_unitario = 4.50', '/subtotal = 45.00'], **O)
alto_det = d.ultima_altura

LX, LY, LW = 930, 380, 340
leche = d.clase("leche : ItemInventario", LX, LY, LW, [
    'id = 1', 'nombre = "Leche entera"', 'descripcion = ""', 'unidad_medida = "L"', 'stock_actual = 3',
    'stock_minimo = 5', 'costo_unitario = 4.50', 'ubicacion = "Cámara fría"', '/stock_bajo = true'], **O)
alto_leche = d.ultima_altura
suc = d.clase_simple("centro : restaurantes::Sucursal", LX + 20, 150, 300, 50, objeto=True)

MX, MW = 1380, 310
Y_E1, Y_S1 = 300, 520
ent = d.clase("e1 : MovimientoInventario", MX, Y_E1, MW, [
    'id = 1', 'tipo = "ENTRADA"', 'cantidad = 10', 'motivo = "Recepción compra #3"',
    'creado_en = 2026-10-01 09:15'], color=VERDE, **O)
alto_ent = d.ultima_altura
sal = d.clase("s1 : MovimientoInventario", MX, Y_S1, MW, [
    'id = 2', 'tipo = "SALIDA"', 'cantidad = 7', 'motivo = "Consumo de cocina"',
    'creado_en = 2026-10-02 13:40'], color=AMARILLO, **O)
alto_sal = d.ultima_altura


def fy(y_abs, y0, h):
    return round((y_abs - y0) / h, 4)


# Enlaces (instancias de las asociaciones del diagrama de clases); el nombre de
# cada extremo es el rol del objeto que está en ese extremo.
Y_CP = 120 + 60
d.arista(compra, prov, LINK + f"exitX=0;exitY={fy(Y_CP, 120, alto_compra)};entryX=1;"
         f"entryY={fy(Y_CP, 120, alto_prov)};",
         etiquetas=[(1, "proveedor", "left", "bottom"), (-1, "compras", "right", "top")])
d.arista(compra, det, LINK + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;",
         etiquetas=[(-1, "compra", "left", "top"), (1, "detalles", "left", "bottom")])
Y_DL = 420 + 50
d.arista(det, leche, LINK + f"exitX=1;exitY={fy(Y_DL, 420, alto_det)};entryX=0;"
         f"entryY={fy(Y_DL, LY, alto_leche)};",
         etiquetas=[(-1, "detalles_compra", "left", "bottom"), (1, "item", "right", "top")])
d.arista(leche, suc, LINK + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;",
         etiquetas=[(-1, "items_inventario", "left", "bottom"), (1, "sucursal", "left", "top")])
Y_E = LY + 14                     # enlaces horizontales: arriba y abajo de leche
d.arista(ent, leche, LINK + f"exitX=0;exitY={fy(Y_E, Y_E1, alto_ent)};entryX=1;entryY={fy(Y_E, LY, alto_leche)};",
         etiquetas=[(-1, "movimientos", "right", "bottom"), (1, "item", "left", "top")])
Y_S = LY + alto_leche - 14
d.arista(sal, leche, LINK + f"exitX=0;exitY={fy(Y_S, Y_S1, alto_sal)};entryX=1;entryY={fy(Y_S, LY, alto_leche)};",
         etiquetas=[(-1, "movimientos", "right", "bottom"), (1, "item", "left", "top")])

YN = max(LY + alto_leche, Y_S1 + alto_sal) + 50
d.nota("Cómo se llegó acá: «Leche entera» se creó con stock 0 (item_crear). Al recibir la compra #3 (compra_recibir) "
       "el stock pasó a 10 y se creó la ENTRADA e1. La salida de 7 (item_ajustar_stock) lo dejó en 3 y creó la "
       "SALIDA s1. Como 3 ≤ 5, stock_bajo = true y el listado la marca «Stock bajo». Ningún campo guarda el stock "
       "anterior: se reconstruye con los movimientos (0 + 10 − 7 = 3).", 40, YN, 1650, 56, tam=12)
d.nota("Línea sólida = enlace (instancia de una asociación del diagrama de clases); los nombres en los extremos son "
       "los related_name y las FK. En verde, lo que dejó la recepción de la compra (diagrama de comunicación); en "
       "amarillo, el movimiento del diagrama de secuencia. centro es de otra app: se muestra sin sus atributos.",
       40, YN + 66, 1650, 56, tam=12)

d.alto = YN + 150
d.guardar(*salida("07-objetos-inventario"))
print("ok")
