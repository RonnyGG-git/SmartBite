# Plan de Implementacion: Flujo de Ordenes MVP

## 1. Estructura de Modulos y Componentes Existentes

**RF cubiertos: RF-001 a RF-010 (todos los requisitos funcionales)**

### Apps involucradas en el flujo de ordenes

| App | Responsabilidad | Modelos clave | Vistas clave |
|-----|----------------|---------------|--------------|
| `operativo` | Ordenes, mesas, clientes rapidos | `Mesa`, `Cliente`, `Orden`, `DetalleOrden` | `crear_orden`, `agregar_producto`, `cambiar_estado_orden`, `generar_qr`, `DetalleOrdenView` |
| `caja` | Pagos y cobro | `Pago`, `MetodoPago` | `cobrar_orden`, `PagoListView`, `VentaListView` |
| `menu_cliente` | Menu publico para clientes | (sin modelos) | `menu` (vista publica sin auth) |
| `cocina` | Vista de cocina (solo lectura) | (sin modelos propios, consulta `Orden`) | `CocinaListView` |
| `catalogo` | Catalogo de productos | `Categoria`, `Producto` | CRUD Productos/Categorias |
| `restaurantes` | Restaurantes y sucursales | `Restaurante`, `Sucursal` | CRUD Restaurantes/Sucursales |
| `cuentas` | Usuarios, roles y permisos | `Usuario`, `Rol`, `Permiso` | CRUD Usuarios/Roles |
| `core` | Utilidades compartidas | `TimestampedModel` (abstracto) | `RoleRequiredMixin`, `rol_requerido` |

### Componentes transversales del flujo

- **`core.mixins.RoleRequiredMixin`** (`core/mixins.py:4-22`): Mixin para vistas basadas en clase. Combina `LoginRequiredMixin` + `UserPassesTestMixin`.
- **`core.mixins.rol_requerido`** (`core/mixins.py:25-47`): Decorador para vistas basadas en funcion. Equivalente funcional al mixin.
- **`core.models.TimestampedModel`** (`core/models.py:4-10`): Modelo abstracto que agrega `creado_en` (auto_now_add) y `actualizado_en` (auto_now).

### Archivos que requieren modificaciones

| Archivo | Tipo de cambio | Hallazgo asociado |
|---------|---------------|-------------------|
| `operativo/views.py` | Validar transiciones, transaccion atomica en crear_orden, proteger generar_qr y crear_cliente_rapido | H1, H3, H4, H5 |
| `operativo/forms.py` | Filtrar choices de estados segun estado actual en `CambiarEstadoOrdenForm` | H1 |
| `operativo/models.py` | Agregar `unique_together` a Cliente; `DetalleOrden` hereda `TimestampedModel` | H10, G10 |
| `caja/views.py` | Validar estado LISTA, unicidad de pago, monto >= total en `cobrar_orden` | H2 |
| `menu_cliente/views.py` | Validar parametro `mesa` contra ValueError | H13 |
| `operativo/tests.py` | Tests de modelos y vistas | G6 |
| `caja/tests.py` | Tests de modelos y vistas | G6 |
| `menu_cliente/tests.py` | Tests de vista publica | G6 |
| `cocina/tests.py` | Tests de vista de cocina | G6 |

---

## 2. Modelo de Datos y Relaciones

**RF cubiertos: RF-001, RF-002, RF-004, RF-006, RF-007, RF-010**

### Diagrama de relaciones

```
Restaurante
    └──< Sucursal
            ├──< Mesa
            │      └──< Orden
            │            ├──< DetalleOrden ──> Producto
            │            ├──< Pago ──> MetodoPago
            │            └──> Cliente (SET_NULL)
            └──< Producto ──> Categoria
```

### Modelos existentes relevantes

#### Mesa (`operativo/models.py:6-25`)

| Campo | Tipo | Existente | Observacion |
|-------|------|-----------|-------------|
| `numero` | `PositiveIntegerField` | Si | - |
| `capacidad` | `PositiveIntegerField` | Si | Default 4 |
| `estado` | `CharField` | Si | Choices: DISPONIBLE/OCUPADA/RESERVADA |
| `activa` | `BooleanField` | Si | Default True |
| `sucursal` | `FK a Sucursal` | Si | on_delete=PROTECT |
| `orden_activa` | `@property` | Si | Excluye ENTREGADA y CANCELADA |

