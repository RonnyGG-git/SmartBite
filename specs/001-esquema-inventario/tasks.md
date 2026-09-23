# Tareas — Spec 001 (Esquema de datos de Inventario)

> Estado: aprobada 2026-09-23

Cada tarea: tests primero contra una base Postgres real de prueba (ver
plan.md, "Estrategia de tests" — sin mocks de base de datos). Se marca
`- [x]` solo cuando su "Hecho cuando:" se cumple; cualquier verificación
extra se anota debajo en **negrita**.

- [x] T1. Esqueleto: carpetas `sql/TABLAS/` y `sql/INSERTS/`; script de
      tests en Python (`pytest` + `psycopg2`) que lee la conexión de
      `DATABASE_URL_TEST` (variable de entorno, no committeada). (RF: —)
      Hecho cuando: `pytest` corre con 0 tests sin errores, y un test
      trivial (`SELECT 1`) contra `DATABASE_URL_TEST` pasa.
      **Se creó vía API la rama de desarrollo `test-inventario-jose` en el
      proyecto de Neon del equipo (`holy-mouse-44756464`), separada de
      `production` — la conexión se guarda solo en `sql/tests/.env.test`
      (gitignored, `conftest.py` la carga sola). 1 test, en verde.**

- [x] T2. Tabla `categoria_insumo`. (RF-3)
      Hecho cuando: tests en verde para crear una categoría, y rechazar un
      nombre duplicado.
      **Se agregó el fixture `esquema` (sesión) que recrea el esquema desde
      cero aplicando `sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql` en cada corrida
      de tests, y `conn` ahora depende de él. Verificado con
      `information_schema` que la tabla y la constraint existen tal como
      las diseña el plan.**

