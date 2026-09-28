# Smart Bite — Django (MVT)

Sistema de gestión para restaurantes (mesas, órdenes, cocina, caja, inventario y
reportes) construido como un proyecto Django monolítico usando el patrón
**Model-View-Template (MVT)**.

Es la migración del frontend React de `smartibite-frontend` a Django. El diseño
completo de esa migración —apps, modelos, decisiones de arquitectura— está
documentado en el `README.md` del repo original (`smartibite-frontend/README.md`).

## Índice

- [Stack](#stack)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Apps del proyecto](#apps-del-proyecto)
- [Roles y permisos](#roles-y-permisos)
- [Puesta en marcha](#puesta-en-marcha)
- [Flujo probado end-to-end](#flujo-probado-end-to-end)
- [Trabajar con Git y ramas](#trabajar-con-git-y-ramas)
- [Paridad con los casos de uso](#paridad-con-los-casos-de-uso)
- [Pendiente](#pendiente-fuera-de-alcance-de-esta-migración)

## Stack

- **Backend:** Django 5.2 (Python), patrón MVT.
- **Base de datos:** SQLite (`db.sqlite3`) en desarrollo.
- **Autenticación:** modelo de usuario propio (`cuentas.Usuario`), sesiones de
  Django (reemplaza el JWT + `localStorage` del frontend React original).
- **Generación de QR:** `qrcode` + `Pillow` (menú público por mesa).
- **Frontend:** templates Django (server-rendered), CSS propio en
  `static/css/theme.css`, sin framework JS.

## Estructura del proyecto

Cada app de dominio sigue la misma convención interna de Django:
`models.py`, `views.py`, `urls.py`, `forms.py` (cuando aplica), `admin.py`,
`migrations/` y `templates/<app>/`.

```text
smartbite/
├── manage.py
├── requirements.txt
├── db.sqlite3                  # base de datos SQLite (desarrollo)
├── static/
│   └── css/theme.css           # estilos globales
├── templates/                  # templates compartidos entre apps
│   ├── base.html                # layout base (sidebar + bloque de contenido)
│   └── includes/
│       ├── sidebar.html          # menú lateral, varía según el rol del usuario
│       ├── generic_form.html     # formulario genérico reutilizado por los CRUD
│       └── confirm_delete.html   # confirmación genérica de borrado
│
├── smartbite/                  # paquete de configuración del proyecto
│   ├── settings.py              # INSTALLED_APPS, AUTH_USER_MODEL, LOGIN_URL, etc.
│   ├── urls.py                  # enrutador raíz — incluye las urls de cada app
│   ├── wsgi.py / asgi.py
│
├── core/                       # utilidades compartidas (no es un dominio propio)
│   ├── models.py                 # TimestampedModel (creado_en/actualizado_en, abstracto)
│   ├── mixins.py                 # RoleRequiredMixin y decorador rol_requerido
│   └── management/commands/
│       └── seed_datos.py         # crea los 5 roles del sistema + métodos de pago
│
├── cuentas/                    # usuarios, roles y permisos (autenticación)
├── restaurantes/                # restaurantes y sucursales
├── catalogo/                    # categorías y productos del menú
├── inventario/                  # stock, movimientos, proveedores y compras
├── recetas/                     # relación producto ↔ ítems de inventario
├── operativo/                   # mesas, clientes, órdenes y QR
├── caja/                        # métodos de pago, cobro y ventas
├── cocina/                      # vista de órdenes pendientes/en preparación
├── cliente/                      # cara pública de Pedidos: menú QR, autopedido, estado, opiniones
├── menu_cliente/                 # solo redirige /menu/?mesa=N (QR antiguos) a cliente
└── reportes/                    # dashboard y reportes agregados
```

## Apps del proyecto

Cada app se corresponde con un dominio del negocio (bounded context). Los
modelos con FK a otra app referencian por string (`"app.Modelo"`) para evitar
imports circulares — es el patrón usado en todo el proyecto.

### `core` — utilidades compartidas

No es un dominio de negocio, es infraestructura reutilizada por el resto:

- `TimestampedModel` (`core/models.py`): modelo abstracto con `creado_en` /
  `actualizado_en`. La mayoría de modelos del proyecto heredan de él.
- `RoleRequiredMixin` y `rol_requerido` (`core/mixins.py`): control de acceso
  por rol para vistas basadas en clase y en función respectivamente. Reemplaza
  al componente `RutaProtegida.jsx` del frontend React original.
- `seed_datos` (`core/management/commands/seed_datos.py`): comando de gestión
  que crea los 5 roles del sistema y los métodos de pago base.

### `cuentas` — usuarios, roles y permisos

Autenticación y autorización del sistema.

- **Modelos:** `Permiso` (catálogo granular, ej. `CREAR_PRODUCTO`), `Rol`
  (uno de los 5 roles del sistema, con M2M a `Permiso`), `Usuario` (modelo de
  usuario propio — `AUTH_USER_MODEL`, login por `email`, FK a `Rol` y a
  `Sucursal`).
- **Rutas** (`/cuentas/`): `login/`, `logout/`, CRUD de `usuarios/` y `roles/`,
  gestión de permisos por rol (`roles/<id>/permisos/`).

### `restaurantes` — restaurantes y sucursales

- **Modelos:** `Restaurante` (razón social, NIF, contacto), `Sucursal` (FK a
  `Restaurante`; punto físico donde operan mesas, productos e inventario).
- **Rutas** (`/restaurantes/`): CRUD de `restaurantes/` y `sucursales/`.

### `catalogo` — productos del menú

- **Modelos:** `Categoria`, `Producto` (precio, imagen, FK a `Categoria` y a
  `Sucursal`, flag `disponible`).
- **Rutas** (`/productos/`): CRUD de productos (incluye
  `toggle_disponibilidad`) y de categorías.

### `inventario` — stock y compras

- **Modelos:** `Proveedor`, `ItemInventario` (stock actual/mínimo, costo
  unitario, propiedad `stock_bajo`), `MovimientoInventario` (entrada/salida
  manual), `Compra` + `DetalleCompra` (compra a proveedor con flujo
  pendiente → recibida/anulada; al recibir, suma stock).
- **Rutas** (`/inventario/`): CRUD de ítems (`item_ajustar` para ajuste manual
  de stock), listado de movimientos, CRUD de proveedores, y compras
  (`compra_crear`, `compra_detalle`, `compra_recibir`, `compra_anular`).

### `recetas` — ingredientes por producto

- **Modelos:** `ProductoIngrediente` (relación producto ↔ ítem de inventario,
  con `cantidad_requerida`; permite modelar qué consume cada plato del stock).
- **Rutas** (`/recetas/`): CRUD de recetas.

### `operativo` — mesas, clientes y órdenes

El corazón del flujo de servicio en sala.

- **Modelos:** `Mesa` (estado `DISPONIBLE`/`OCUPADA`/`RESERVADA`, FK a
  `Sucursal`, propiedad `orden_activa`), `Cliente`, `Orden` (estado
  `PENDIENTE` → `EN_PREPARACION` → `LISTA` → `ENTREGADA`/`CANCELADA`, FK a
  `Mesa` y `Cliente`), `DetalleOrden` (línea de producto dentro de una orden).
- **Rutas** (`/operativo/`): CRUD de mesas, generación de QR por mesa
  (`mesas/qr/<id>/`), crear orden, agregar producto a una orden, cambiar
  estado, solicitar cuenta, alta rápida de cliente.
- `Orden` guarda además `origen` (mesero o autopedido QR), el tiempo estimado
  que fija el Chef y cuándo se pidió la cuenta.
- El Mesero solo cancela órdenes `PENDIENTE` y pide la cuenta de las `LISTA`;
  la preparación la mueve el Chef en `cocina` y el cierre lo hace `caja`.
- `generar_qr` codifica en el QR la URL de `cliente:mesa` usando `qrcode`.

### `caja` — pagos y ventas

- **Modelos:** `MetodoPago` (Efectivo, Tarjeta, Transferencia, Billetera
  Digital — creados por `seed_datos`), `Pago` (FK a `Orden` y `MetodoPago`,
  monto, referencia de transacción).
- **Rutas** (`/caja/`): listado de pagos, `cobrar_orden` (crea el `Pago`,
  pasa la orden a `ENTREGADA` y libera la mesa dentro de una transacción
  atómica), `por-cobrar/` (cuentas que pidió el mesero), listado de ventas
  (`ventas/`, órdenes ya entregadas).

### `cocina` — pantalla de preparación

Sin modelos propios: reutiliza `operativo.Orden`.

- **Vista:** `CocinaListView` lista las órdenes en estado `PENDIENTE` o
  `EN_PREPARACION`, visible solo para `ADMINISTRADOR`/`JEFE_COCINA`, y avisa
  si el stock no alcanza para la receta de algún platillo.
- **Rutas** (`/cocina/`): listado y `ordenes/<id>/estado/` (iniciar con tiempo
  estimado → marcar lista).

### `cliente` — el comensal (sin login)

Cara pública del módulo de Pedidos del diagrama de casos de uso. La mesa se
identifica al escanear su QR y los pedidos del comensal se recuerdan en su
sesión. Las páginas usan `templates/base_publico.html`, que se ve igual haya
o no una sesión de personal abierta.

- **Modelos:** `Retroalimentacion` (sugerencia o denuncia, opcionalmente
  asociada a la mesa; el Administrador la marca como revisada).
- **Rutas** (`/cliente/`): `mesa/<id>/` (destino del QR), `menu/` (solo
  platillos disponibles de la sucursal de la mesa), `pedido/` (POST del
  autopedido: crea la orden `PENDIENTE` y ocupa la mesa), `pedido/<id>/`
  (estado del pedido, solo para quien lo hizo), `opinion/`, y para el
  Administrador `retroalimentacion/`.

### `menu_cliente` — compatibilidad

Solo redirige `/menu/?mesa=<id>` (URL de los QR impresos antes de existir
`cliente`) a `/cliente/mesa/<id>/`.

### `reportes` — dashboard y reportes

Sin modelos propios: agrega datos de `caja`, `catalogo`, `cuentas`,
`inventario` y `operativo`.

- **Vistas:** `DashboardView` (usuarios activos, productos, mesas
  ocupadas, ítems con stock bajo, órdenes y ventas del día — solo
  `ADMINISTRADOR`), `ReportesView` (órdenes por estado, ventas por método de
  pago).
- **Rutas:** `reportes/urls.py` está incluido en la raíz (`''`) en
  `smartbite/urls.py`, así que el dashboard es la home (`/`) del sitio.

## Roles y permisos

Definidos en `cuentas.models.ROLES_SISTEMA` y creados por `seed_datos`:

| Rol | Acceso típico |
|---|---|
| `ADMINISTRADOR` | Todo el sistema (equivalente a superusuario a nivel de negocio) |
| `JEFE_INVENTARIO` | Inventario, proveedores, compras (platillos solo en consulta) |
| `JEFE_COCINA` | Pantalla de cocina, platillos, categorías y recetas |
| `MESERO` | Mesas, crear órdenes, cancelar pendientes, solicitar cuenta |
| `CAJERO` | Cobrar órdenes, ventas |

El control de acceso se aplica por vista con `RoleRequiredMixin.roles_permitidos`
(class-based views) o el decorador `rol_requerido(...)` (function-based views),
ambos en `core/mixins.py`. Un `is_superuser` de Django siempre tiene acceso
total, sin importar el rol.

## Puesta en marcha

```bash
# Entorno virtual ya creado en ./venv — para reactivarlo:
venv\Scripts\activate            # Windows

pip install -r requirements.txt

python manage.py migrate
python manage.py seed_datos      # crea los 5 roles del sistema y métodos de pago
python manage.py createsuperuser
python manage.py runserver
```

Después de crear el superusuario, asígnale el rol `ADMINISTRADOR` desde `/admin/` (o por
shell) para que el sidebar y las vistas de gestión se habiliten correctamente:

```python
python manage.py shell
>>> from cuentas.models import Usuario, Rol
>>> u = Usuario.objects.get(email="tu@email.com")
>>> u.rol = Rol.objects.get(nombre="ADMINISTRADOR")
>>> u.save()
```

## Flujo probado end-to-end

Restaurante → Sucursal → Categoría → Producto → Ítem de inventario → Mesa → Compra a
proveedor (con recepción que suma stock) → Ajuste manual de stock → Crear orden → Agregar
producto a la orden → Cambiar estado → Cobrar (genera Pago, cierra la orden, libera la
mesa) → aparece en Ventas. También: QR de mesa → menú público sin login, y control de
acceso por rol (un usuario `MESERO` no puede entrar a pantallas de `ADMINISTRADOR`/`CAJERO`).

## Trabajar con Git y ramas

El repositorio remoto está en GitHub: `https://github.com/RonnyGG-git/SmartBite.git`.
La rama por defecto es `main`.

### Ver el estado y las ramas actuales

```bash
git status                  # cambios pendientes en el working directory
git branch                  # ramas locales (la actual tiene un *)
git branch -a               # ramas locales + remotas
```

### Crear una rama nueva a partir de `main`

Antes de crear o cambiar de rama, revisa `git status` — si hay cambios sin
confirmar, haz commit o `git stash` primero para no perder trabajo.

```bash
git checkout main           # asegúrate de estar parado en main
git pull origin main         # trae los últimos cambios del remoto
git checkout -b smartbite    # crea la rama "smartbite" y cambia a ella
```

`checkout -b` crea la rama con el contenido exacto que tiene `main` en ese
momento (un nuevo puntero sobre el mismo commit) — no hace falta copiar nada
a mano.

### Subir la rama nueva al remoto

```bash
git push -u origin smartbite   # publica la rama y la vincula con origin/smartbite
```

El flag `-u` (`--set-upstream`) hace que, de ahí en adelante, un simple
`git push` / `git pull` en esa rama ya sepa contra qué rama remota sincronizar.

### Trabajar en la rama y guardar cambios

```bash
git checkout smartbite            # cambiarte a la rama (si no estás ya en ella)
git add archivo.py                # o git add . para todos los cambios
git commit -m "Mensaje descriptivo del cambio"
git push                          # sube los commits a origin/smartbite
```

### Traer cambios nuevos de `main` hacia `smartbite`

Si `main` avanza mientras trabajas en `smartbite` y quieres incorporar esos
cambios:

```bash
git checkout smartbite
git merge main                    # trae los commits nuevos de main a smartbite
```

### Volver a `main` o cambiar entre ramas

```bash
git checkout main            # o: git checkout smartbite
```

### Publicar los cambios de `smartbite` de vuelta a `main`

Cuando el trabajo en `smartbite` esté listo, la forma más segura es abrir un
Pull Request en GitHub (`origin/smartbite` → `main`) para poder revisar el
diff antes de integrar, en vez de mergear directo desde la terminal:

```bash
gh pr create --base main --head smartbite --title "..." --body "..."
```

### Comandos que hay que usar con cuidado

Estos comandos pueden descartar trabajo sin confirmar — revisa siempre
`git status` antes de usarlos, y solo con autorización explícita:

```bash
git checkout -- archivo.py   # descarta cambios locales de un archivo
git reset --hard             # descarta todos los cambios sin confirmar
git clean -fd                # borra archivos no rastreados
git push --force              # sobrescribe el historial remoto
```

## Paridad con los casos de uso

`docs/PARIDAD-CASOS-DE-USO.md` contrasta cada caso de uso del diagrama
(7 módulos, 114 casos) con lo que existe en el código.

## Pendiente (fuera de alcance de esta migración)

Diseño de API (DRF), base de datos de producción (Postgres), despliegue. Ver la sección 9
del README de migración original.
