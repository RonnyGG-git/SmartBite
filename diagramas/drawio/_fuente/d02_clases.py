"""02 — Clases de Inventario según inventario/models.py de la app Django de
Ronny (rama smartbite), más las clases de otras apps con las que se relaciona.
UML 2.5.1: 9.2.4, 9.5.4, 9.6.4, 11.4.4, 11.5.4.

- Atributos = campos del modelo con su tipo de Django; '/' = @property.
- Generalización hacia core::TimestampedModel (abstracta): todos menos
  DetalleCompra, que hereda directo de models.Model.
- on_delete=CASCADE → composición (la parte se borra con el todo);
  on_delete=PROTECT → asociación (no se puede borrar mientras haya referencias).
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Clases - Inventario", 1660, 1060)
d.titulo("Diagrama de clases — Inventario (Smart Bite)",
         "Los modelos de Django de la app inventario (rama smartbite) y las clases de otras apps con las que se "
         "relacionan")

STR = "+ __str__(): str"
TS = d.clase("core::TimestampedModel", 650, 100, 360, [
    "+ creado_en: DateTimeField {auto_now_add}",
    "+ actualizado_en: DateTimeField {auto_now}",
], restriccion="abstract", color=GRIS)

Y1 = 300
prov = d.clase("Proveedor", 40, Y1, 270, [
    "+ id: BigAutoField {id}",
    "+ nombre: CharField(150)",
    "+ contacto: CharField(150)",
    "+ telefono: CharField(30)",
    "+ email: EmailField",
    "+ direccion: CharField(255)",
    "+ activo: BooleanField = True",
], [STR])
alto_prov = d.ultima_altura
compra = d.clase("Compra", 430, Y1, 290, [
    "+ id: BigAutoField {id}",
    "+ estado: CharField(15) = PENDIENTE",
    "      {PENDIENTE, RECIBIDA o ANULADA}",
    "+ /total: Decimal {Σ subtotal de los detalles}",
], [STR])
alto_compra = d.ultima_altura
item = d.clase("ItemInventario", 780, Y1, 360, [
    "+ id: BigAutoField {id}",
    "+ nombre: CharField(150)",
    "+ descripcion: CharField(255)",
    "+ unidad_medida: CharField(20) = unidad",
    "      {kg, g, L, ml, unidad, caja o paquete}",
    "+ stock_actual: PositiveIntegerField = 0",
    "+ stock_minimo: PositiveIntegerField = 0",
    "+ costo_unitario: DecimalField(10,2) = 0",
    "+ ubicacion: CharField(150)",
    "+ /stock_bajo: bool {stock_actual ≤ stock_minimo}",
], [STR])
alto_item = d.ultima_altura
mov = d.clase("MovimientoInventario", 1290, Y1, 320, [
    "+ id: BigAutoField {id}",
    "+ tipo: CharField(10) {ENTRADA o SALIDA}",
    "+ cantidad: PositiveIntegerField",
    "+ motivo: CharField(255)",
], [STR])
alto_mov = d.ultima_altura

Y2 = Y1 + alto_item + 110
detalle = d.clase("DetalleCompra", 430, Y2, 290, [
    "+ id: BigAutoField {id}",
    "+ cantidad: PositiveIntegerField",
    "+ costo_unitario: DecimalField(10,2)",
    "+ /subtotal: Decimal {cantidad × costo_unitario}",
], [STR])
alto_det = d.ultima_altura
ingr = d.clase_simple("recetas::ProductoIngrediente", 780, Y2, 220, 50)
suc = d.clase_simple("restaurantes::Sucursal", 1040, Y2, 200, 50)

# Generalización: un solo árbol hacia la clase abstracta (UML 9.7.4)
for c in (prov, compra, item, mov):
    d.arista(c, TS, GENERALIZACION + "edgeStyle=orthogonalEdgeStyle;exitX=0.5;exitY=0;entryX=0.5;entryY=1;")


def fy(y_abs, y0, h):
    return round((y_abs - y0) / h, 4)


# Compra * — 1 Proveedor (PROTECT)
Y_CP = Y1 + 60
d.arista(compra, prov, ASOCIACION + f"exitX=0;exitY={fy(Y_CP, Y1, alto_compra)};entryX=1;"
         f"entryY={fy(Y_CP, Y1, alto_prov)};",
         etiquetas=[(-1, "0..*", "right", "top"), (1, "proveedor 1", "left", "bottom")])
# ItemInventario ◆— MovimientoInventario (CASCADE): composición, rombo en el todo
Y_IM = Y1 + 70
d.arista(item, mov, COMPOSICION + f"exitX=1;exitY={fy(Y_IM, Y1, alto_item)};entryX=0;"
         f"entryY={fy(Y_IM, Y1, alto_mov)};",
         etiquetas=[(-1, "item 1", "left", "bottom"), (1, "movimientos 0..*", "right", "top")])
# Compra ◆— DetalleCompra (CASCADE)
d.arista(compra, detalle, COMPOSICION + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;",
         etiquetas=[(-1, "compra 1", "left", "top"), (1, "detalles 0..*", "left")])
# DetalleCompra * — 1 ItemInventario (PROTECT), por el pasillo entre Compra e Item
Y_DI = Y1 + alto_item - 30
d.arista(detalle, item, ASOC_ORTO + f"exitX=1;exitY=0.3;entryX=0;entryY={fy(Y_DI, Y1, alto_item)};",
         puntos=[(750, Y2 + round(0.3 * alto_det)), (750, Y_DI)],
         etiquetas=[(-1, "0..*", "left"), (1, "item 1", "right")])
# recetas::ProductoIngrediente * — 1 ItemInventario (PROTECT)
d.arista(ingr, item, ASOCIACION + f"exitX=0.5;exitY=0;entryX={fy(890, 780, 360)};entryY=1;",
         etiquetas=[(-1, "usado_en_recetas 0..*", "left"), (1, "item_inventario 1", "left", "top")])
# ItemInventario * — 1 restaurantes::Sucursal (PROTECT)
d.arista(item, suc, ASOCIACION + f"exitX={fy(1110, 780, 360)};exitY=1;entryX=0.35;entryY=0;",
         etiquetas=[(-1, "items_inventario 0..*", "left", "top"), (1, "sucursal 1", "left")])

y_n = Y2 + max(alto_det, 60) + 50
d.nota("Clases = modelos de Django (inventario/models.py); atributos = campos con su tipo de Django. Todo es + "
       "(público): en Python los campos de un modelo se leen y escriben desde afuera. / = propiedad calculada "
       "(@property), no se guarda en la base. Los CharField con blank=True (contacto, teléfono, ubicación…) "
       "pueden quedar vacíos (''), no nulos.\n"
       "Rombo lleno = composición: on_delete=CASCADE (si se borra el ítem o la compra, se borran sus movimientos "
       "o detalles). Línea simple = on_delete=PROTECT (no se puede borrar mientras haya referencias). Triángulo "
       "hueco = herencia. Los nombres en los extremos son los related_name.\n"
       "Clases grises = de otras apps (app::Clase). Proveedor, Compra y DetalleCompra son de Compras pero hoy "
       "viven en esta misma app. MovimientoInventario no guarda qué usuario lo registró.",
       40, y_n, 1570, 110, tam=11)

d.alto = y_n + 140
d.guardar(*salida("02-clases-inventario"))
print("ok", Y2, d.alto)
