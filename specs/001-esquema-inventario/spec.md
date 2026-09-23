# Spec 001 — Esquema de datos de Inventario

> Estado: aprobada 2026-09-23

## Contexto y objetivo
Smart Bite necesita un módulo de Inventario que permita al Jefe de Almacén
mantener el catálogo de insumos, controlar existencias con trazabilidad
completa (kardex), gestionar vencimientos y pérdidas, y coordinarse con
Compras (reabastecimiento) y Menú (disponibilidad de platillos). Esta spec
formaliza los 17 casos de uso ya documentados por el equipo
(`CU-INV-01..17`) como requisitos verificables, para que de ahí salga el
esquema de base de datos (SQL puro, desplegado en Neon) en la Fase 4.

## Usuarios / actores
- **Jefe de Almacén**: actor principal, gestiona insumos, movimientos,
  vencimientos y pérdidas.
- **Administrador**: aprueba ajustes por encima del umbral configurado;
  consume reportes.
- **Módulo de Compras** (system): dispara entradas de inventario al recibir
  una compra verificada; recibe solicitudes de reabastecimiento.
- **Módulo de Menú** (system): consulta disponibilidad de stock para marcar
  platillos como disponibles/no disponibles.

## Historias de usuario
- H1: Como Jefe de Almacén, quiero registrar, consultar, actualizar,
  clasificar y desactivar insumos, para mantener el catálogo de inventario
  al día.
- H2: Como Jefe de Almacén, quiero que el sistema identifique los insumos
  con stock por debajo del mínimo, para saber qué reabastecer.
- H3: Como Jefe de Almacén, quiero registrar entradas, salidas y ajustes de
  inventario con trazabilidad completa, para que el stock refleje la
  realidad y pueda auditarse.
- H4: Como Jefe de Almacén, quiero que el sistema controle vencimientos y
  permita registrar pérdidas, para reducir la merma.
- H5: Como Módulo de Compras y Módulo de Menú, necesitamos consultar y
  disparar acciones sobre el inventario, para coordinar reabastecimiento y
  disponibilidad de platillos.
- H6: Como Jefe de Almacén o Administrador, quiero generar reportes de
  inventario exportables, para tomar decisiones y rendir cuentas.

## Requisitos funcionales (criterios de aceptación en EARS)

### Gestión de insumos (H1)
- RF-1: EL SISTEMA asignará un código único a cada insumo registrado.
- RF-2: SI el nombre de un insumo ya existe para la misma sucursal
  (ignorando mayúsculas y espacios exteriores), ENTONCES EL SISTEMA no
  creará un duplicado y sugerirá actualizar el existente.
- RF-3: EL SISTEMA exigirá una categoría de insumo al registrar un insumo
  nuevo, permitiendo crear la categoría en el momento si no existe.
- RF-4: CUANDO se actualicen los datos de un insumo, EL SISTEMA registrará
  un historial con los valores anteriores y nuevos de cada campo
  modificado, junto con fecha, hora y usuario responsable.
- RF-5: EL SISTEMA permitirá desactivar un insumo (baja lógica) sin
  eliminar su registro ni su historial.
- RF-6: SI un insumo tiene una orden de compra en estado pendiente que lo
  incluye, ENTONCES EL SISTEMA no permitirá su desactivación (el historial
  de movimientos pasados no bloquea la baja; este dato depende de que el
  Módulo de Compras lo exponga — se resuelve en su propia spec).
- RF-7: SI un insumo ya está inactivo, ENTONCES EL SISTEMA no permitirá
  volver a desactivarlo e informará el estado actual.
- RF-8: EL SISTEMA permitirá consultar insumos filtrando por nombre,
  categoría, estado y sucursal.
- RF-37: EL SISTEMA no permitirá modificar el código único de un insumo una
  vez asignado.

### Control de existencias (H2)
- RF-9: EL SISTEMA permitirá configurar un nivel de stock mínimo por
  insumo.
- RF-10: CUANDO se ejecute el control de existencias, EL SISTEMA
  identificará todos los insumos de una sucursal cuyo stock actual esté
  por debajo de su nivel mínimo configurado.
