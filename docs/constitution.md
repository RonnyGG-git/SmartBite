# Constitución — Base de Datos y API (José)

> Estado: aprobada 2026-09-23 (enmienda sobre la versión aprobada 2026-09-17)

## Enmienda 2026-09-23 — qué cambió y por qué

La versión anterior asumía un frente acotado a `HU-BD-*`/`HU-API-*` con Django
como única fuente del esquema. Ronny (líder) confirmó que el encargo real es
más amplio: José construye **la base de datos del proyecto completo** (no
solo su frente), como punto de partida del proyecto, entregada como **SQL
puro** (`sql/TABLAS/`, `sql/INSERTS/`) que se ejecuta de verdad contra Neon —
no solo documentación. Trabaja en sub-ramas de `jose_blanco`, una por módulo.
Esto tensiona los principios 1 y 7 de la versión anterior (alcance acotado a
un frente; Django como dueño del esquema) — se resuelven abajo, no en
silencio.

## Principios

1. **Alcance ampliado — toda la base de datos del proyecto:** José diseña y
   construye el esquema físico completo de Smart Bite (tablas, relaciones,
   índices, datos semilla) para los módulos en alcance (punto 2), más la API
   REST que los expone. No implementa lógica de negocio/reglas de aplicación
   de otros dominios (aprobaciones, flujos de estado, permisos de negocio) —
   eso sigue siendo dependencia resuelta de quien sea dueño de ese módulo
   (Integrante 4: inventario/cocina/catálogo; Integrante 2: pagos;
   Integrante 3: cuentas). Traduce reglas ya definidas a estructura de datos
   (tablas, columnas, constraints, tipos), nunca a lógica de aplicación.
2. **Módulos en alcance ahora [NECESITA CONFIRMACIÓN DE JOSÉ/RONNY]:** los 10
   dominios ya implementados en Django (`cuentas`, `restaurantes`,
   `catalogo`, `inventario`, `recetas`, `operativo`, `caja`, `cocina`,
   `menu_cliente`, `reportes`) más las ampliaciones ya documentadas de
   Inventario (`CU-INV-01..17`) y Compras (`CU-COM-01..20`) en `contexto/`.
   **Quedan fuera hasta que el equipo lo decida explícitamente** —siguen
   siendo "conflicto de alcance sin resolver" según el propio análisis del
   equipo—: Facturación DIAN, Pagos con pasarela/autoservicio de cliente,
   Administración de empleados (RR. HH., distinto de `cuentas.Usuario`). No
   empezar la spec de un módulo fuera de los 10 ya implementados sin
   confirmar con Ronny primero.
3. **El SQL es la fuente real, no un export:** los scripts de
   `sql/TABLAS/SMARTBITE_<MODULO>_SP.sql` y `sql/INSERTS/` se ejecutan de
   verdad contra Neon. Una vez creado el esquema ahí, los `models.py` Django
   afectados se actualizan (con sus migraciones) para reflejarlo — el SQL
   manda, Django se ajusta a él, nunca al revés, en este frente.
4. **Una spec por módulo:** cada módulo (`inventario`, `compras`, …) es su
   propia ronda SDD (`specs/NNN-esquema-<modulo>/`) con su propia sub-rama
   sobre `jose_blanco` (`jose_blanco/esquema-<modulo>`). No se empieza la
   spec de un módulo nuevo antes de validar el anterior, salvo decisión
   explícita de trabajar dos en paralelo.
5. **Convenciones existentes se respetan:** identificadores en español
   (`nombre`, `precio`, `stock_actual`...), igual que el código actual. En
   SQL puro, cada FK entre tablas de distinto módulo lleva nombre explícito
   de constraint (`fk_<tabla>_<columna>`).
6. **Config y secretos fuera del código:** `SECRET_KEY`, `DEBUG`,
   `ALLOWED_HOSTS`, la cadena de conexión a Neon y cualquier API key nunca se
   commitean — solo en `.env` local (ya en `.gitignore`) o secretos del
   entorno de despliegue.
7. **Probar en una rama de Neon antes de tocar la real:** si el proyecto de
   Neon lo permite (branching de bases de datos), cada script de
   `sql/TABLAS/` se corre primero contra una base de desarrollo/prueba, nunca
   directo contra la base que usa el equipo. SQLite queda solo como fallback
   para quien no tenga acceso a Neon.
8. **Permisos de API = mismo patrón que `core.mixins`** (para cuando llegue
   `HU-API-01`): bypass si `is_superuser`, bypass si la vista no restringe
   roles, si no `usuario.rol.nombre in roles_permitidos`. Se porta a un
   `BasePermission` de DRF, no se reinventa el control de acceso.
9. **Decisiones estructurales van a ADR:** generación del "código único" de
   producto, tipos de datos para campos monetarios/fechas, TokenAuth vs JWT,
   estrategia de despliegue/respaldo.
10. **La API expone datos, no inventa reglas** (para cuando llegue
    `HU-API-*`): todo endpoint de escritura valida contra las reglas que ya
    definió el módulo dueño de ese dato.
