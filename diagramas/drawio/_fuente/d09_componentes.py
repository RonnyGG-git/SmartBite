"""09 — Componentes: las piezas de Inventario en ejecución (la app Django y
el esquema de Neon) y las interfaces por las que se comunican. Fuente:
inventario/ (urls, views, forms, models, templates), core/mixins.py y
sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql.

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1, 11.6 y 10.4):
- Notación UML 2 del componente: rectángulo con «component» y el icono de
  componente arriba a la derecha (11.6.4). La versión anterior usaba el
  estilo de UML 1 (dos pestañas sobresaliendo del borde izquierdo).
- El navegador ya no se une con una flecha de dos puntas (no existe en UML):
  la app ofrece la interfaz HTTP (bola) y el navegador la requiere (socket).
- 'PostgreSQL en Neon' es un nodo de despliegue, no un componente: sale de
  este diagrama (está en el de despliegue).
- Interfaz provista = bola; interfaz requerida = socket (10.4.4). OJO: en la
  tabla de símbolos que circula en clase estos dos están al revés.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Componentes - Inventario", 1760, 1060)
d.titulo("Diagrama de componentes — Inventario (Smart Bite)",
         "De qué piezas está hecho Inventario en ejecución y por qué interfaces se comunican la aplicación Django y "
         "la base de datos")

USO = DEPENDENCIA
SPEC003 = "strokeColor=#b85450;fontColor=#b85450;dashPattern=8 4;"

# --- Aplicación Django (con sus componentes internos)
APP_X, APP_Y, APP_W, APP_H = 300, 100, 720, 820
d.componente("Smart Bite — aplicación Django 5.2", APP_X, APP_Y, APP_W, APP_H, BLANCO, tam=13)

# Interfaz HTTP: la app la ofrece (bola) y el navegador la requiere (socket)
Y_HTTP = 205
bola_x, _ = d.interfaz_provista(APP_X, Y_HTTP, "HTTP", lado="izq", largo=22)
NAV_X, NAV_W = 40, 170
nav = d.componente("Navegador web", NAV_X, Y_HTTP - 45, NAV_W, 90, GRIS, detalle="Jefe de Almacén,\nAdministrador")
d.interfaz_requerida(NAV_X + NAV_W, Y_HTTP, lado="der", largo=bola_x - 9 - 8 - (NAV_X + NAV_W))

sqlite = d.componente("SQLite (db.sqlite3)", 40, 500, 190, 90, GRIS, detalle="la base de Django hoy\n(desarrollo)")

urls = d.componente("URLs de inventario", 330, 165, 190, 84, detalle="inventario/urls.py\n/inventario/…")
vistas = d.componente("Vistas de Inventario", 560, 160, 230, 94,
                      detalle="inventario/views.py: listado,\ncrear/editar, item_ajustar_stock,\nmovimientos, compras")
roles = d.componente("Control de roles", 820, 160, 180, 94, detalle="core/mixins.py:\nRoleRequiredMixin")
forms = d.componente("Formularios", 330, 330, 190, 84, detalle="inventario/forms.py")
plantillas = d.componente("Plantillas", 820, 330, 180, 84, detalle="templates/inventario/\n+ base.html")
orm = d.componente("Modelos / ORM", 560, 490, 230, 104,
                   detalle="inventario/models.py:\nItemInventario, Movimiento-\nInventario, Proveedor, Compra")
reportes = d.componente("Reportes", 330, 690, 190, 84, GRIS, detalle="dashboard: stock bajo")
recetas = d.componente("Recetas y Cocina", 810, 690, 190, 84, GRIS, detalle="ingredientes e\ninsumos faltantes")

d.arista(urls, vistas, USO + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(vistas, roles, USO + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(vistas, forms, USO + "edgeStyle=orthogonalEdgeStyle;exitX=0.2;exitY=1;entryX=0.5;entryY=0;")
d.arista(vistas, plantillas, USO + "edgeStyle=orthogonalEdgeStyle;exitX=0.8;exitY=1;entryX=0.5;entryY=0;")
d.arista(vistas, orm, USO + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
d.arista(reportes, orm, USO + "edgeStyle=orthogonalEdgeStyle;exitX=0.5;exitY=0;entryX=0;entryY=0.95;")
d.arista(recetas, orm, USO + "edgeStyle=orthogonalEdgeStyle;exitX=0;exitY=0.5;entryX=0.8;entryY=1;",
         puntos=[(744, 732)])
d.arista(orm, sqlite, USO + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;", "«use» hoy")

# --- Esquema de Inventario en PostgreSQL, con sus interfaces provistas
ESQ_X, ESQ_Y, ESQ_W, ESQ_H = 1340, 160, 380, 600
esquema = d.componente("Esquema de Inventario", ESQ_X, ESQ_Y, ESQ_W, ESQ_H, VIOLETA, detalle=(
    "sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql\n\n"
    "Tablas: categoria_insumo, item_inventario,\n"
    "item_inventario_historial, movimiento_inventario,\n"
    "solicitud_reabastecimiento\n\n"
    "Triggers: código único, stock protegido,\n"
    "historial de cambios, aplicar y aprobar\n"
    "movimientos, pérdida por vencimiento repetida,\n"
    "solicitud automática\n\n"
    "Vistas: control de existencias, próximos a\n"
    "vencer, reporte de inventario\n\n"
    "El stock solo cambia por el kardex; el kardex\n"
    "no se edita ni se borra."))
bolas = {}
for clave, cy, texto in [("kardex", 470, "kardex: INSERT en\nmovimiento_inventario"),
                         ("vistas", 545, "vistas de consulta"),
                         ("perdidas", 620, "fn_generar_perdidas_\nvencimiento()"),
                         ("dispo", 720, "fn_verificar_\ndisponibilidad(items)")]:
    bolas[clave] = d.interfaz_provista(ESQ_X, cy, texto, lado="izq", largo=30)

compras = d.componente("Esquema de Compras", ESQ_X, 840, ESQ_W, 100, VIOLETA,
                       detalle="sql/TABLAS/SMARTBITE_COMPRAS_SP.sql\n(spec 002, en curso)")
d.arista(compras, esquema, USO + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", "«use»")
d.texto("ENTRADA al aprobar calidad (compra_id);\nsolicitudes ATENDIDA", ESQ_X - 80, 784, 250, 34, tam=11,
        alin="right", color="#444444")


def usa(origen, bola, estilo, texto="«use»"):
    """Dependencia de uso desde un componente hasta la bola de una interfaz provista (UML 10.4.4)."""
    bx, by = bola
    d.arista(origen, d.vertice("", bx - 9, by - 1, 2, 2, "rounded=0;fillColor=none;strokeColor=none;"),
             USO + estilo, texto)


usa(orm, bolas["kardex"], SPEC003 + "exitX=1;exitY=0.2;entryX=0;entryY=0.5;")
usa(orm, bolas["vistas"], SPEC003 + "exitX=1;exitY=0.85;entryX=0;entryY=0.5;")
usa(recetas, bolas["dispo"], SPEC003 + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

d.nota("En rojo: conexiones de la spec 003. Hoy Django usa SQLite con sus propios modelos y cambia el stock en "
       "Python; con la spec 003 pasa a Neon y usa estas interfaces.", 330, 800, 330, 80, tam=11)
d.nota("fn_generar_perdidas_vencimiento() la tiene que ejecutar la aplicación una vez por día (RF-26); todavía "
       "nadie la llama.", 680, 800, 320, 80, tam=11)
d.nota("Bola (círculo) = interfaz que el componente ofrece. Socket (medio círculo) = interfaz que el componente "
       "necesita. Flecha punteada = dependencia: el de la cola usa al de la punta.", 40, 960, 980, 44, tam=11)

d.alto = 1030
d.guardar(*salida("09-componentes-inventario"))
print("ok")