- RF-11: SI un insumo no tiene nivel mínimo configurado, ENTONCES EL
  SISTEMA lo excluirá del control de existencias y lo señalará como no
  configurado.
- RF-33: EL SISTEMA excluirá los insumos inactivos del control de
  existencias.

### Movimientos de inventario (H3)
- RF-12: CUANDO se registre una entrada de inventario, EL SISTEMA
  incrementará el stock del insumo y generará un movimiento de tipo
  ENTRADA, trazado a la compra que la originó cuando exista (el stock
  inicial de un insumo nuevo genera una ENTRADA sin compra asociada).
- RF-13: CUANDO se registre una salida de inventario, EL SISTEMA
  descontará el stock del insumo y generará un movimiento de tipo SALIDA.
- RF-14: SI la cantidad de salida solicitada supera el stock disponible,
  ENTONCES EL SISTEMA rechazará la operación e informará el stock
  insuficiente.
- RF-15: CUANDO se registre un ajuste de inventario, EL SISTEMA exigirá un
  motivo y actualizará el stock del insumo a la cantidad indicada.
- RF-16: SI no se indica un motivo, ENTONCES EL SISTEMA no permitirá
  continuar con el ajuste.
- RF-17: SI la diferencia entre el stock anterior y el nuevo en un ajuste
  supera un umbral configurable, ENTONCES EL SISTEMA requerirá la
  aprobación del Administrador antes de aplicarlo.
- RF-18: EL SISTEMA registrará todo movimiento (entrada, salida o ajuste)
  en un kardex trazable, con fecha, hora, usuario responsable, insumo, tipo
  y cantidad.
- RF-19: EL SISTEMA permitirá consultar el historial de movimientos
  filtrando por insumo, tipo de movimiento y rango de fechas.
- RF-20: EL SISTEMA garantizará que el stock de un insumo nunca quede en un
  valor negativo, incluso ante operaciones simultáneas sobre el mismo
  insumo.

### Vencimientos y pérdidas (H4)
- RF-21: DONDE un insumo tenga fecha de vencimiento registrada, EL SISTEMA
  lo incluirá en el control de productos próximos a vencer.
- RF-22: EL SISTEMA permitirá configurar un rango de días de alerta previo
  al vencimiento.
- RF-23: CUANDO un insumo con fecha de vencimiento entre en el rango de
  alerta configurado, EL SISTEMA lo incluirá en el listado de productos
  próximos a vencer.
- RF-34: EL SISTEMA excluirá los insumos inactivos del control de
  productos próximos a vencer.
- RF-24: EL SISTEMA permitirá registrar la pérdida de un insumo (daño,
  vencimiento o extravío) descontando el stock correspondiente.
- RF-25: SI la cantidad de pérdida reportada excede el stock disponible,
  ENTONCES EL SISTEMA rechazará el registro.
- RF-26: CUANDO un insumo con fecha de vencimiento supere esa fecha sin
  haberse usado, EL SISTEMA generará automáticamente un registro de
  pérdida por vencimiento.
- RF-38: SI ya existe un registro de pérdida automática por vencimiento sin
  resolver para un insumo, ENTONCES EL SISTEMA no permitirá registrar una
  pérdida manual adicional por la misma causa para ese insumo.

### Integración con Compras y Menú (H5)
- RF-27: EL SISTEMA permitirá consultar, para una lista de pares
  insumo-cantidad requerida (por ejemplo, los ingredientes de una receta),
  si hay stock suficiente de cada uno.
- RF-28: CUANDO un insumo quede por debajo de su nivel mínimo y no tenga ya
  una solicitud de reabastecimiento pendiente, EL SISTEMA generará una
  solicitud de reabastecimiento dirigida al Módulo de Compras.
- RF-29: SI ya existe una solicitud de reabastecimiento pendiente para un
  insumo, ENTONCES EL SISTEMA no generará una nueva.
- RF-35: SI un insumo está inactivo, ENTONCES EL SISTEMA lo reportará como
  no disponible ante una consulta de stock del Módulo de Menú.
