# Especificacion: Flujo de Ordenes MVP

## Contexto

SmartBite es un sistema de gestion para restaurantes. El flujo de ordenes es la funcionalidad central: desde que un mesero crea una orden para una mesa, pasa por preparacion en cocina, hasta el cobro al cliente.

El sistema ya cuenta con codigo funcional para este flujo, pero tiene problemas de seguridad (transiciones sin validar, cobro sin validacion, falta de autenticacion en vistas) que deben corregirse.

## Objetivo

Documentar el flujo completo de ordenes del MVP, incluyendo la funcionalidad existente que debe mantenerse y los controles de seguridad que deben implementarse.

## Usuarios/Roles

| Rol | Acciones permitidas |
|-----|---------------------|
| MESERO | Crear orden, agregar productos, cambiar estado, ver QR |
| CAJERO | Ver detalle de orden, cobrar orden |
| JEFE_COCINA | Ver tabla de cocina (solo lectura) |
| ADMINISTRADOR | Todas las acciones |

## Historias de Usuario

### HU-001: Crear orden
**Como** mesero, **quiero** crear una orden para una mesa, **para** registrar el pedido del cliente.

### HU-002: Agregar productos
**Como** mesero, **quiero** agregar productos a una orden existente, **para** construir el pedido completo.

### HU-003: Enviar a cocina
**Como** mesero, **quiero** enviar la orden a cocina, **para** que inicien la preparacion.

### HU-004: Preparar orden
**Como** jefe de cocina, **quiero** ver las ordenes pendientes, **para** organizar la preparacion.

### HU-005: Marcar como lista
**Como** mesero, **quiero** marcar una orden como lista, **para** indicar que esta lista para entregar.

### HU-006: Entregar orden
**Como** mesero, **quiero** marcar una orden como entregada, **para** confirmar que el cliente recibio su pedido.

### HU-007: Cobrar orden
**Como** cajero, **quiero** cobrar una orden, **para** registrar el pago y cerrar la transaccion.

### HU-008: Cancelar orden
**Como** mesero, **quiero** cancelar una orden, **para** anular un pedido que no se realizara.

### HU-009: Ver menu y pedir desde telefono
**Como** cliente, **quiero** escanear un QR y crear una orden desde mi telefono, **para** pedir sin esperar al mesero.

## Requisitos Funcionales

### RF-001: Creacion de orden
- El mesero selecciona una mesa (solo mesas DISPONIBLES y activas).
- Opcionalmente selecciona o crea un cliente rapido.
- Al crear, la mesa cambia a estado OCUPADA.
- **Criterio de aceptacion:** DADO un mesero con permisos, CUANDO crea una orden para una mesa DISPONIBLE, ENTONCES la orden se crea con estado PENDIENTE y la mesa cambia a OCUPADA.

### RF-002: Agregar productos a orden
- El mesero agrega productos uno a uno desde el detalle de la orden.
- Se registra el precio unitario actual del producto como snapshot.
- **Criterio de aceptacion:** DADO una orden en estado PENDIENTE, CUANDO el mesero agrega un producto, ENTONCES se crea un DetalleOrden con precio unitario del catalogo actual.

### RF-003: Transiciones de estado validas
Las transiciones permitidas son:
- PENDIENTE -> EN_PREPARACION
- PENDIENTE -> CANCELADA
- EN_PREPARACION -> LISTA
- EN_PREPARACION -> CANCELADA
- LISTA -> ENTREGADA
- LISTA -> CANCELADA

Cualquier otra transicion debe ser rechazada.
- **Criterio de aceptacion:** DADO una orden en estado EN_PREPARACION, CUANDO se intenta cambiar a PENDIENTE, ENTONCES el sistema rechaza el cambio con un mensaje de error.

### RF-004: Liberar mesa al estados terminales
Al alcanzar ENTREGADA o CANCELADA, la mesa vuelve a DISPONIBLE.
- **Criterio de aceptacion:** DADO una orden para una mesa OCUPADA, CUANDO la orden cambia a ENTREGADA, ENTONCES la mesa vuelve a DISPONIBLE.

### RF-005: Visualizacion de cocina
- La vista de cocina muestra ordenes en estado PENDIENTE o EN_PREPARACION.
- Muestra mesa, productos con cantidades y estado.
- Es solo lectura (sin botones para cambiar estado).
- **Criterio de aceptacion:** DADO ordenes en estado PENDIENTE, CUANDO el jefe de cocina accede a la vista de cocina, ENTONCES ve las ordenes con mesa, productos y cantidades.

### RF-006: Cobro de orden
- Solo se puede cobrar ordenes en estado LISTA.
- Las ordenes en estado PENDIENTE, EN_PREPARACION, ENTREGADA o CANCELADA no pueden cobrarse.
- Se valida que no exista un pago previo para la misma orden.
- El monto debe ser mayor o igual al total de la orden.
- Si el monto recibido es mayor al total, se acepta el pago completo y la orden queda como cobrada. El excedente no se registra como cambio ni saldo a favor dentro del MVP.
- Se registra metodo de pago y referencia opcional.
- Al cobrar, la orden cambia a ENTREGADA.
- **Criterio de aceptacion:** DADO una orden en estado LISTA con total $50.000, CUANDO el cajero registra un pago de $50.000, ENTONCES se crea el Pago, la orden cambia a ENTREGADA y la mesa a DISPONIBLE.