**Cambios requeridos:** Ninguno. El modelo cubre RF-001 y RF-004.

#### Cliente (`operativo/models.py:28-38`)

| Campo | Tipo | Existente | Observacion |
|-------|------|-----------|-------------|
| `nombre` | `CharField(150)` | Si | - |
| `telefono` | `CharField(30)` | Si | blank=True |
| `email` | `EmailField` | Si | blank=True |
| `numero_documento` | `CharField(30)` | Si | blank=True |

**Cambios requeridos:** Agregar `unique_together = [("nombre", "telefono", "email")]` (H10 de VALIDACIONES.md).

#### Orden (`operativo/models.py:41-73`)

| Campo | Tipo | Existente | Observacion |
|-------|------|-----------|-------------|
| `mesa` | `FK a Mesa` | Si | on_delete=PROTECT |
| `cliente` | `FK a Cliente` | Si | on_delete=SET_NULL, null=True |
| `estado` | `CharField` | Si | Choices: PENDIENTE/EN_PREPARACION/LISTA/ENTREGADA/CANCELADA |
| `total` | `@property` | Si | Suma de detalles.subtotal |
| `es_final` | `@property` | Si | True si ENTREGADA o CANCELADA |

**Cambios requeridos:** Ninguno. Los estados y el calculo de total cubren RF-006 y RF-007.

#### DetalleOrden (`operativo/models.py:76-87`)

| Campo | Tipo | Existente | Observacion |
|-------|------|-----------|-------------|
| `orden` | `FK a Orden` | Si | on_delete=CASCADE |
| `producto` | `FK a Producto` | Si | on_delete=PROTECT |
| `cantidad` | `PositiveIntegerField` | Si | Default 1 |
| `precio_unitario` | `DecimalField` | Si | Snapshot del precio actual |

**Cambios requeridos:** Heredar de `TimestampedModel` en lugar de `models.Model` (G10 de VALIDACIONES.md). Solo agrega trazabilidad, no afecta funcionalidad.

#### Pago (`caja/models.py:17-27`)

| Campo | Tipo | Existente | Observacion |
|-------|------|-----------|-------------|
| `orden` | `FK a Orden` | Si | on_delete=PROTECT |
| `metodo_pago` | `FK a MetodoPago` | Si | on_delete=PROTECT |
| `monto` | `DecimalField` | Si | max_digits=10, decimal_places=2 |
| `referencia_transaccion` | `CharField(100)` | Si | blank=True |

**Cambios requeridos:** Ninguno.

#### MetodoPago (`caja/models.py:6-13`)

| Campo | Tipo | Existente | Observacion |
|-------|------|-----------|-------------|
| `nombre` | `CharField(50)` | Si | unique=True |
| `activo` | `BooleanField` | Si | Default True |

**Cambios requeridos:** Ninguno.

### Relaciones y restricciones de integridad

| Relacion | on_delete | Justificacion | RF cubierto |
|----------|-----------|---------------|-------------|
| `Orden.mesa a Mesa` | PROTECT | No se puede eliminar mesa con ordenes | RF-001, RF-004 |
| `Orden.cliente a Cliente` | SET_NULL | Cliente puede eliminarse sin perder la orden | RF-001 |
| `DetalleOrden.orden a Orden` | CASCADE | Eliminar orden elimina sus detalles | RF-002 |
| `DetalleOrden.producto a Producto` | PROTECT | No se puede eliminar producto en uso | RF-002 |
| `Pago.orden a Orden` | PROTECT | No se puede eliminar orden con pagos | RF-006 |
| `Pago.metodo_pago a MetodoPago` | PROTECT | No se puede eliminar metodo de pago en uso | RF-006 |

### Resumen de cambios al modelo

| Modelo | Cambio | Hallazgo | Prioridad |
|--------|--------|----------|-----------|
| `Cliente` | Agregar `unique_together` | H10 | MEDIA |
| `DetalleOrden` | Cambiar herencia a `TimestampedModel` | G10 | BAJA |

No se crean nuevos modelos. Todos los modelos necesarios ya existen.

---

## 3. Flujo y Reglas de Negocio

**RF cubiertos: RF-001 a RF-008**

### Diagrama de estados de una Orden

```
PENDIENTE ──> EN_PREPARACION ──> LISTA ──> ENTREGADA
    │                │              │
    └──> CANCELADA   └──> CANCELADA └──> CANCELADA
```

