# Plan técnico — Spec 001 (Esquema de datos de Inventario)

> Estado: aprobada 2026-09-23

## Módulos
- `sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql` → DDL de las 5 tablas, triggers y
  la vista de reporte. Cubre todos los RF de la spec.
- `sql/INSERTS/SMARTBITE_INVENTARIO_SP.sql` → datos semilla (categorías base
  de ejemplo, sin insumos ficticios de negocio real).
- `inventario/models.py` (Django) → se actualiza en una tarea posterior a
  este plan, para reflejar el esquema una vez aplicado en Neon (constitución,
  principio 3). No se toca en esta ronda.

## Modelo de datos y contratos

Dependencias externas a este módulo: `restaurantes_sucursal(id)` y
`cuentas_usuario(id)` — nombres previstos según `restaurantes/models.py` y
`cuentas/models.py`, pero **verificado en Neon (2026-09-23, `production`,
solo lectura) que esas tablas todavía no existen** — esos módulos no
tienen su propia spec/plan en este proceso SDD. Por eso `sucursal_id`,
`usuario_id` y `aprobado_por` se crean como columnas simples (`BIGINT`,
sin `REFERENCES`) en vez de FKs reales — mismo criterio que la Decisión #4
para `compra_id`. Se agregan las constraints con `ALTER TABLE` cuando esos
módulos tengan su propia spec.

### `categoria_insumo`
```sql
CREATE TABLE categoria_insumo (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_categoria_insumo_nombre UNIQUE (nombre)
);
```
Cubre RF-3.

### `item_inventario` (el insumo)
```sql
CREATE TABLE item_inventario (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_unico            VARCHAR(30) NOT NULL,
    nombre                  VARCHAR(150) NOT NULL,
    descripcion             VARCHAR(255),
    unidad_medida           VARCHAR(20) NOT NULL,
    categoria_id            BIGINT NOT NULL REFERENCES categoria_insumo(id),
    sucursal_id             BIGINT NOT NULL,  -- sin FK todavía: ver Decisión #4
    stock_actual            NUMERIC(12,3) NOT NULL DEFAULT 0,
    stock_minimo            NUMERIC(12,3),              -- NULL = no configurado (RF-11)
    costo_unitario          NUMERIC(10,2) NOT NULL DEFAULT 0,
    fecha_vencimiento       DATE,                        -- NULL = no perecedero (RF-21)
    dias_alerta_vencimiento INTEGER,                     -- NULL = usa default de la app (RF-22)
    activo                  BOOLEAN NOT NULL DEFAULT true,
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_item_inventario_codigo UNIQUE (sucursal_id, codigo_unico),
    CONSTRAINT ck_item_inventario_stock_no_negativo CHECK (stock_actual >= 0)
);
CREATE UNIQUE INDEX uq_item_inventario_nombre_sucursal
    ON item_inventario (sucursal_id, lower(btrim(nombre)));  -- RF-2
```
Cubre RF-1, RF-2, RF-3, RF-5, RF-7, RF-8, RF-9, RF-20, RF-21, RF-22.
`codigo_unico` (ADR 0002) y `stock_actual`/`stock_minimo`/`costo_unitario`
(ADR 0001, `NUMERIC`).

**Ejemplo de fila:**
```
id=1, codigo_unico='LAC-00001', nombre='Leche entera', unidad_medida='L',
categoria_id=3 (Lácteos), sucursal_id=1, stock_actual=12.500,
stock_minimo=5.000, costo_unitario=4200.00, fecha_vencimiento='2026-10-01',
dias_alerta_vencimiento=3, activo=true
```