### RF-007: Cancelacion de orden
- La orden puede cancelarse desde cualquier estado no terminal.
- La mesa se libera automaticamente.
- No se registra motivo de cancelacion.
- No se devuelve inventario.
- **Criterio de aceptacion:** DADO una orden en estado EN_PREPARACION para una mesa OCUPADA, CUANDO se cancela, ENTONCES la orden cambia a CANCELADA y la mesa a DISPONIBLE.

### RF-008: Cliente pide desde telefono
- El cliente escanea un QR que contiene la URL /menu/?mesa=id.
- Puede ver el menu de la sucursal asignada a la mesa.
- Puede crear una orden nueva agregando productos.
- La orden se crea con estado PENDIENTE y la mesa cambia a OCUPADA.
- **Criterio de aceptacion:** DADO un cliente que escanea el QR de una mesa DISPONIBLE, CUANDO agrega productos y confirma, ENTONCES se crea una orden PENDIENTE y la mesa pasa a OCUPADA.

### RF-009: Proteccion de vistas
- Todas las vistas de ordenes requieren autenticacion.
- Las vistas de creacion, edicion y cambio de estado requieren rol MESERO o ADMINISTRADOR.
- Las vistas de cobro requieren rol CAJERO o ADMINISTRADOR.
- La vista de cocina requiere rol JEFE_COCINA o ADMINISTRADOR.
- **Criterio de aceptacion:** DADO un usuario sin sesion, CUANDO intenta acceder a cualquier vista de ordenes, ENTONCES es redirigido al login.

### RF-010: Proteccion contra concurrencia
- Al crear una orden, se verifica que la mesa no tenga otra orden activa.
- Se usa transaccion atomica para evitar duplicados.
- **Criterio de aceptacion:** DADO dos solicitudes simultaneas para crear orden en la misma mesa, CUANDO se procesan, ENTONCES solo una exita y la otra recibe un error.

## Requisitos No Funcionales

### RNF-001: Seguridad
- Todas las vistas requieren autenticacion excepto el menu publico.
- Los roles se validan en cada vista segun la matriz de permisos.
- Las transiciones de estado se validan con un diccionario de transiciones permitidas.

### RNF-002: Integridad de datos
- Las operaciones financieras (cobro) usan transacciones atomicas.
- El precio unitario se registra como snapshot al momento de agregar el producto.
- Las relaciones ForeignKey usan PROTECT o CASCADE segun corresponda.

### RNF-003: Rendimiento
- Las consultas usan select_related y prefetch_related para evitar N+1.
- Los listados deben soportar paginacion minima de 25 registros.

## Casos Limite

1. **Mesa con orden activa:** No se puede crear otra orden para la misma mesa mientras exista una orden no terminal.
2. **Producto sin stock:** El sistema no valida inventario al agregar productos (fuera de alcance del MVP).
3. **Cobro con monto insuficiente:** Si el monto es menor al total, el cobro debe ser rechazado.
4. **Cobro duplicado:** No se puede cobrar dos veces la misma orden.
5. **Cancelacion con pago previo:** Si la orden ya tiene un pago registrado, no se puede cancelar.
6. **QR de mesa ocupada:** El QR solo funciona para mesas DISPONIBLES.
7. **Cliente sin mesa:** El cliente no puede crear una orden sin escanear el QR de una mesa.
8. **Transicion invalida:** Cualquier transicion no listada en RF-003 debe ser rechazada.
9. **Cobro con excedente:** Si el monto recibido supera el total de la orden, se acepta el pago completo. El excedente no se registra como cambio.

## Fuera de Alcance (MVP)

- Integracion con inventario (devolver ingredientes al cancelar).
- Notas o instrucciones especiales por producto o orden.
- Pagos parciales o division de cuenta.
- Propinas.
- Edicion o eliminacion de productos en una orden.
- Historial de cambios de estado (solo se actualiza updated_en).
- Exportacion de datos.
- Impresion de tickets.
- Transferencia de mesa.
- Tiempo estimado de preparacion.
- WebSocket o actualizaciones en tiempo real para cocina.

## Criterios de Finalizacion

1. Todos los requisitos funcionales RF-001 a RF-001 estan implementados.
2. Todos los hallazgos criticos y altos de VALIDACIONES.md relacionados con ordenes estan corregidos (H1, H2, H3, H4, H5, H6, H7).
3. Existen tests minimos para los flujos criticos (crear orden, cambiar estado, cobrar).
4. Las vistas tienen autenticacion y control de rol segun la matriz de permisos.
5. Las transiciones de estado estan validadas con un diccionario de transiciones permitidas.
6. El cobro valida estado LISTA (rechaza PENDIENTE, EN_PREPARACION, ENTREGADA, CANCELADA), unicidad de pago, monto >= total y maneja excedente.
7. La creacion de orden usa transaccion atomica y verifica que la mesa no tenga orden activa.

## Dudas Abiertas

[NECESITA ACLARACION] ¿Que debe ocurrir si el cliente intenta pedir desde el telefono pero la mesa ya esta ocupada por otra orden? ¿Debe ver un mensaje de error o no puede acceder al menu?

[NECESITA ACLARACION] ¿Debe permitirse al MESERO agregar productos a una orden en estado EN_PREPARACION o solo en PENDIENTE?

[NECESITA ACLARACION] ¿El JEFE_COCINA debe poder ver el detalle completo de una orden (productos, cantidades, precio) o solo mesa y productos?
