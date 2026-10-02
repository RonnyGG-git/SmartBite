"""08 — Paquetes: cómo se organiza el código de Inventario en el proyecto
Django y en sql/, y qué paquetes dependen de él. Las dependencias salen de
los imports y las FK por string reales del código (*/models.py, */views.py).

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1, cláusula 12):
- Si el paquete muestra sus miembros adentro, el nombre va en la pestaña;
  si no, en el cuerpo (12.2.4).
- Miembros verificados contra los models.py actuales (antes: 'autopedido' en
  cliente y 'Receta' en recetas, que no son clases del código).
- Palabras clave estándar en las dependencias: «import» (importación de
  paquete, 7.4.4) y «use» (uso, 7.7.4) con un nombre que explica el uso. Se
  quitan «FK», «extends» y «carga en», que no son palabras clave de UML.
- Los scripts SQL son artefactos «script» (perfil estándar, cláusula 22):
  rectángulo con icono de documento, no el símbolo de nota.
- La alineación con la spec 003 no es una dependencia: va en un comentario
  anclado a los dos paquetes.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Paquetes - Inventario", 1760, 1060)
d.titulo("Diagrama de paquetes — Inventario (Smart Bite)",
         "Dónde vive el código de Inventario, de qué depende y quién depende de él (el proyecto Django y el esquema "
         "SQL de Neon)")

# --- Proyecto Django
d.paquete("smartbite", 40, 100, 1080, 860, BLANCO, miembros=" ", tam=14)

for i, (nombre, miembros) in enumerate([("cuentas", "Usuario, Rol,\nPermiso"), ("catalogo", "Categoria,\nProducto"),
                                         ("operativo", "Mesa, Cliente,\nOrden, DetalleOrden"),
                                         ("caja", "MetodoPago,\nPago"), ("cliente", "Retroalimentacion")]):
    d.paquete(nombre, 70 + i * 205, 145, 190, 82, GRIS, miembros=miembros, tam=12)
d.paquete("menu_cliente", 70, 245, 190, 60, GRIS, tam=12)
d.texto("Otras apps del proyecto: no se dibujan sus dependencias porque no tocan Inventario.", 280, 262, 700, 20,
        tam=11, color="#666666")

IX, IY, IW, IH = 390, 340, 400, 360
inv = d.paquete("inventario", IX, IY, IW, IH, AZUL, tam=15, miembros=(
    "ItemInventario, MovimientoInventario,\n"
    "Proveedor, Compra, DetalleCompra (models.py)\n\n"
    "vistas: listado, crear y editar insumo,\n"
    "item_ajustar_stock, movimientos, compras (views.py)\n\n"
    "ItemInventarioForm, AjusteStockForm,\n"
    "CompraForm (forms.py)\n\n"
    "rutas /inventario/… (urls.py)\n"
    "7 plantillas (templates/inventario/)\n\n"
    "Compras vive hoy dentro de esta app."))
core = d.paquete("core", 70, 350, 220, 100, GRIS, tam=13,
                 miembros="TimestampedModel,\nRoleRequiredMixin,\ncomando seed_datos")
rest = d.paquete("restaurantes", 70, 520, 220, 80, GRIS, tam=13, miembros="Restaurante, Sucursal")
recetas = d.paquete("recetas", 900, 340, 200, 80, GRIS, tam=12, miembros="ProductoIngrediente")
reportes = d.paquete("reportes", 900, 460, 200, 80, GRIS, tam=12, miembros="dashboard (vistas)")
cocina = d.paquete("cocina", 900, 600, 200, 80, GRIS, tam=12, miembros="insumos faltantes\nde una orden (vistas)")
plantillas = d.paquete("templates", IX, 790, IW, 100, GRIS, tam=13,
                       miembros="base.html, includes/ (generic_form, sidebar…)\n+ static/ (css, js)")


def fy(y):
    return round((y - IY) / IH, 4)


DEP = DEPENDENCIA
d.arista(inv, core, DEP + f"exitX=0;exitY={fy(400)};entryX=1;entryY=0.5;", "«import»")
d.arista(inv, rest, DEP + f"exitX=0;exitY={fy(560)};entryX=1;entryY=0.5;", "«use»\nFK a Sucursal")
d.arista(recetas, inv, DEP + f"exitX=0;exitY=0.5;entryX=1;entryY={fy(380)};", "«use»\nFK a ItemInventario")
d.arista(reportes, inv, DEP + f"exitX=0;exitY=0.5;entryX=1;entryY={fy(500)};", "«import»")
d.arista(cocina, inv, DEP + f"exitX=0;exitY=0.5;entryX=1;entryY={fy(640)};", "«use»\nlee stock_actual")
d.arista(inv, plantillas, DEP + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", "«use» hereda base.html")

# --- sql/
SX = 1170
sql = d.paquete("sql", SX, 100, 550, 700, BLANCO, miembros=" ", tam=14)
tablas = d.paquete("TABLAS", SX + 20, 145, 420, 190, VIOLETA, miembros=" ", tam=13)
inv_sql = d.artefacto("SMARTBITE_INVENTARIO\n_SP.sql", SX + 40, 200, 170, 74, palabra_clave="script", tam=11)
com_sql = d.artefacto("SMARTBITE_COMPRAS\n_SP.sql", SX + 250, 200, 170, 74, palabra_clave="script", tam=11)
d.arista(com_sql, inv_sql, DEP + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
d.texto("«use»", SX + 212, 214, 40, 16, tam=11, alin="center", color="#333333")
d.texto("Compras usa las tablas\ny funciones de Inventario", SX + 140, 282, 200, 34, tam=11, alin="center",
        color="#444444")
inserts = d.paquete("INSERTS", SX + 20, 400, 420, 110, VIOLETA, tam=13,
                    miembros="SMARTBITE_INVENTARIO_SP.sql — categorías de insumo\n(Lácteos, Cárnicos, …)\n"
                             "SMARTBITE_COMPRAS_SP.sql — métodos de pago")
tests = d.paquete("tests", SX + 20, 570, 420, 120, VIOLETA, tam=13,
                  miembros="conftest.py, test_*.py (pytest + psycopg2)\ncontra una rama de prueba de Neon; el "
                           "fixture\naplica INVENTARIO y después COMPRAS")
d.arista(inserts, tablas, DEP + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", "«use» carga datos semilla")
d.arista(tests, tablas, DEP + "exitX=1;exitY=0.3;entryX=1;entryY=0.8;", puntos=[(SX + 480, 606), (SX + 480, 297)])
d.texto("«use»\naplica\ny prueba", SX + 486, 420, 60, 50, tam=11, alin="left", color="#333333")

# --- comentarios
n_alin = d.nota("Hoy Django corre sobre SQLite con sus propios modelos. Alinearlos con el esquema de Neon (y pasar "
                "Django a PostgreSQL) es la spec 003.", 1190, 840, 510, 50, tam=11)
d.ancla(n_alin, inv, "exitX=0;exitY=0.5;entryX=1;entryY=0.85;")
d.ancla(n_alin, sql, "exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
d.nota("«import» = el paquete importa clases del otro (from x.models import …). «use» = depende de él de otra forma: "
       "FK por string (\"app.Modelo\"), plantilla heredada o datos que lee. La flecha va del que depende al que se usa.",
       60, 975, 1120, 46, tam=11)

d.alto = 1050
d.guardar(*salida("08-paquetes-inventario"))
print("ok")