### `item_inventario_historial` (RF-4, changelog)
```sql
CREATE TABLE item_inventario_historial (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_inventario_id  BIGINT NOT NULL REFERENCES item_inventario(id),
    campo               VARCHAR(50) NOT NULL,
    valor_anterior      TEXT,
    valor_nuevo         TEXT,
    usuario_id          BIGINT NOT NULL,  -- sin FK todavía: ver Decisión #4
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
Se llena automáticamente vía trigger (ver Algoritmos). Cubre RF-4.

### `movimiento_inventario` (kardex unificado — ENTRADA / SALIDA / AJUSTE)
```sql
CREATE TABLE movimiento_inventario (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_inventario_id  BIGINT NOT NULL REFERENCES item_inventario(id),
    tipo                VARCHAR(10) NOT NULL CHECK (tipo IN ('ENTRADA','SALIDA','AJUSTE')),
    cantidad_movimiento NUMERIC(12,3) CHECK (cantidad_movimiento > 0),  -- ENTRADA/SALIDA
    cantidad_objetivo   NUMERIC(12,3) CHECK (cantidad_objetivo >= 0),   -- solo AJUSTE
    stock_anterior      NUMERIC(12,3) NOT NULL,   -- lo calcula el trigger, no el cliente
    stock_nuevo         NUMERIC(12,3),            -- NULL mientras un ajuste espera aprobación
    motivo              VARCHAR(255),
    causa_perdida       VARCHAR(20) CHECK (causa_perdida IN ('DANIO','VENCIMIENTO','EXTRAVIO')),
    origen_perdida      VARCHAR(10) CHECK (origen_perdida IN ('MANUAL','AUTOMATICA')),
    compra_id           BIGINT,        -- sin FK todavía: ver Decisión #4
    requiere_aprobacion BOOLEAN NOT NULL DEFAULT false,
    aprobado_por        BIGINT,        -- sin FK todavía: ver Decisión #4
    aprobado_en         TIMESTAMPTZ,
    usuario_id          BIGINT NOT NULL,  -- sin FK todavía: ver Decisión #4
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_movimiento_tipo_cantidad CHECK (
        (tipo IN ('ENTRADA','SALIDA') AND cantidad_movimiento IS NOT NULL AND cantidad_objetivo IS NULL)
        OR
        (tipo = 'AJUSTE' AND cantidad_objetivo IS NOT NULL AND cantidad_movimiento IS NULL)
    ),
    CONSTRAINT ck_movimiento_ajuste_motivo CHECK (tipo <> 'AJUSTE' OR motivo IS NOT NULL),  -- RF-16
    CONSTRAINT ck_movimiento_perdida_es_salida CHECK (causa_perdida IS NULL OR tipo = 'SALIDA'),
    CONSTRAINT ck_movimiento_origen_requiere_causa CHECK (origen_perdida IS NULL OR causa_perdida IS NOT NULL)
);
```
Cubre RF-12 a RF-20, RF-24, RF-25, RF-26, RF-38.

**Ejemplo de fila (salida por pérdida automática de vencimiento):**
```
id=57, item_inventario_id=1, tipo='SALIDA', cantidad_movimiento=2.000,
stock_anterior=12.500, stock_nuevo=10.500, motivo='Vencido sin usar',
causa_perdida='VENCIMIENTO', origen_perdida='AUTOMATICA',
requiere_aprobacion=false, usuario_id=<usuario_sistema>
```

### `solicitud_reabastecimiento`
```sql
CREATE TABLE solicitud_reabastecimiento (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_inventario_id  BIGINT NOT NULL REFERENCES item_inventario(id),
    cantidad_sugerida   NUMERIC(12,3) NOT NULL,
    estado              VARCHAR(10) NOT NULL DEFAULT 'PENDIENTE'
                            CHECK (estado IN ('PENDIENTE','ENVIADA','ATENDIDA','CANCELADA')),
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_solicitud_reabastecimiento_pendiente
    ON solicitud_reabastecimiento (item_inventario_id) WHERE estado = 'PENDIENTE';
```
Cubre RF-28, RF-29, RF-36 (el índice único parcial hace RF-29/RF-36 atómico
de verdad, ver Decisión #8). `cantidad_sugerida = stock_minimo - stock_nuevo`
(lo que falta para llegar al mínimo) — no lo fija ningún RF, es un default
razonable, no una cifra de negocio confirmada.

**Dónde se dispara (agregado al implementar T10, el plan no lo detallaba):**
`fn_generar_solicitud_si_hace_falta()` se llama después de **cada** cambio
real de `stock_actual` — ENTRADA/SALIDA (T7), AJUSTE aplicado de inmediato
y AJUSTE aprobado (T8) — nunca desde un `SELECT` aparte de "¿bajó del
mínimo?": siempre justo después de la misma `UPDATE` que cambió el stock,
para no dejar una ventana entre "cambió el stock" y "se revisó el mínimo".
Intenta el `INSERT` directo y atrapa `unique_violation` si ya hay una
solicitud pendiente — nunca `SELECT` antes de `INSERT`, que sí tendría
condición de carrera (Decisión #8).

### Consultas derivadas (RF-10, RF-23, RF-27, RF-33, RF-34, RF-35)
El plan original solo decía "consulta sobre item_inventario, sin tabla
propia" — al implementar T11 se concretó como 2 vistas + 1 función:

```sql
CREATE VIEW vista_control_existencias AS
SELECT id, codigo_unico, nombre, sucursal_id, stock_actual, stock_minimo
FROM item_inventario
WHERE activo = true AND stock_minimo IS NOT NULL AND stock_actual < stock_minimo;

CREATE VIEW vista_proximos_a_vencer AS
SELECT id, codigo_unico, nombre, sucursal_id, fecha_vencimiento,
       COALESCE(dias_alerta_vencimiento, 7) AS dias_alerta_aplicado
FROM item_inventario
WHERE activo = true AND fecha_vencimiento IS NOT NULL
  AND fecha_vencimiento <= CURRENT_DATE + COALESCE(dias_alerta_vencimiento, 7);
```
`7` días es el mismo tipo de placeholder que el umbral de RF-17 (ADR
0001/0002 style: valor por defecto razonable, no cifra de negocio
confirmada) — RF-22 dice que el rango es configurable *por insumo*
(`dias_alerta_vencimiento`), así que el default solo aplica cuando ese
campo es `NULL`.

RF-27 (disponibilidad para una receta) necesita un parámetro variable
(lista de insumo+cantidad), así que es una **función**, no una vista:
```sql
fn_verificar_disponibilidad(items JSONB)
  RETURNS TABLE (item_inventario_id BIGINT, cantidad_requerida NUMERIC, disponible BOOLEAN)
```
`items` es un array JSON de `{"item_inventario_id":.., "cantidad_requerida":..}`.
`disponible` es `false` si el insumo está inactivo (RF-35) **o** si el
stock no alcanza — ambas condiciones en una sola expresión.

### Vista de reporte (RF-30, RF-32)
```sql
CREATE VIEW vista_reporte_inventario AS
SELECT i.id, i.codigo_unico, i.nombre, c.nombre AS categoria, i.activo,
       i.stock_actual, i.stock_minimo, i.fecha_vencimiento, i.sucursal_id,
       i.creado_en, i.actualizado_en
FROM item_inventario i
JOIN categoria_insumo c ON c.id = i.categoria_id;
```
**Corrección al implementar T12**: la definición original no traía ninguna
columna de fecha aparte de `fecha_vencimiento` (un dato de negocio, no del
reporte) — con eso, RF-30 ("filtrable... por rango de fechas") no tenía
sobre qué filtrar. Se agregaron `creado_en`/`actualizado_en`; el filtrado
por categoría/estado/fechas lo arma quien consulte la vista con `WHERE`,
la vista no impone los filtros.

La exportación a Excel/CSV/PDF (RF-31) es responsabilidad de la capa de
aplicación sobre esta vista — fuera de alcance del esquema (ya está en
"Fuera de alcance" de la spec).

## Algoritmos clave (pseudocódigo)

**Aplicar un movimiento (trigger `BEFORE INSERT` en `movimiento_inventario`)**
— resuelve RF-14, RF-17, RF-20, RF-25:
```
LOCK la fila de item_inventario (SELECT ... FOR UPDATE) por item_inventario_id
NEW.stock_anterior = stock_actual actual del insumo

SI tipo = 'ENTRADA':
    nuevo_stock = stock_anterior + cantidad_movimiento
SI tipo = 'SALIDA':
    nuevo_stock = stock_anterior - cantidad_movimiento
    # si nuevo_stock < 0, el CHECK de item_inventario lo rechaza (RF-14/RF-25)
SI tipo = 'AJUSTE':
    diferencia = abs(cantidad_objetivo - stock_anterior)
    SI diferencia > umbral_configurable:
        NEW.requiere_aprobacion = true
        NEW.stock_nuevo = NULL          # no se aplica todavía (RF-17)
        RETORNAR NEW                     # el UPDATE a item_inventario se hace al aprobar
    SINO:
        nuevo_stock = cantidad_objetivo

NEW.stock_nuevo = nuevo_stock
UPDATE item_inventario SET stock_actual = nuevo_stock, actualizado_en = now()
    WHERE id = NEW.item_inventario_id
RETORNAR NEW
```

**Aprobar un ajuste pendiente (trigger `BEFORE UPDATE` en
`movimiento_inventario`, cuando `aprobado_por` pasa de NULL a un valor)** —
resuelve RF-17:
```
SI OLD.aprobado_por IS NULL Y NEW.aprobado_por IS NOT NULL:
    UPDATE item_inventario SET stock_actual = NEW.cantidad_objetivo
        WHERE id = NEW.item_inventario_id
    NEW.stock_nuevo = NEW.cantidad_objetivo
    NEW.aprobado_en = now()
```
**Corrección al implementar T8**: el plan original decía `AFTER UPDATE`,
pero un trigger `AFTER` no puede modificar `NEW.stock_nuevo` de la propia
fila (`NEW` ya quedó escrito). Tiene que ser `BEFORE UPDATE`, igual que los
demás triggers de `item_inventario` que también mutan `NEW`.

**Umbral de aprobación (RF-17) — valor por defecto**: la spec lo dejaba
como duda abierta ("se define en el plan técnico"). Se implementó como
`SET app.umbral_ajuste_aprobacion = <valor>` (configurable por sesión,
mismo patrón que `app.usuario_actual`), con **20 unidades** como valor por
defecto si no se fija — un placeholder razonable, no una cifra de negocio
confirmada; Ronny/el Administrador pueden cambiarlo sin tocar el trigger.

**Registrar historial de cambios (trigger `BEFORE UPDATE` en `item_inventario`)**
— resuelve RF-4:
```
usuario_actual = current_setting('app.usuario_actual')  # la app hace
                 # SET LOCAL app.usuario_actual = <id> antes del UPDATE (Decisión #7)
PARA CADA campo en [nombre, descripcion, categoria_id, stock_minimo,
                     costo_unitario, fecha_vencimiento,
                     dias_alerta_vencimiento, activo]:
    SI OLD.campo <> NEW.campo:
        INSERT INTO item_inventario_historial
            (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
            VALUES (OLD.id, campo, OLD.campo::text, NEW.campo::text, usuario_actual)
```

**Impedir modificar el código único (trigger `BEFORE UPDATE` en `item_inventario`)**
— resuelve RF-37:
```
SI NEW.codigo_unico IS DISTINCT FROM OLD.codigo_unico:
    RAISE EXCEPTION 'codigo_unico es inmutable'
```

**Generar código único al crear un insumo (trigger `BEFORE INSERT` en
`item_inventario`)** — resuelve RF-1 (ver ADR 0002):
```
prefijo = primeras 3 letras en mayúsculas del nombre de categoria_id,
          sin tildes/ñ (ej. "Lácteos" -> "LAC", no "LÁC")
siguiente = MAX(secuencial ya usado con ese prefijo en esa sucursal) + 1
NEW.codigo_unico = prefijo || '-' || siguiente con padding a 5 dígitos
```
**Corrección detectada al implementar T4**: sin normalizar tildes, "Lácteos"
generaba el prefijo "LÁC" (con tilde), inconsistente con el ejemplo del
propio ADR 0002 ("LAC-00001"). Se agregó un `translate()` de vocales
acentuadas y ñ antes de tomar las 3 letras.

**Generar pérdidas automáticas por vencimiento (función `fn_generar_perdidas_vencimiento()`,
invocada periódicamente por la aplicación — programar esa periodicidad es
responsabilidad de la app, no de este esquema)** — resuelve RF-26, agregado
al implementar T9 (el plan no detallaba cuánto se pierde ni quién la llama):
```
PARA CADA insumo activo con fecha_vencimiento < hoy y stock_actual > 0:
    intentar registrar una SALIDA por el total del stock_actual restante,
    causa_perdida = 'VENCIMIENTO', origen_perdida = 'AUTOMATICA'
    SI ya existe una pérdida por vencimiento hoy para ese insumo (RF-38):
        omitir este insumo, seguir con el resto (no aborta el lote completo)
```
Se pierde el stock **completo** restante, no una cantidad parcial — "venció
sin usarse" se interpreta como que todo lo que quedaba ya no sirve.

**Evitar pérdida automática duplicada el mismo día (trigger `BEFORE INSERT`
en `movimiento_inventario`, solo si `causa_perdida = 'VENCIMIENTO'`)** —
resuelve RF-38:
```
SI existe ya un movimiento con el mismo item_inventario_id,
   causa_perdida = 'VENCIMIENTO' y creado_en::date = hoy:
    RAISE EXCEPTION 'ya existe una pérdida por vencimiento registrada hoy para este insumo'
```
**Orden de triggers, detectado al implementar T9**: Postgres corre los
triggers `BEFORE` del mismo evento en orden alfabético por nombre. Sin
intervenir, "aplicar" corría antes que "evitar_perdida_duplicada" (a < e) y
una pérdida duplicada fallaba con el `CHECK` de stock negativo en vez del
error específico de RF-38. Se renombraron con prefijo numérico
(`trg_movimiento_inventario_10_evitar_perdida_duplicada`,
`trg_movimiento_inventario_20_aplicar`) para fijar el orden a propósito.

**Rechazar una desactivación redundante (trigger `BEFORE UPDATE` en
`item_inventario`)** — resuelve RF-7 (no estaba detallado como pseudocódigo,
se agrega aquí al implementarlo en T3):
```
SI OLD.activo = false Y NEW.activo = false:
    RAISE EXCEPTION 'el insumo ya está inactivo'
```

## Decisiones técnicas

1. **Nombres de tabla propios en español** (`item_inventario`, no
   `inventario_iteminventario`) en vez del nombre por defecto de Django →
   el entregable de este frente son scripts SQL legibles para el curso, no
   algo atado a la convención interna de un ORM (constitución, principio 3:
   "el SQL manda, Django se ajusta a él").
2. **`NUMERIC(12,3)` / `NUMERIC(10,2)`** en vez de enteros → ADR 0001.
2b. **`codigo_unico` único compuesto con `sucursal_id`, no global** → el
    ADR 0002 numera el secuencial por sucursal a propósito; con un `UNIQUE`
    global, dos sucursales generando su primer insumo de una misma
    categoría producirían el mismo código y chocarían. Corregido al
    implementar T4 (bug del plan original, detectado antes de escribir el
    trigger).
3. **Kardex unificado** (`movimiento_inventario` con `tipo` ENTRADA/SALIDA/
   AJUSTE, y pérdida como SALIDA con `causa_perdida`) en vez de una tabla
   `perdida_inventario` separada → RF-18 pide "un kardex" (singular);
   separar pérdida rompería la trazabilidad centralizada del stock.
4. **`compra_id`, `sucursal_id`, `usuario_id` y `aprobado_por` sin
   `REFERENCES` todavía** → los módulos de Compras, Restaurantes y Cuentas
   no tienen su propia spec/plan en esta ronda (constitución, principio 4:
   una spec por módulo) — y se verificó en Neon (2026-09-23, solo lectura)
   que `restaurantes_sucursal` y `cuentas_usuario` **no existen todavía**,
   no es solo una cuestión de orden de specs. Se agregan las constraints
   con `ALTER TABLE ... ADD CONSTRAINT` cuando cada módulo tenga su propia
   spec. Alternativa descartada: crear ya tablas mínimas solo para las FK —
   descartada porque reinventaría sin spec módulos que no son de esta
   ronda, y porque esas tablas cambiarían de todos modos cuando esos
   módulos pasen por su propia constitución → spec → plan.
5. **Aprobación de ajustes como dos fases sobre la misma fila** (`INSERT`
   con `stock_nuevo = NULL` si excede el umbral, luego `UPDATE` de
   `aprobado_por` que sí aplica el cambio) en vez de bloquear el `INSERT`
   o usar una tabla de solicitudes aparte → RF-17 exige que el ajuste no se
   aplique hasta la aprobación; la fila ya tiene todos los campos
   necesarios, no hace falta una tabla extra.
6. **El trigger calcula `stock_anterior`/`stock_nuevo` con `SELECT ... FOR
   UPDATE`**, el cliente nunca los envía → si el cliente los calculara,
   dos transacciones concurrentes podrían perder una actualización
   (lost update), violando RF-20 ("incluso ante operaciones simultáneas").
7. **Variable de sesión (`SET LOCAL app.usuario_actual`) para que el
   trigger de historial sepa quién hizo el cambio** → un trigger no recibe
   el usuario de la aplicación directamente; la alternativa (guardar solo
   un `ultimo_editor_id` en `item_inventario`) no cumple RF-4 (changelog
   completo, no solo el último cambio).
8. **Índice único parcial** (`WHERE estado = 'PENDIENTE'`) para evitar
   solicitudes de reabastecimiento duplicadas, en vez de un chequeo
   `SELECT` + `INSERT` desde la aplicación → el índice es atómico ante
   concurrencia; un chequeo aplicativo tiene la condición de carrera que
   motivó RF-36 (caso límite L3 de la Fase 3).

## Cambios en código existente
Ninguno en esta ronda. `inventario/models.py` se actualizará en una tarea
futura (fuera de este plan) para reflejar `item_inventario`,
`categoria_insumo`, `movimiento_inventario`, etc. una vez el esquema esté
aplicado en Neon — así lo fija la constitución (principio 3: el SQL manda,
Django se ajusta después).

## Estrategia de tests
- **Contra la base de Neon de prueba** (constitución, principio 7): correr
  `sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql` sobre una base vacía y confirmar
  que no hay errores.
- **Por RF**, usando `psql` o un script de Python con `psycopg2`/`asyncpg`
  contra esa base de prueba: cada test inserta datos y verifica el
  resultado o el error esperado (ver tabla de Cobertura — cada RF apunta a
  qué tabla/trigger probar).
- **Triggers**: probar cada uno de forma aislada (insertar/actualizar filas
  mínimas y verificar el efecto — ej. intentar un `UPDATE` de
  `codigo_unico` y confirmar que lanza la excepción de RF-37).
- **Concurrencia** (RF-20, RF-36): dos conexiones simultáneas a la base de
  prueba, cada una intentando la misma operación al mismo tiempo,
  verificando que el resultado final es correcto y ninguna deja datos
  inconsistentes.
- Sin mocks de base de datos: al ser un frente de esquema, los tests
  necesitan una base Postgres real (de prueba), no SQLite ni dobles.

## Cobertura
| RF | Tabla / mecanismo |
|---|---|
| RF-1 | `item_inventario.codigo_unico` + trigger de generación (ADR 0002) |
| RF-2 | Índice único `uq_item_inventario_nombre_sucursal` |
| RF-3 | `categoria_insumo` + `item_inventario.categoria_id` |
| RF-4 | `item_inventario_historial` + trigger de historial |
| RF-5, RF-7 | `item_inventario.activo` |
| RF-6 | Consulta de aplicación contra Compras (fuera de este esquema — Decisión #4) |
| RF-8 | Consulta sobre `item_inventario` |
| RF-9, RF-11 | `item_inventario.stock_minimo` (nullable) |
| RF-10, RF-33 | Consulta sobre `item_inventario` filtrando `activo` |
| RF-12 a RF-16, RF-18, RF-19 | `movimiento_inventario` |
| RF-17 | `movimiento_inventario.requiere_aprobacion/aprobado_por` + trigger de aplicación en 2 fases |
| RF-20 | `CHECK` en `item_inventario.stock_actual` + trigger con `FOR UPDATE` |
| RF-21, RF-22, RF-23, RF-34 | `item_inventario.fecha_vencimiento/dias_alerta_vencimiento` (consulta) |
| RF-24, RF-25 | `movimiento_inventario` (tipo SALIDA, causa_perdida) |
| RF-26, RF-38 | Trigger de pérdida automática + chequeo de duplicado |
| RF-27 | Consulta sobre `item_inventario`, sin tabla propia |
| RF-28, RF-29, RF-36 | `solicitud_reabastecimiento` + índice único parcial |
| RF-30, RF-32 | `vista_reporte_inventario` |
| RF-31 | Fuera del esquema — capa de aplicación |
| RF-35 | Consulta sobre `item_inventario.activo` |
| RF-37 | Trigger de inmutabilidad de `codigo_unico` |