### Transiciones permitidas (RF-003)

| Estado origen | Estados destino permitidos | RF asociado |
|---------------|---------------------------|-------------|
| PENDIENTE | EN_PREPARACION, CANCELADA | RF-003 |
| EN_PREPARACION | LISTA, CANCELADA | RF-003 |
| LISTA | ENTREGADA, CANCELADA | RF-003, RF-006 |
| ENTREGADA | (ninguna - terminal) | - |
| CANCELADA | (ninguna - terminal) | - |

Cualquier otra transicion debe ser rechazada.

### Diccionario de transiciones

A implementar como constante en `operativo/models.py`:

```python
TRANSICIONES_VALIDAS = {
    Orden.PENDIENTE: [Orden.EN_PREPARACION, Orden.CANCELADA],
    Orden.EN_PREPARACION: [Orden.LISTA, Orden.CANCELADA],
    Orden.LISTA: [Orden.ENTREGADA, Orden.CANCELADA],
    Orden.ENTREGADA: [],
    Orden.CANCELADA: [],
}
```

### Ciclo de vida de una orden

1. **Creacion (RF-001):** Mesero selecciona mesa DISPONIBLE y activa. Opcionalmente crea cliente rapido. Se crea Orden con estado PENDIENTE. Mesa cambia a OCUPADA. Operacion dentro de `transaction.atomic()` con `select_for_update()` en Mesa (RF-010).

2. **Agregar productos (RF-002):** Mesero agrega productos uno a uno desde el detalle de la orden. Se crea DetalleOrden con `precio_unitario = producto.precio` (snapshot). Solo se permite si la orden esta en PENDIENTE (decision tecnica, ver seccion 5).

3. **Enviar a cocina (RF-003):** Mesero cambia PENDIENTE a EN_PREPARACION. Jefe de cocina ve la orden.

4. **Preparar en cocina (RF-005):** Jefe de cocina visualiza ordenes en PENDIENTE o EN_PREPARACION. Vista de solo lectura.

5. **Marcar como lista (RF-003):** Mesero cambia EN_PREPARACION a LISTA.

6. **Entregar (RF-003):** Mesero cambia LISTA a ENTREGADA. Mesa vuelve a DISPONIBLE (RF-004).

7. **Cobrar (RF-006):** Cajero cobra orden en estado LISTA. Valida:
   - Solo ordenes en estado LISTA pueden cobrarse (PENDIENTE, EN_PREPARACION, ENTREGADA, CANCELADA se rechazan).
   - No existe pago previo para la misma orden (unicidad).
   - Monto recibido >= total de la orden.
   - Monto exactamente igual al total es valido.
   - Monto superior al total se acepta como excedente (sin saldo pendiente ni modificacion del total).
   - Registra metodo de pago y referencia cuando corresponda.
   - Despues de cobro valido, orden pasa a ENTREGADA. Mesa vuelve a DISPONIBLE.
   - Operacion dentro de `transaction.atomic()` (RNF-002).

8. **Cancelar (RF-007):** Mesero cancela desde cualquier estado no terminal. Valida que no exista pago previo (caso limite 5). Orden cambia a CANCELADA. Mesa vuelve a DISPONIBLE.

### Flujo de cliente desde telefono (RF-008)

1. Cliente escanea QR con URL `/menu/?mesa=id`.
2. Vista publica muestra menu de la sucursal de la mesa.
3. Si mesa DISPONIBLE: cliente agrega productos y confirma.
4. Se crea Orden PENDIENTE + mesa OCUPADA.
5. Si mesa OCUPADA: pendiente de aclaracion (Duda Abierta en spec.md).

---

## 4. Contrato Funcional del Flujo

**RF cubiertos: RF-001 a RF-010**

### RF-001: Creacion de orden

| Aspecto | Detalle |
|---------|---------|
| **Entrada** | `mesa` (ID, requerido), `cliente` (ID o datos nuevos, opcional) |
| **Salida** | Redirect a `detalle_orden` con la orden creada |
| **Errores** | Mesa no DISPONIBLE o inactiva: rechazo del formulario. Mesa con orden activa: error de concurrencia (RF-010) |
| **Permisos** | MESERO, ADMINISTRADOR (RF-009) |
| **Estados** | Orden: PENDIENTE. Mesa: DISPONIBLE a OCUPADA |
| **Transaccion** | `transaction.atomic()` + `select_for_update()` en Mesa |

