# Tareas: Flujo de Ordenes MVP

## Fase 1: Cambios en modelos (sin dependencias entre si)

- [x] **T1.1 — Diccionario de transiciones y metodo `puede_cambiar_a` en `Orden`**
  Revisar `operativo/models.py`. Agregar constante `TRANSICIONES_VALIDAS` (dict que mapea cada estado a sus estados destino permitidos) y metodo `puede_cambiar_a(estado_destino)` en el modelo `Orden`. El metodo retorna `True` si `estado_destino` esta en `TRANSICIONES_VALIDAS[self.estado]`.
  RF: RF-003 | Hallazgo: H1
  Hecho cuando: `Orden.PENDIENTE.puede_cambiar_a(Orden.EN_PREPARACION)` retorna `True` y `Orden.CANCELADA.puede_cambiar_a(Orden.LISTA)` retorna `False`.

- [x] **T1.2 — Agregar `unique_together` a `Cliente`**
  Revisar `operativo/models.py`. Agregar `unique_together = [("nombre", "telefono", "email")]` en `Meta` de `Cliente`. Ejecutar `makemigrations` y `migrate`.
  RF: — | Hallazgo: H10
  Hecho cuando: Crear dos `Cliente` con mismo nombre, telefono y email lanza `IntegrityError`.

- [x] **T1.3 — Cambiar herencia de `DetalleOrden` a `TimestampedModel`**
  Revisar `operativo/models.py`. Cambiar `DetalleOrden` para que herede de `TimestampedModel` en lugar de `models.Model`. Ejecutar `makemigrations` y `migrate`.
  RF: — | Hallazgo: G10
  Hecho cuando: `DetalleOrden` tiene campos `creado_en` y `actualizado_en` disponibles.

---

## Fase 2: Cambios en formularios (depende de T1.1)

- [x] **T2.1 — Filtrar choices de estado en `CambiarEstadoOrdenForm`**
  Revisar `operativo/forms.py`. Modificar `CambiarEstadoOrdenForm` para que acepte una instancia de `Orden` (o su estado actual) y filtre el `ChoiceField` de estado usando `Orden.TRANSICIONES_VALIDAS[estado_actual]`. Los estados no permitidos no deben aparecer como opciones.
  RF: RF-003 | Hallazgo: H1
  Hecho cuando: Para una orden en estado `PENDIENTE`, el formulario solo muestra `EN_PREPARACION` y `CANCELADA` como opciones.

---

## Fase 3: Proteccion de vistas — autenticacion y roles (sin dependencias entre si)

- [x] **T3.1 — Proteger `generar_qr` con autenticacion**
  Revisar `operativo/views.py`. Agregar decorador `@rol_requerido("ADMINISTRADOR", "MESERO")` a la vista `generar_qr`.
  RF: RF-009 | Hallazgo: H3
  Hecho cuando: Un usuario sin sesion que accede a `/operativo/mesas/qr/<id>/` es redirigido al login.

- [x] **T3.2 — Proteger `crear_cliente_rapido` con autenticacion**
  Revisar `operativo/views.py`. Agregar decorador `@rol_requerido("ADMINISTRADOR", "MESERO")` a la vista `crear_cliente_rapido`. Reemplazar redirect via `HTTP_REFERER` por un redirect fijo a `operativo:crear_orden`.
  RF: RF-009 | Hallazgo: H4
  Hecho cuando: Un usuario sin sesion que hace POST a `/operativo/ordenes/clientes/nuevo/` recibe 302 al login, y el redirect despues del POST apunta a una URL fija.

- [x] **T3.3 — Proteger `agregar_producto` con autenticacion**
  Revisar `operativo/views.py`. Agregar decorador `@rol_requerido("ADMINISTRADOR", "MESERO")` a la vista `agregar_producto`.
  RF: RF-009
  Hecho cuando: Un usuario sin sesion que hace POST a `/operativo/ordenes/<pk>/productos/` recibe 302 al login.

