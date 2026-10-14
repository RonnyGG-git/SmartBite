"""09 — Componentes: las piezas de Inventario en ejecución dentro de la app
Django de Ronny (rama smartbite) y las interfaces por las que se comunican.
Fuente: smartbite/urls.py y settings.py, inventario/ (urls, views, forms,
models, templates), core/mixins.py, reportes/views.py, recetas/models.py,
cocina/views.py. UML 2.5.1, 11.6 y 10.4.

- Componente UML 2: «component» y el icono arriba a la derecha (11.6.4).
- Bola = interfaz provista; socket = requerida (10.4.4). El socket abraza la
  bola = conector de ensamble (11.2.4).
- Puertos en el borde de la aplicación y conectores de delegación hacia la
  pieza interna que atiende (11.3.3).
- La máquina donde corre la base no va acá (es despliegue): solo el esquema.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Componentes - Inventario", 1760, 1080)
d.titulo("Diagrama de componentes — Inventario (Smart Bite)",
         "De qué piezas está hecho Inventario en ejecución dentro de la app Django y por qué interfaces se comunican")

USO = DEPENDENCIA
LINEA = "html=1;endArrow=open;endSize=8;strokeColor=#333333;"

# --- Aplicación Django (con sus componentes internos)
APP_X, APP_Y, APP_W, APP_H = 300, 100, 900, 760
d.componente("Smart Bite — aplicación Django 5.2", APP_X, APP_Y, APP_W, APP_H, BLANCO, tam=13)

urls = d.componente("URLs", 360, 160, 170, 84, detalle="smartbite/urls.py →\ninventario/urls.py")
vistas = d.componente("Vistas de Inventario", 580, 150, 250, 104,
                      detalle="inventario/views.py: listados,\ncrear/editar, item_ajustar_stock,\n"
                              "compra_crear/recibir/anular")
roles = d.componente("Control de roles", 890, 160, 200, 84, detalle="core/mixins.py:\nRoleRequiredMixin")
forms = d.componente("Formularios", 360, 330, 170, 84, detalle="inventario/forms.py")
plantillas = d.componente("Plantillas", 890, 330, 200, 84, detalle="templates/inventario/\n+ base.html")
MOD_Y, MOD_H = 450, 120
modelos = d.componente("Modelos de Inventario", 580, MOD_Y, 250, MOD_H,
                       detalle="inventario/models.py:\nItemInventario, Movimiento-\nInventario, Proveedor, Compra,\n"
                               "DetalleCompra")
ORM_Y, ORM_H = 690, 100
orm = d.componente("ORM de Django", 580, ORM_Y, 250, ORM_H,
                   detalle="django.db: QuerySet, save(),\ntransaction.atomic()")
reportes = d.componente("Reportes", 990, 445, 190, 70, GRIS, detalle="dashboard: stock bajo")
recetas = d.componente("Recetas", 990, 535, 190, 70, GRIS, detalle="FK item_inventario")
cocina = d.componente("Cocina", 990, 625, 190, 70, GRIS, detalle="insumos_faltantes")

# Dependencias internas (punteada: el de la cola usa al de la punta)
d.arista(urls, vistas, USO + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(vistas, roles, USO + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.arista(vistas, forms, USO + "edgeStyle=orthogonalEdgeStyle;rounded=0;exitX=0.15;exitY=1;entryX=0.5;entryY=0;")
d.arista(vistas, plantillas, USO + "edgeStyle=orthogonalEdgeStyle;rounded=0;exitX=0.85;exitY=1;entryX=0.5;entryY=0;")
d.arista(vistas, modelos, USO + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
d.arista(forms, modelos, USO + "edgeStyle=orthogonalEdgeStyle;rounded=0;exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
d.arista(modelos, orm, USO + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

# Interfaz provista por los modelos y usada por las otras apps (dependencia hasta la bola)
Y_IF = MOD_Y + MOD_H / 2
bx, by = d.interfaz_provista(830, Y_IF, "ItemInventario", lado="der", largo=30)
blanco = d.vertice("", bx + 7, by - 1, 2, 2, "rounded=0;fillColor=none;strokeColor=none;")
for comp in (reportes, recetas, cocina):
    d.arista(comp, blanco, USO + "exitX=0;exitY=0.5;")

# --- HTTP: puerto en el borde, bola afuera, el navegador la requiere (socket)
Y_HTTP = 202
d.puerto(APP_X, Y_HTTP)
bola_http, _ = d.interfaz_provista(APP_X - 7, Y_HTTP, "HTTP", lado="izq", largo=24)
NAV_X, NAV_W = 40, 170
nav = d.componente("Navegador web", NAV_X, Y_HTTP - 50, NAV_W, 100, GRIS,
                   detalle="Jefe de Inventario,\nAdministrador,\nJefe de Cocina")
d.interfaz_requerida(NAV_X + NAV_W, Y_HTTP, lado="der", largo=bola_http - 17 - (NAV_X + NAV_W))
d.flecha(APP_X + 7, Y_HTTP, 360, Y_HTTP, LINEA)          # delegación del puerto a las URLs

# --- Base de datos: puerto en el borde, el ORM requiere DB-API (socket) y el driver la provee (bola)
Y_DB = ORM_Y + ORM_H / 2
PX = APP_X + APP_W
d.puerto(PX, Y_DB)
d.flecha(830, Y_DB, PX - 7, Y_DB, LINEA)                 # delegación del ORM al puerto
DRV_X, DRV_W = 1310, 210
drv = d.componente("Driver de base de datos", DRV_X, Y_DB - 55, DRV_W, 110, GRIS,
                   detalle="psycopg2 si el .env define\nDATABASE_URL; si no, sqlite3")
bola_db, _ = d.interfaz_provista(DRV_X, Y_DB, "DB-API 2.0", lado="izq", largo=30)
d.interfaz_requerida(PX + 7, Y_DB, lado="der", largo=bola_db - 17 - (PX + 7))

ESQ_X, ESQ_W = 1290, 430
esq = d.componente("Esquema de la base", ESQ_X, 180, ESQ_W, 330, VIOLETA, detalle=(
    "Tablas que crean las migraciones de Django\n(inventario/migrations):\n\n"
    "inventario_proveedor\n"
    "inventario_iteminventario\n"
    "inventario_movimientoinventario\n"
    "inventario_compra\n"
    "inventario_detallecompra\n"
    "+ las tablas de las otras apps\n\n"
    "Sin triggers ni funciones: las reglas (sumar o\n"
    "restar stock, estados de la compra) están en\n"
    "las vistas de Django."))
d.arista(drv, esq, USO + "exitX=0.45;exitY=0;entryX=0.5;entryY=1;")
d.texto("«use»\nSQL", DRV_X + 0.45 * DRV_W + 8, 560, 60, 32, tam=11, alin="left", color="#222222")

d.nota("Bola (círculo) = interfaz que el componente ofrece. Socket (medio círculo) = interfaz que necesita; cuando "
       "abraza una bola, las dos piezas están conectadas. Punteada = dependencia (el de la cola usa al de la punta). "
       "Cuadrado en el borde = puerto; la línea con flecha que entra o sale de él lleva el pedido a la pieza interna "
       "(delegación).", 40, 890, 860, 76, tam=11)
d.nota("Hoy la única interfaz hacia afuera son páginas HTML por HTTP: todavía no hay API REST. Compras vive dentro de la "
       "misma app (las vistas compra_* usan los mismos modelos). Dónde corre cada pieza (PC, Neon): diagrama de "
       "despliegue.", 920, 890, 800, 76, tam=11)

d.alto = 1000
d.guardar(*salida("09-componentes-inventario"))
print("ok")