### RF-002: Agregar productos

| Aspecto | Detalle |
|---------|---------|
| **Entrada** | `orden` (ID en URL), `producto` (ID), `cantidad` (entero >= 1) |
| **Salida** | Redirect a `detalle_orden` |
| **Errores** | Producto no disponible en sucursal de mesa: rechazo. Orden no en PENDIENTE: bloquear (seccion 5) |
| **Permisos** | MESERO, ADMINISTRADOR (RF-009) |
| **Estados** | Solo PENDIENTE |
| **Snapshot** | `precio_unitario = producto.precio` al momento de agregar |

### RF-003: Transiciones de estado

| Aspecto | Detalle |
|---------|---------|
| **Entrada** | `orden` (ID en URL), `estado` (nuevo estado) |
| **Salida** | Redirect a `detalle_orden` |
| **Errores** | Transicion no valida: rechazo con mensaje de error |
| **Permisos** | MESERO, ADMINISTRADOR para todos los cambios de estado |
| **Estados** | Ver diccionario en seccion 3 |

### RF-004: Liberar mesa

| Aspecto | Detalle |
|---------|---------|
| **Logica** | Al alcanzar ENTREGADA o CANCELADA, `mesa.estado = DISPONIBLE` |
| **Implementacion** | Se ejecuta en `cambiar_estado_orden` y `cobrar_orden` |

### RF-005: Visualizacion de cocina

| Aspecto | Detalle |
|---------|---------|
| **Entrada** | Ninguna (consulta) |
| **Salida** | Lista de ordenes en PENDIENTE/EN_PREPARACION con mesa, productos, cantidades |
| **Permisos** | JEFE_COCINA, ADMINISTRADOR (RF-009) |
| **Solo lectura** | Sin botones de cambio de estado |

### RF-006: Cobro de orden

| Aspecto | Detalle |
|---------|---------|
| **Entrada** | `orden` (ID en URL), `metodo_pago` (ID), `monto` (decimal), `referencia_transaccion` (opcional) |
| **Salida** | Redirect a `mesas_list` |
| **Errores** | Orden no en LISTA: rechazo. PENDIENTE, EN_PREPARACION, ENTREGADA o CANCELADA: rechazo. Pago previo existente: rechazo. Monto < total: rechazo |
| **Permisos** | CAJERO, ADMINISTRADOR (RF-009) |
| **Estados** | Orden: LISTA a ENTREGADA. Mesa: OCUPADA a DISPONIBLE |
| **Validacion monto** | monto >= total. Si monto > total: se acepta el pago completo, excedente no se registra como cambio ni saldo a favor |
| **Transaccion** | `transaction.atomic()` |

### RF-007: Cancelacion de orden

| Aspecto | Detalle |
|---------|---------|
| **Entrada** | `orden` (ID en URL), `estado` = CANCELADA |
| **Salida** | Redirect a `detalle_orden` |
| **Errores** | Orden terminal (ENTREGADA/CANCELADA): rechazo. Orden con pago previo: rechazo |
| **Permisos** | MESERO, ADMINISTRADOR (RF-009) |
| **Estados** | Cualquier estado no terminal a CANCELADA. Mesa a DISPONIBLE |
| **Restricciones** | Sin motivo. Sin devolucion de inventario |

### RF-008: Cliente pide desde telefono

| Aspecto | Detalle |
|---------|---------|
| **Entrada** | URL `/menu/?mesa=id` (escaneo QR) |
| **Salida** | Pagina del menu + formulario de creacion de orden |
| **Errores** | Mesa inexistente: 404. Mesa ocupada: pendiente de aclaracion |
| **Permisos** | Sin autenticacion (vista publica) |
| **Estados** | Mesa DISPONIBLE a OCUPADA. Orden PENDIENTE |

### RF-009: Proteccion de vistas

| Rol | Vistas permitidas |
|-----|-------------------|
| MESERO | Crear orden, agregar productos, cambiar estado, ver QR, ver detalle orden |
| CAJERO | Ver detalle orden, cobrar orden, ver pagos, ver ventas |
| JEFE_COCINA | Ver tabla de cocina (solo lectura) |
| ADMINISTRADOR | Todas las acciones |