- [x] **T3.4 — Proteger `cambiar_estado_orden` con autenticacion**
  Revisar `operativo/views.py`. Agregar decorador `@rol_requerido("ADMINISTRADOR", "MESERO")` a la vista `cambiar_estado_orden`.
  RF: RF-009
  Hecho cuando: Un usuario sin sesion que hace POST a `/operativo/ordenes/<pk>/estado/` recibe 302 al login.

---

## Fase 4: Logica de negocio en vistas (depende de T1.1, T2.1)

- [x] **T4.1 — Proteger creacion de orden contra concurrencia**
  Revisar `operativo/views.py` funcion `crear_orden`. Envolver la creacion en `transaction.atomic()`. Usar `Mesa.objects.select_for_update()` para bloquear la mesa. Verificar `mesa.orden_activa is None` antes de crear. Si la mesa ya tiene orden activa, retornar error al usuario.
  RF: RF-001, RF-010 | Hallazgo: H5
  Hecho cuando: Dos requests simultaneos para crear orden en la misma mesa solo producen una orden exitosa y el otro retorna error.

- [ ] **T4.2 — Validar transiciones de estado en `cambiar_estado_orden`**
  Revisar `operativo/views.py` funcion `cambiar_estado_orden`. Antes de guardar el nuevo estado, llamar `orden.puede_cambiar_a(nuevo_estado)`. Si retorna `False`, agregar error al formulario y no guardar.
  RF: RF-003 | Hallazgo: H1
  Hecho cuando: Intentar cambiar una orden de `EN_PREPARACION` a `PENDIENTE` retorna un error y la orden mantiene su estado.

- [ ] **T4.3 — Restringir agregar productos a ordenes en estado PENDIENTE**
  Revisar `operativo/views.py` funcion `agregar_producto`. Antes de crear el `DetalleOrden`, verificar `orden.estado == Orden.PENDIENTE`. Si no es PENDIENTE, redirigir sin agregar el producto.
  RF: RF-002
  Hecho cuando: Intentar agregar un producto a una orden en estado `EN_PREPARACION` no crea el `DetalleOrden` y redirige al detalle.

- [x] **T4.4 — Validar cobro: estado, pago previo, monto y excedente**
  Revisar `caja/views.py` funcion `cobrar_orden`. Agregar validaciones antes de crear el `Pago`: (1) `orden.estado == Orden.LISTA` — rechazar si esta en `PENDIENTE`, `EN_PREPARACION`, `ENTREGADA` o `CANCELADA`. (2) `orden.pagos.count() == 0` — rechazar pago duplicado. (3) `monto >= orden.total` — rechazar si es menor. (4) Si `monto > total`, aceptar el pago completo sin registrar excedente como cambio ni saldo a favor. Envolver toda la operacion en `transaction.atomic()` con `select_for_update()` en la orden (RNF-002). Despues del cobro valido, la orden debe quedar en estado `ENTREGADA` y la mesa en `DISPONIBLE`. Si cualquiera validacion falla, retornar error al formulario.
  RF: RF-006 | Hallazgo: H2
  Hecho cuando: (a) Intentar cobrar una orden en estado `PENDIENTE` retorna error. (b) Intentar cobrar una orden en estado `EN_PREPARACION` retorna error. (c) Intentar cobrar una orden en estado `ENTREGADA` retorna error. (d) Intentar cobrar una orden en estado `CANCELADA` retorna error. (e) Intentar cobrar una orden que ya tiene pago retorna error. (f) Enviar un monto menor al total retorna error. (g) Enviar un monto exactamente igual al total crea el Pago y cambia la orden a ENTREGADA. (h) Enviar un monto mayor al total crea el Pago con el monto completo, la orden pasa a ENTREGADA y no se genera saldo pendiente.