- [x] T3. Tabla `item_inventario`: columnas, FK a `categoria_insumo`,
      índice único de nombre por sucursal, `CHECK` de stock no negativo,
      trigger de RF-7. (RF-2, RF-3, RF-5, RF-6, RF-7, RF-8, RF-9, RF-11,
      RF-20, RF-21, RF-22)
      Hecho cuando: tests en verde para crear un insumo válido; rechazar
      nombre duplicado en la misma sucursal (ignorando mayúsculas/espacios);
      rechazar `stock_actual` negativo; desactivar y re-desactivar (RF-7);
      consultar filtrando por nombre/categoría/estado/sucursal (RF-8).
      **Se descubrió que `restaurantes_sucursal` no existe en Neon
      (verificado en `production`, solo lectura) — se corrigió el plan
      (Decisión #4 ampliada) para que `sucursal_id`, y de paso `usuario_id`/
      `aprobado_por` de `movimiento_inventario`, queden sin FK por ahora,
      igual que `compra_id`. Se agregó también el trigger de RF-7
      (`fn_item_inventario_validar_desactivacion`), no detallado antes en
      el plan — documentado ahí ahora. 10 tests en verde; verificado con
      `information_schema`/`pg_constraint`/`pg_trigger` que la tabla, la FK,
      el índice y el trigger existen tal como se diseñaron.**
      **RF-6 (bloquear baja si hay compra pendiente) sigue pendiente de
      verdad: la tabla `compra` no existe — se agrega cuando exista la spec
      de Compras.**

- [x] T4. Trigger de generación de código único (ADR 0002) + trigger de
      inmutabilidad. (RF-1, RF-37)
      Hecho cuando: tests en verde — insertar dos insumos de la misma
      categoría/sucursal genera códigos consecutivos con el prefijo
      correcto; intentar `UPDATE` de `codigo_unico` lanza la excepción
      esperada.
      **Dos bugs reales encontrados y corregidos antes de cerrar la tarea:
      (1) el plan tenía `UNIQUE (codigo_unico)` global, pero el ADR 0002
      numera por sucursal — dos sucursales generando su primer insumo de
      una categoría habrían chocado; se corrigió a
      `UNIQUE (sucursal_id, codigo_unico)`. (2) el prefijo no normalizaba
      tildes/ñ: "Lácteos" generaba "LÁC-00001" en vez de "LAC-00001" (el
      propio ejemplo del ADR). Se agregó `translate()` de vocales
      acentuadas y ñ. 15 tests en verde (5 nuevos); verificado con una
      inserción real fuera de los tests ("Panadería" → `PAN-00001`) y con
      `pg_trigger` que los 3 triggers de la tabla existen.**

- [x] T5. Tabla `item_inventario_historial` + trigger de historial en
      `item_inventario`. (RF-4)
      Hecho cuando: test en verde — actualizar dos campos de un insumo crea
      dos filas de historial con valor anterior/nuevo y el usuario correcto
      (vía `SET LOCAL app.usuario_actual`).
      **El trigger es `AFTER UPDATE` (no `BEFORE`), a propósito: así el
      historial solo se registra si la actualización pasó los triggers
      `BEFORE` de RF-7/RF-37 (si esos rechazan el `UPDATE`, no queda un
      registro de historial de algo que no pasó). Regresión real detectada
      al correr la suite completa: los tests de T3/T4 que actualizaban
      `activo`/`descripcion` sin fijar `app.usuario_actual` empezaron a
      fallar (`NotNullViolation`) — es el comportamiento correcto (lo exige
      el propio test nuevo de "sin usuario falla claro"), así que se
      corrigieron esos 3 tests agregando `SET LOCAL`, no el trigger.
      3 tests nuevos + 18 en verde en total. Verificado con
      `information_schema`/`pg_trigger`.**

- [x] T6. Tabla `movimiento_inventario` (DDL y `CHECK`s, sin el trigger de
      aplicación todavía). (RF-15, RF-16, RF-18, RF-19)
      Hecho cuando: tests en verde — insertar una fila válida de cada tipo
      (ENTRADA, SALIDA, AJUSTE); rechazar un AJUSTE sin motivo (RF-16);
      consultar movimientos filtrando por insumo/tipo/fecha (RF-19).
      **`stock_anterior`/`stock_nuevo` se pasan a mano en los tests de esta
      tarea (todavía no hay trigger que los calcule, eso es T7). Se
      agregaron 2 tests extra para `ck_movimiento_tipo_cantidad` (rechaza
      ENTRADA sin `cantidad_movimiento`, y AJUSTE con `cantidad_movimiento`
      puesto). Bug propio de test encontrado y corregido (no del esquema):
      dos insumos creados con la categoría por defecto colisionaban por el
      nombre único. 7 tests nuevos, 25 en total en verde; verificado con
      `information_schema`/`pg_constraint` que la tabla, la FK y los 4
      `CHECK` nombrados existen.**

- [x] T7. Trigger `BEFORE INSERT` que aplica el movimiento sobre
      `item_inventario.stock_actual` con `SELECT ... FOR UPDATE`. (RF-12,
      RF-13, RF-14, RF-20)
      Hecho cuando: tests en verde — una ENTRADA incrementa el stock (con y
      sin `compra_id`, cubriendo el stock inicial); una SALIDA lo
      descuenta; una SALIDA que excede el stock disponible se rechaza; dos
      SALIDAs concurrentes sobre el mismo insumo nunca dejan el stock
      negativo (test de concurrencia con dos conexiones).
      **A propósito, el trigger solo actúa sobre ENTRADA/SALIDA — AJUSTE
      pasa sin tocar (el umbral de aprobación es T8, no se adelantó).
      Regresión real detectada al correr la suite completa: 2 tests de T6
      simulaban SALIDA con `stock_anterior` inventado sobre un insumo con
      stock real 0 — ahora que el trigger calcula el stock de verdad,
      quedaban en negativo y violaban el `CHECK`. Se corrigieron agregando
      una ENTRADA real antes de la SALIDA en esos tests, no se tocó el
      trigger. El test de concurrencia usa dos conexiones psycopg2 propias
      en hilos separados (no la fixture `cursor`, que es de una sola
      conexión) — corrido 3 veces seguidas sin fallos para descartar
      flakiness. 6 tests nuevos, 31 en total en verde; verificado con
      `pg_trigger` que el trigger existe.**

- [x] T8. Trigger de aprobación de ajustes en dos fases (umbral
      configurable). (RF-17)
      Hecho cuando: tests en verde — un ajuste por debajo del umbral se
      aplica de inmediato; uno por encima queda con `stock_nuevo = NULL` y
      `requiere_aprobacion = true` sin tocar el stock; al aprobar
      (`aprobado_por`), el stock se actualiza recién ahí.
      **Dos correcciones al plan, hechas antes de cerrar la tarea: (1) el
      trigger de aprobación tiene que ser `BEFORE UPDATE`, no `AFTER` como
      decía el plan — un `AFTER` no puede modificar `NEW.stock_nuevo` de su
      propia fila. (2) la spec dejaba el valor del umbral como duda
      abierta ("se define en el plan técnico"); se implementó como
      `SET app.umbral_ajuste_aprobacion` (mismo patrón que
      `app.usuario_actual`), con **20 unidades** de default — placeholder
      explícito, no una cifra de negocio confirmada. Test extra que prueba
      que el umbral es configurable de verdad (bajarlo a 5 por sesión
      cambia el resultado). Sin regresiones al correr la suite completa
      esta vez. 4 tests nuevos, 35 en total en verde; verificado con
      `pg_trigger` que ambos triggers de `movimiento_inventario` existen.**

- [x] T9. Pérdidas (`causa_perdida`/`origen_perdida`) + trigger de pérdida
      automática por vencimiento + chequeo de duplicado. (RF-24, RF-25,
      RF-26, RF-38)
      Hecho cuando: tests en verde — registrar una pérdida manual descuenta
      el stock; una pérdida que excede el stock disponible se rechaza; un
      insumo vencido sin usar genera automáticamente una pérdida; una
      segunda pérdida manual por vencimiento el mismo día para el mismo
      insumo se rechaza.
      **RF-24/25 (pérdida manual) no necesitaron trigger nuevo — una
      pérdida es una SALIDA con `causa_perdida` puesta, ya cubierta por el
      trigger de T7. Se agregó `fn_generar_perdidas_vencimiento()` (función
      invocable, no trigger — no hay evento de "pasó un día" que dispare
      algo solo; programar cuándo llamarla es de la app, no de este
      esquema) y el trigger de RF-38. **Bug de orden de triggers encontrado
      y corregido antes de cerrar la tarea**: Postgres corre los `BEFORE`
      en orden alfabético, y "aplicar" corría antes que
      "evitar_perdida_duplicada" — una pérdida duplicada fallaba con
      "stock insuficiente" en vez del error de RF-38. Renombrados con
      prefijo numérico (`_10_evitar...`, `_20_aplicar`) para fijar el
      orden. Bug propio de test (categoría duplicada) corregido, no del
      esquema. 7 tests nuevos, 42 en total en verde; verificado con
      `pg_trigger` el orden real y con `pg_proc` que la función existe.**

- [x] T10. Tabla `solicitud_reabastecimiento` + índice único parcial. (RF-28,
      RF-29, RF-36)
      Hecho cuando: tests en verde — un insumo bajo mínimo genera una
      solicitud; una segunda solicitud para el mismo insumo mientras la
      primera sigue `PENDIENTE` se rechaza; dos intentos concurrentes de
      generar la solicitud producen una sola fila (test de concurrencia).
      **El plan no detallaba dónde se disparaba RF-28: se agregó la llamada
      a `fn_generar_solicitud_si_hace_falta()` justo después de cada
      `UPDATE` real de `stock_actual` (ENTRADA/SALIDA de T7, AJUSTE
      inmediato y AJUSTE aprobado de T8) — nunca un `SELECT` aparte, para
      no dejar ventana entre "cambió el stock" y "se revisó el mínimo". La
      función intenta el `INSERT` directo y atrapa `unique_violation` si ya
      hay una pendiente, en vez de `SELECT`-antes-de-`INSERT` (que sí
      tendría condición de carrera). Se verificó que las funciones pueden
      referenciar código definido más abajo en el mismo script sin
      problema (PL/pgSQL no valida existencia hasta que se ejecuta). Test
      de concurrencia corrido 3 veces sin fallos. 6 tests nuevos, 48 en
      total en verde; verificado con `pg_indexes` que el índice único
      parcial existe.**

- [x] T11. Consultas derivadas: control de existencias, próximos a vencer,
      disponibilidad para Menú, exclusión de insumos inactivos. (RF-10,
      RF-23, RF-27, RF-33, RF-34, RF-35)
      Hecho cuando: tests en verde para cada consulta, incluyendo que un
      insumo inactivo nunca aparece en ninguna de las tres.
      **El plan solo decía "consulta, sin tabla propia" — se concretó como
      2 vistas (`vista_control_existencias`, `vista_proximos_a_vencer`) y
      1 función (`fn_verificar_disponibilidad`, porque RF-27 necesita un
      parámetro variable — una lista de pares insumo-cantidad — que una
      vista no puede recibir). El default de 7 días para el rango de
      alerta cuando `dias_alerta_vencimiento` es `NULL` tampoco estaba
      fijado; documentado como placeholder, mismo criterio que el umbral
      de RF-17. Tests de fecha evitan depender de "hoy": usan rangos de
      alerta enormes o `CURRENT_DATE` calculado en SQL, no fechas
      hardcodeadas. 12 tests nuevos, 60 en total en verde; verificado con
      `information_schema.views`/`pg_proc` que existen.**

- [x] T12. Vista `vista_reporte_inventario`. (RF-30, RF-32)
      Hecho cuando: test en verde — filtrar por categoría/estado/fechas
      devuelve lo esperado; sin coincidencias devuelve vacío (la app
      interpreta esto como "sin datos", RF-32).
      **RF-31 (exportar a Excel/CSV/PDF) es explícitamente fuera de alcance
      del esquema (spec, "Fuera de alcance") — no tiene tarea de SQL.**
      **Bug de diseño encontrado antes de escribir el primer test**: la
      vista del plan no tenía ninguna columna de fecha aparte de
      `fecha_vencimiento` (un dato de negocio, no de auditoría) — RF-30
      pide filtrar "por rango de fechas" y no había sobre qué. Se
      agregaron `creado_en`/`actualizado_en`. El filtro de categoría/
      estado/fechas lo arma quien consulta con `WHERE`, la vista no lo
      impone. 4 tests nuevos, 64 en total en verde; verificado con
      `information_schema.columns` que la vista tiene las columnas
      correctas.

- [x] T13. `sql/INSERTS/SMARTBITE_INVENTARIO_SP.sql`: datos semilla
      (categorías base de ejemplo). (Soporte)
      Hecho cuando: el script corre limpio sobre la base de prueba después
      de T2-T12, sin violar ninguna constraint.
      **8 categorías genéricas (Lácteos, Cárnicos, Panadería, Bebidas,
      Frutas y Verduras, Abarrotes, Limpieza, Desechables) — nada de
      insumos ficticios, porque un insumo real necesita una sucursal real
      que este esquema todavía no tiene (Decisión #4). `ON CONFLICT (nombre)
      DO NOTHING` para que sea seguro re-ejecutarlo. Bug propio de test
      corregido (no del script): la aserción de idempotencia comparaba
      contra un conteo total fijo, pero los tests de concurrencia de T7/T10
      usan `autocommit=True` y dejan categorías propias committeadas de
      verdad en la sesión — se corrigió a comparar antes/después, no contra
      un número fijo. 2 tests nuevos, 66 en total en verde; verificado
      además con una corrida real y doble (`TABLAS` + `INSERTS` × 2) fuera
      de cualquier transacción de test, sobre un schema recién dropeado.**

- [x] T14. Validación final: recorrer la spec RF por RF en `validacion.md`.
      (Todos)
      Hecho cuando: cada uno de los 38 RF tiene una prueba directa
      identificada (o está marcado explícitamente como fuera de alcance,
      como RF-6 parcial y RF-31) y el veredicto es "spec cumplida".
      **Siguiendo la propia fase 7 (la cobertura indirecta no cuenta): se
      encontraron 5 RF (RF-3, RF-8 nombre, RF-9, RF-10 alcance por
      sucursal, RF-18) probados solo de paso por otros tests, no de forma
      directa. Se agregaron 5 tests nuevos (71 en total) antes de cerrar la
      validación. Veredicto en `validacion.md`: spec cumplida a nivel de
      esquema SQL (36/38 RF, con RF-6 y RF-31 como exclusiones explícitas,
      no huecos) — pero el tercer criterio de finalización de la spec
      ("`models.py` alineados con Neon") **no** se hizo, porque ninguna
      tarea T1-T14 lo incluyó. Queda como trabajo pendiente explícito, no
      escondido.**