Todas las vistas excepto el menu publico requieren autenticacion.

### RF-010: Proteccion contra concurrencia

| Aspecto | Detalle |
|---------|---------|
| **Mecanismo** | `transaction.atomic()` + `select_for_update()` en Mesa al crear orden |
| **Verificacion** | `mesa.orden_activa` debe ser None antes de crear |
| **Comportamiento** | Dos solicitudes simultaneas: solo una exita, la otra recibe error |

---

## 5. Decisiones Tecnicas Justificadas

**RF cubiertos: RF-001, RF-002, RF-003, RF-005, RF-006, RF-007, RF-008, RF-009, RF-010**

### Decision 1: Agregar productos solo en estado PENDIENTE

**Alternativa considerada:** Permitir agregar productos en PENDIENTE y EN_PREPARACION.
**Alternativa descartada:** El spec.md (Duda Abierta) plantea esta pregunta pero no resuelve. La decision es restringir a PENDIENTE porque:
- El RF-003 define que EN_PREPARACION es un estado donde la cocina ya esta trabajando.
- Agregar productos en EN_PREPARACION crearia inconsistencia entre lo que cocina ve y lo que el mesero modifica.
- La Duda Abierta del spec.md deja esto pendiente, por lo que la restriccion a PENDIENTE es la mas segura.

### Decision 2: Diccionario de transiciones en el modelo

**Alternativa considerada:** Validar transiciones en la vista directamente.
**Alternativa considerada:** Validar en el modelo con un metodo `puede_cambiar_a(estado)`.
**Decision:** Colocar `TRANSICIONES_VALIDAS` como constante en `operativo/models.py` y un metodo `puede_cambiar_a()` en `Orden`. Esto cumple con la constitucion (modelos = logica de negocio) y evita duplicacion de logica entre `cambiar_estado_orden` y `cobrar_orden`.

### Decision 3: Bloqueo selectivo para concurrencia

**Alternativa considerada:** Solo usar `transaction.atomic()` sin `select_for_update()`.
**Alternativa descartada:** Sin el bloqueo, dos transacciones podrian leer la misma mesa como DISPONIBLE simultaneamente. `select_for_update()` bloquea la fila de Mesa hasta que la transaccion complete, garantizando que solo una creacion de orden exitosa para la misma mesa.

### Decision 4: Validacion de cobro en la vista

**Alternativa considerada:** Validar en el modelo con un metodo `puede_cobrar()`.
**Decision:** Validar en `cobrar_orden` (vista) usando el diccionario de transiciones + verificacion de pago previo + monto >= total + rechazo de estados no LISTA + manejo de excedente. La constitucion establece que la vista orquesta HTTP, y estas validaciones son de control de acceso e integridad transaccional, que corresponden a la capa de vista. Sin embargo, se puede extraer la logica de validacion a un metodo en el modelo para reutilizar en tests.

### Decision 5: Menu publico sin autenticacion

**Alternativa considerada:** Requerir autenticacion para el menu publico.
**Alternativa descartada:** El RF-008 establece que el cliente escanea un QR y ve el menu. El spec.md (linea 123) confirma que el menu publico es la unica vista sin autenticacion. Esto es correcto porque el QR se accede desde el telefono del cliente.

### Decision 6: Cancelacion con validacion de pago previo

**Alternativa considerada:** Permitir cancelar incluso con pago previo.
**Alternativa descartada:** El caso limite 5 del spec.md establece: "Si la orden ya tiene un pago registrado, no se puede cancelar." Esto evita inconsistencia financiera.

### Decision 7: Transiciones invalidas con choice field filtrado

**Alternativa considerada:** Aceptar cualquier estado y validar en la vista.
**Decision:** Modificar `CambiarEstadoOrdenForm` para que el `ChoiceField` de estado se filtre dinamicamente segun el estado actual de la orden. Esto brinda UX clara (el usuario solo ve opciones validas) y reduce la superficie de error.

### Decision 8: No crear nuevos modelos

**Observacion:** Todos los modelos necesarios (Mesa, Cliente, Orden, DetalleOrden, Pago, MetodoPago, Producto, Categoria, Sucursal, Restaurante, Usuario, Rol) ya existen. No se requieren migraciones de esquema nuevas, solo los cambios menores indicados en la seccion 2.

---

## 6. Estrategia de Tests