- [ ] **T4.5 — Validar cancelacion: orden no terminal y sin pago previo**
  Revisar `operativo/views.py` funcion `cambiar_estado_orden`. Cuando el estado destino es `CANCELADA`, verificar ademas que (1) la orden no sea terminal (`orden.es_final == False`) y (2) `orden.pagos.count() == 0`.
  RF: RF-007 | Caso limite: 5
  Hecho cuando: (a) Intentar cancelar una orden `ENTREGADA` retorna error. (b) Intentar cancelar una orden con pago registrado retorna error.

- [ ] **T4.6 — Validar parametro `mesa` en menu publico**
  Revisar `menu_cliente/views.py` funcion `menu`. Envolver `get_object_or_404(Mesa, pk=mesa_id)` en un bloque `try/except ValueError` para que parametros no numericos retornen 404 en vez de 500.
  RF: RF-008 | Hallazgo: H13
  Hecho cuando: Acceder a `/menu/?mesa=abc` retorna una pagina 404 en lugar de un error 500.

---

## Fase 5: RF-008 — Cliente pide desde telefono (depende de T4.1, Fase 3)

- [ ] **T5.1 — Crear vista POST para crear orden desde el telefono**
  Crear una nueva vista en `menu_cliente/views.py` (funcion `crear_orden_cliente`) que reciba POST con `mesa_id` y lista de productos. Verificar que la mesa este DISPONIBLE. Usar `transaction.atomic()` + `select_for_update()` + verificacion `orden_activa`. Crear `Orden` (PENDIENTE) + `DetalleOrden` + cambiar mesa a OCUPADA. No requiere autenticacion.
  RF: RF-008
  Hecho cuando: Un POST con `mesa_id` valida y productos crea una orden PENDIENTE y la mesa cambia a OCUPADA.

- [ ] **T5.2 — Crear URL y template para confirmar orden del telefono**
  Agregar URL pattern en `menu_cliente/urls.py` para la vista de creacion. Crear template `confirmar_orden.html` en `menu_cliente/templates/menu_cliente/` que muestre los productos seleccionados, el total, y un boton de confirmar.
  RF: RF-008
  Hecho cuando: El flujo completo funciona: escanear QR -> ver menu -> seleccionar productos -> confirmar -> orden creada.

- [ ] **T5.3 — Agregar interactividad de seleccion de productos al menu publico**
  Revisar `menu_cliente/templates/menu_cliente/menu.html`. Agregar mecanismo (formularios o datos HTML) para que el cliente pueda seleccionar productos con cantidad. Incluir un boton "Confirmar pedido" que envie los productos seleccionados a la vista de creacion.
  RF: RF-008
  Hecho cuando: El cliente puede ver el menu, indicar cantidades de productos, y enviar el pedido.

---

## Fase 6: Tests

- [ ] **T6.1 — Tests de modelos en `operativo`**
  Crear tests en `operativo/tests.py`: (1) `test_mesa_str`, (2) `test_mesa_orden_activa` retorna orden no terminal, (3) `test_mesa_sin_orden_activa` retorna None, (4) `test_orden_total` suma subtotales, (5) `test_orden_es_final`, (6) `test_detalle_orden_subtotal`, (7) `test_detalle_orden_snapshot`, (8) `test_cliente_unique_together`, (9) `test_orden_puede_cambiar_a_transicion_valida`, (10) `test_orden_puede_cambiar_a_transicion_invalida`.
  RF: RF-001, RF-002, RF-003, RF-004, RF-006 | Hallazgo: G6
  Hecho cuando: `python manage.py test operativo` ejecuta todos los tests sin errores.