- RF-36: EL SISTEMA garantizará que la verificación de una solicitud de
  reabastecimiento pendiente (RF-29) y la creación de una nueva sean
  atómicas, para evitar solicitudes duplicadas ante controles de
  existencias simultáneos.

### Reportes (H6)
- RF-30: EL SISTEMA permitirá generar un reporte de inventario filtrable
  por categoría, estado y rango de fechas.
- RF-31: EL SISTEMA soportará la exportación del reporte de inventario en
  formatos Excel, CSV y PDF.
- RF-32: SI no hay insumos que coincidan con los filtros del reporte,
  ENTONCES EL SISTEMA informará que no hay datos para generar el reporte.

## Requisitos no funcionales
- Trazabilidad: todo movimiento de stock (entrada, salida, ajuste, pérdida)
  queda auditado con usuario y fecha/hora responsables, sin excepción.
- Idioma: identificadores y mensajes en español, igual que el resto del
  proyecto (constitución, principio 5).
- El umbral de aprobación de ajustes (RF-17) y el rango de días de alerta
  de vencimiento (RF-22) son valores configurables, no fijos en el sistema.
- RF-17 y RF-26 se resuelven en el plan técnico como estructura de datos
  (p. ej., un estado del movimiento que una vista puede consultar), nunca
  como lógica de aplicación — coherente con el principio 1 de la
  constitución.

## Casos límite
- Registrar un insumo con nombre duplicado en la misma sucursal (RF-2).
- Dos salidas simultáneas sobre el mismo insumo que en conjunto excedan el
  stock disponible (RF-20: ninguna debe dejar el stock negativo).
- Ajuste que deja el stock exactamente en el nivel mínimo configurado.
- Insumo sin categoría al momento de migrar datos existentes (no debería
  ocurrir tras RF-3, pero se contempla en el plan técnico).
- Registrar una fecha de vencimiento ya pasada al crear el insumo.
- Insumo con una compra pendiente que lo incluye al intentar desactivarlo
  (RF-6).
- Reporte solicitado sin insumos que coincidan con los filtros (RF-32).

## Fuera de alcance
- El flujo completo de Compras (aprobación de órdenes, proveedores,
  devoluciones) — se especifica en su propia ronda SDD.
- La disponibilidad de platillos en el menú público y su presentación —
  Módulo de Menú, otra ronda.
- Permisos de UI y vistas (qué botón ve cada rol) — responsabilidad de
  quien implemente la lógica de aplicación de este módulo, no de este
  esquema de datos.
- El mecanismo técnico real de exportación a Excel/CSV/PDF (RF-31) — se
  decide en el plan técnico.
- Facturación electrónica, pagos, autoservicio de cliente y gestión de
  empleados (RR. HH.) — confirmado fuera de alcance en
  `docs/constitution.md`, principio 2.
- Valores por defecto concretos del umbral de aprobación (RF-17) y del
  rango de días de alerta (RF-22) — se definen en el plan técnico.
- Reactivar un insumo previamente desactivado — ningún caso de uso
  original lo contempla; si se necesita, se resuelve como cambio en una
  ronda futura (Fase 8).

## Criterios de finalización
- Cada RF tiene una prueba directa que lo verifica (se define en `tasks.md`
  de la Fase 5).
- El script SQL resultante (Fase 4) corre limpio contra una base Neon de
  prueba y soporta insertar/consultar/actualizar datos cumpliendo cada RF.
- Los `models.py` de Django que correspondan quedan alineados con el
  esquema aplicado en Neon.

## Dudas abiertas
- [NECESITA ACLARACIÓN: si una devolución a proveedor (que gestionará la
  spec de Compras) debe generar un motivo específico de salida en el
  kardex de Inventario, o si Compras solo dispara una salida genérica
  (RF-13). Se puede resolver al especificar Compras sin bloquear esta
  spec.]
- [NECESITA ACLARACIÓN: valores por defecto del umbral de aprobación
  (RF-17) y del rango de días de alerta de vencimiento (RF-22) — quedan
  como parámetros configurables; el valor concreto lo define Ronny/el
  Administrador o se fija en el plan técnico si no hay respuesta.]