**RF cubiertos: RF-001 a RF-010, G6 (tests vacios)**

### Enfoque general

- Framework: `django.test.TestCase` (ya disponible, sin dependencias externas adicionales).
- Ubicacion: `operativo/tests.py`, `caja/tests.py`, `menu_cliente/tests.py`, `cocina/tests.py`.
- Cada test crea sus propios datos (fixtures manuales en setUp o factory methods).
- Constitucion: "Toda app debe tener tests minimos (models + views)".

### Tests de modelos (`operativo/tests.py`)

| Test | Que valida | RF/RNF |
|------|-----------|--------|
| `test_mesa_str` | `__str__` de Mesa retorna "Mesa X" | - |
| `test_mesa_orden_activa` | `orden_activa` retorna la orden no terminal | RF-001 |
| `test_mesa_sin_orden_activa` | `orden_activa` retorna None cuando todas son terminales | RF-004 |
| `test_orden_total` | `total` suma correctamente los subtotales | RF-006 |
| `test_orden_es_final` | `es_final` es True solo para ENTREGADA y CANCELADA | RF-003 |
| `test_detalle_orden_subtotal` | `subtotal` = cantidad * precio_unitario | RF-002 |
| `test_detalle_orden_snapshot` | `precio_unitario` se guarda como snapshot | RF-002 |
| `test_cliente_unique_together` | Dos clientes con mismo nombre/telefono/email genera error | H10 |

### Tests de vistas - operativo (`operativo/tests.py`)

| Test | Que valida | RF |
|------|-----------|-----|
| `test_crear_orden_get` | GET a crear_orden retorna 200 para MESERO | RF-009 |
| `test_crear_orden_post` | POST crea orden PENDIENTE y mesa OCUPADA | RF-001 |
| `test_crear_orden_mesa_no_disponible` | POST con mesa OCUPADA es rechazado | RF-001 |
| `test_crear_orden_concurrencia` | Dos POST simultaneos para misma mesa: solo uno exita | RF-010 |
| `test_agregar_producto` | POST crea DetalleOrden con snapshot de precio | RF-002 |
| `test_agregar_producto_orden_no_pendiente` | POST a orden EN_PREPARACION es rechazado | RF-002 |
| `test_cambiar_estado_valido` | POST cambia estado segun transiciones permitidas | RF-003 |
| `test_cambiar_estado_invalido` | POST con transicion no valida es rechazada | RF-003 |
| `test_liberar_mesa_entregada` | Al cambiar a ENTREGADA, mesa vuelve a DISPONIBLE | RF-004 |
| `test_liberar_mesa_cancelada` | Al cambiar a CANCELADA, mesa vuelve a DISPONIBLE | RF-004 |
| `test_cocina_solo_lectura` | JEFE_COCINA ve ordenes pendientes pero sin botones | RF-005 |
| `test_generar_qr_auth` | generar_qr sin autenticacion redirige a login | RF-009, H3 |
| `test_crear_cliente_rapido_auth` | crear_cliente_rapido sin auth es rechazado | RF-009, H4 |

### Tests de vistas - caja (`caja/tests.py`)

| Test | Que valida | RF |
|------|-----------|-----|
| `test_cobrar_orden_ok` | POST con estado LISTA crea Pago y cambia a ENTREGADA | RF-006 |
| `test_cobrar_orden_estado_invalido` | POST con estado PENDIENTE es rechazado | RF-006 |
| `test_cobrar_orden_estado_en_preparacion` | POST con estado EN_PREPARACION es rechazado | RF-006 |
| `test_cobrar_orden_estado_entregada` | POST con estado ENTREGADA es rechazado | RF-006 |
| `test_cobrar_orden_estado_cancelada` | POST con estado CANCELADA es rechazado | RF-006 |
| `test_cobrar_orden_pago_duplicado` | Segundo pago para misma orden es rechazado | RF-006, caso limite 4 |
| `test_cobrar_orden_monto_insuficiente` | Monto menor al total es rechazado | RF-006, caso limite 3 |
| `test_cobrar_orden_monto_exacto` | Monto igual al total es aceptado | RF-006 |
| `test_cobrar_orden_monto_excedente` | Monto mayor al total se acepta, excedente no registra cambio | RF-006, caso limite 9 |
| `test_cobrar_orden_transaccion_atomica` | Error en creacion de Pago no cambia estado de orden | RF-006, RNF-002 |

