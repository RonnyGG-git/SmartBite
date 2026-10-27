"""08 — Paquetes: cómo se organiza el código de Inventario en la app Django
de Ronny (rama smartbite), de qué depende y quién depende de él. Cada
dependencia sale de un import o de una FK por string real:
inventario/models.py y views.py, recetas/models.py, reportes/views.py,
cocina/views.py, smartbite/urls.py. UML 2.5.1, cláusula 12.

- Nombre en la pestaña si el paquete muestra miembros; en el cuerpo si no.
- «import» = importa clases del otro (from x.models import …), 7.4.4.
  «use» + un nombre = otro uso (FK por string, include de URLs, plantilla
  heredada, datos que lee sin importar), 7.7.4.
- Sin ciclos: nadie de quien depende inventario depende de inventario.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Paquetes - Inventario", 1560, 1020)
d.titulo("Diagrama de paquetes — Inventario (Smart Bite)",
         "Dónde vive el código de Inventario en el proyecto Django, de qué depende y quién depende de él")

# --- Repositorio con todas las apps
d.paquete("SmartBite (repositorio)", 40, 100, 1140, 800, BLANCO, miembros=" ", tam=14)

conf = d.paquete("smartbite", 70, 145, 300, 110, GRIS, tam=13,
                 miembros="settings.py: INSTALLED_APPS,\nDATABASES (DATABASE_URL o SQLite)\n"
                          "urls.py: include() de cada app")
for i, nombre in enumerate(["cuentas", "catalogo", "operativo", "caja", "menu_cliente", "cliente"]):
    d.paquete(nombre, 410 + i * 125, 150, 115, 60, GRIS, tam=12)
d.texto("Las otras apps no dependen de Inventario ni Inventario de ellas.", 660, 222, 500, 18, tam=11,
        alin="right", color="#666666")

IX, IY, IW, IH = 390, 330, 400, 330
inv = d.paquete("inventario", IX, IY, IW, IH, AZUL, tam=15, miembros=(
    "models.py: Proveedor, ItemInventario,\n"
    "MovimientoInventario, Compra, DetalleCompra\n\n"
    "views.py: listado, crear y editar ítem,\n"
    "item_ajustar_stock, movimientos, proveedores,\n"
    "compras (crear, detalle, recibir, anular)\n\n"
    "forms.py: ItemInventarioForm, AjusteStockForm,\n"
    "ProveedorForm, CompraForm, DetalleCompraFormSet\n\n"
    "urls.py: /inventario/…   admin.py\n"
    "templates/inventario/: 7 plantillas\n\n"
    "Compras (Proveedor, Compra) vive hoy acá."))
core = d.paquete("core", 70, 340, 220, 110, GRIS, tam=13,
                 miembros="models.py: TimestampedModel\nmixins.py: RoleRequiredMixin,\nusuario_tiene_rol")
rest = d.paquete("restaurantes", 70, 540, 220, 80, GRIS, tam=13, miembros="models.py: Restaurante, Sucursal")
recetas = d.paquete("recetas", 930, 330, 230, 80, GRIS, tam=12, miembros="models.py: ProductoIngrediente")
reportes = d.paquete("reportes", 930, 455, 230, 80, GRIS, tam=12, miembros="views.py: DashboardView")
cocina = d.paquete("cocina", 930, 580, 230, 80, GRIS, tam=12, miembros="views.py: insumos_faltantes(orden),\n"
                                                                        "CocinaListView")
plantillas = d.paquete("templates", IX, 770, IW, 90, GRIS, tam=13,
                       miembros="base.html\nincludes/: sidebar, generic_form, form_fields…")

# --- Framework, fuera del repositorio
dj = d.paquete("django", 1240, 720, 280, 140, GRIS, tam=13,
               miembros="db: models, transaction\nforms\nviews.generic, shortcuts\nurls, contrib.admin")


def fy(y):
    return round((y - IY) / IH, 4)


DEP = DEPENDENCIA


def dep(a, b, estilo, rotulo, tx, ty, w=150, puntos=()):
    """Dependencia con el rótulo en un texto aparte, arriba de la línea, para que
    no tape la punta de flecha en los tramos cortos."""
    d.arista(a, b, DEP + estilo, puntos=puntos)
    d.texto(rotulo, tx - w / 2, ty, w, 15 * (rotulo.count("\n") + 1) + 2, tam=11, alin="center", color="#222222")


dep(conf, inv, "edgeStyle=orthogonalEdgeStyle;rounded=0;exitX=1;exitY=0.85;entryX=0.15;entryY=0;",
    "«use»\ninclude('inventario.urls')", IX + 0.15 * IW + 92, 266, w=170)
dep(inv, core, f"exitX=0;exitY={fy(395)};entryX=1;entryY=0.5;", "«import»", 340, 375, w=90)
dep(inv, rest, f"exitX=0;exitY={fy(580)};entryX=1;entryY=0.5;", "«use»\nFK sucursal", 340, 545, w=100)
dep(recetas, inv, f"exitX=0;exitY=0.5;entryX=1;entryY={fy(370)};", "«use»\nFK item_inventario", 860, 335)
dep(reportes, inv, f"exitX=0;exitY=0.5;entryX=1;entryY={fy(495)};", "«import»\nItemInventario", 860, 460)
dep(cocina, inv, f"exitX=0;exitY=0.5;entryX=1;entryY={fy(620)};", "«use»\nlee stock_actual", 860, 585)
dep(inv, plantillas, "exitX=0.35;exitY=1;entryX=0.35;entryY=0;", "«use» extends base.html", IX + 0.35 * IW + 82, 705,
    w=160)
dep(inv, dj, "edgeStyle=orthogonalEdgeStyle;rounded=0;exitX=0.85;exitY=1;entryX=0.5;entryY=0;", "«import»",
    1300, 676, w=80, puntos=[(IX + 0.85 * IW, 695), (1380, 695)])

d.nota("«import» = el paquete importa clases del otro (from inventario.models import ItemInventario). «use» = "
       "depende de otra forma: FK por string (\"restaurantes.Sucursal\"), include() de las URLs, plantilla que "
       "hereda, o datos que lee sin importar (cocina llega a stock_actual por producto.ingredientes). La flecha va "
       "del que depende al que usa.", 40, 920, 1140, 60, tam=11)
d.nota("La carpeta sql/ (el diseño SQL anterior de Inventario y Compras) quedó archivada: ya no forma parte del "
       "proyecto. La base sale de los modelos de Django (migraciones).", 1220, 920, 300, 76, tam=11)

d.alto = 1020
d.guardar(*salida("08-paquetes-inventario"))
print("ok")