- [ ] **T6.2 — Tests de vistas en `operativo`**
  Crear tests en `operativo/tests.py`: (1) `test_crear_orden_get` (MESERO ve 200), (2) `test_crear_orden_post` (crea PENDIENTE + mesa OCUPADA), (3) `test_crear_orden_mesa_no_disponible`, (4) `test_crear_orden_concurrencia`, (5) `test_agregar_producto`, (6) `test_agregar_producto_orden_no_pendiente`, (7) `test_cambiar_estado_valido`, (8) `test_cambiar_estado_invalido`, (9) `test_liberar_mesa_entregada`, (10) `test_liberar_mesa_cancelada`, (11) `test_cancelar_orden_con_pago_previo`, (12) `test_generar_qr_auth`, (13) `test_crear_cliente_rapido_auth`.
  RF: RF-001, RF-002, RF-003, RF-004, RF-007, RF-009, RF-010 | Hallazgo: G6
  Hecho cuando: `python manage.py test operativo` ejecuta todos los tests de vistas sin errores.

- [ ] **T6.3 — Tests de vistas en `caja`**
  Crear tests en `caja/tests.py`: (1) `test_cobrar_orden_ok` (LISTA -> ENTREGADA), (2) `test_cobrar_orden_estado_invalido` (PENDIENTE rechazado), (3) `test_cobrar_orden_estado_en_preparacion` (EN_PREPARACION rechazado), (4) `test_cobrar_orden_estado_entregada` (ENTREGADA rechazado), (5) `test_cobrar_orden_estado_cancelada` (CANCELADA rechazado), (6) `test_cobrar_orden_pago_duplicado` (segundo pago rechazado), (7) `test_cobrar_orden_monto_insuficiente` (monto < total rechazado), (8) `test_cobrar_orden_monto_exacto` (monto == total aceptado), (9) `test_cobrar_orden_monto_excedente` (monto > total aceptado, excedente sin cambio), (10) `test_cobrar_orden_transaccion_atomica` (error en Pago no cambia estado de orden).
  RF: RF-006 | Hallazgo: G6
  Hecho cuando: `python manage.py test caja` ejecuta todos los tests sin errores.

- [ ] **T6.4 — Tests de vistas en `menu_cliente`**
  Crear tests en `menu_cliente/tests.py`: (1) `test_menu_con_mesa` (retorna menu de sucursal), (2) `test_menu_sin_mesa` (retorna menu general), (3) `test_menu_mesa_inexistente` (404), (4) `test_menu_parametro_invalido` (404 en vez de 500).
  RF: RF-008 | Hallazgo: G6
  Hecho cuando: `python manage.py test menu_cliente` ejecuta todos los tests sin errores.

- [ ] **T6.5 — Tests de vistas en `cocina`**
  Crear tests en `cocina/tests.py`: (1) `test_cocina_lista_ordenes` (ve PENDIENTE/EN_PREPARACION), (2) `test_cocina_sin_auth` (redirect a login), (3) `test_cocina_rol_incorrecto` (MESERO no accede).
  RF: RF-005, RF-009 | Hallazgo: G6
  Hecho cuando: `python manage.py test cocina` ejecuta todos los tests sin errores.

---

## Fase 7: Verificacion final

- [ ] **T7.1 — Ejecutar suite completa de tests**
  Ejecutar `python manage.py test` en la raiz del proyecto. Verificar que todos los tests pasan sin errores.
  RF: Todos | Criterio de finalizacion 3
  Hecho cuando: La salida muestra 0 errores y 0 fallos.

- [ ] **T7.2 — Verificar checklist de criterios de finalizacion del spec.md**
  Revisar cada uno de los 7 criterios de finalizacion del spec.md (lineas 164-172) y confirmar que se cumplen: (1) RF-001 a RF-010 implementados, (2) hallazgos H1-H7 corregidos, (3) tests minimos existen, (4) autenticacion y control de rol, (5) transiciones validadas, (6) cobro valida estado LISTA (rechaza PENDIENTE, EN_PREPARACION, ENTREGADA, CANCELADA), unicidad de pago, monto >= total y maneja excedente, (7) creacion atomica.
  RF: Todos
  Hecho cuando: Los 7 criterios estan marcados como cumplidos.