### Tests de vistas - menu_cliente (`menu_cliente/tests.py`)

| Test | Que valida | RF |
|------|-----------|-----|
| `test_menu_con_mesa` | GET con mesa_id retorna menu de la sucursal | RF-008 |
| `test_menu_sin_mesa` | GET sin mesa_id retorna menu general | RF-008 |
| `test_menu_mesa_inexistente` | GET con mesa_id invalido retorna 404 | RF-008 |

### Tests de vistas - cocina (`cocina/tests.py`)

| Test | Que valida | RF |
|------|-----------|-----|
| `test_cocina_lista_ordenes` | JEFE_COCINA ve ordenes PENDIENTE/EN_PREPARACION | RF-005 |
| `test_cocina_sin_auth` | Sin autenticacion redirige a login | RF-009 |
| `test_cocina_rol_incorrecto` | MESERO no puede acceder a cocina | RF-009 |

### Casos limite a testear (especificados en spec.md)

| Caso limite | Test asociado | RF |
|-------------|--------------|-----|
| 1. Mesa con orden activa | `test_crear_orden_concurrencia` | RF-010 |
| 2. Producto sin stock | Fuera de alcance del MVP | - |
| 3. Cobro con monto insuficiente | `test_cobrar_orden_monto_insuficiente` | RF-006 |
| 4. Cobro duplicado | `test_cobrar_orden_pago_duplicado` | RF-006 |
| 5. Cancelacion con pago previo | `test_cancelar_orden_con_pago_previo` | RF-007 |
| 6. QR de mesa ocupada | Pendiente de aclaracion (Duda Abierta) | RF-008 |
| 7. Cliente sin mesa | RF-008 requiere QR con mesa | RF-008 |
| 8. Transicion invalida | `test_cambiar_estado_invalido` | RF-003 |
| 9. Cobro con excedente | `test_cobrar_orden_monto_excedente` | RF-006 |

---

## 7. Mapeo RF por Seccion del Plan

| Seccion del plan | RF cubiertos |
|------------------|-------------|
| 1. Estructura de modulos | RF-001 a RF-010 (todas las apps y componentes que intervienen) |
| 2. Modelo de datos y relaciones | RF-001, RF-002, RF-004, RF-006, RF-007, RF-010 |
| 3. Flujo y reglas de negocio | RF-001 a RF-008 |
| 4. Contrato funcional | RF-001 a RF-010 |
| 5. Decisiones tecnicas | RF-001, RF-002, RF-003, RF-005, RF-006, RF-007, RF-008, RF-009, RF-010 |
| 6. Estrategia de tests | RF-001 a RF-010, casos limite 1, 3, 4, 5, 8 |

### Hallazgos de VALIDACIONES.md cubiertos

| Hallazgo | Seccion del plan | Descripcion |
|----------|-----------------|-------------|
| H1 (CRITICA) | 3, 4, 5 | Transiciones de estado sin validar -> diccionario de transiciones + formulario filtrado |
| H2 (CRITICA) | 3, 4, 5, 6 | Cobro sin verificar estado/pagos -> validaciones en cobrar_orden (estado LISTA, unicidad, monto >= total, excedente) |
| H3 (ALTA) | 1, 4 | generar_qr sin autenticacion -> agregar rol_requerido |
| H4 (ALTA) | 1, 4 | crear_cliente_rapido sin control de rol -> agregar rol_requerido |
| H5 (ALTA) | 3, 4, 5 | crear_orden sin proteccion atomica -> transaction.atomic + select_for_update |
| H10 (MEDIA) | 2 | Clientes sin unicidad -> unique_together |
| G6 (CRITICA) | 6 | Tests completamente vacios -> estrategia completa de tests |
| G10 (BAJA) | 2 | DetalleOrden sin TimestampedModel -> cambiar herencia |
| H13 (MEDIA) | 5 | Menu publico sin validacion robusta -> validar parametro mesa |

### Dudas abiertas del spec.md pendientes de resolver

1. Que debe ocurrir si el cliente intenta pedir desde el telefono pero la mesa ya esta ocupada.
2. Debe permitirse al MESERO agregar productos a una orden en EN_PREPARACION o solo en PENDIENTE.
3. El JEFE_COCINA debe poder ver el detalle completo de una orden o solo mesa y productos.
