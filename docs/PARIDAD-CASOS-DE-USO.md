# Paridad con el diagrama de casos de uso

Contrasta el código de Smart Bite con el diagrama
`CEREBRO/04 Arquitectura/DIAGRAMAS/casos-de-uso-pos-restaurante/` (7 módulos,
114 casos de uso, códigos `CU-<MÓDULO>-NN` de `LOGICA-DE-NEGOCIO.md`).

Revisado el 2026-09-27, después de crear la app `cliente`.

**Leyenda:** ✅ implementado · 🟡 parcial (se indica qué falta) · ❌ no existe

## Resumen

| Módulo del diagrama | Casos | ✅ | 🟡 | ❌ | Dónde vive en el código |
|---|---:|---:|---:|---:|---|
| Pedidos | 23 | 18 | 5 | 0 | `cliente`, `operativo`, `cocina` |
| Pagos | 16 | 5 | 4 | 7 | `caja` |
| Facturación | 10 | 0 | 0 | 10 | — (no existe) |
| Administración | 16 | 9 | 3 | 4 | `cuentas`, `restaurantes`, `reportes`, `cliente` |
| Inventario | 17 | 11 | 3 | 3 | `inventario` |
| Menú | 12 | 10 | 1 | 1 | `catalogo`, `recetas` |
| Compras | 20 | 3 | 0 | 17 | `inventario` (compras) |
| **Total** | **114** | **56** | **16** | **42** | |

## Correspondencia de actores y roles

| Actor del diagrama | Rol en el sistema | Nota |
|---|---|---|
| Cliente | — (sin login) | App `cliente`: la mesa se identifica por QR y los pedidos se recuerdan en la sesión. |
| Mesero | `MESERO` | |
| Chef/Cocinero | `JEFE_COCINA` | |
| Cajero | `CAJERO` | |
| Jefe de Almacén | `JEFE_INVENTARIO` | |
| Administrador | `ADMINISTRADOR` | |
| Proveedor, DIAN, Pasarela de pago | — | Actores externos sin integración. |

> **Roles del Módulo de Menú:** platillos y categorías los gestionan
> `ADMINISTRADOR` y `JEFE_COCINA` (Chef), como indica el diagrama
> (CU-MEN-01/02/04/05). El Jefe de Inventario solo los consulta.

## 1. Pedidos

| Código | Caso de uso | Estado | Implementación / qué falta |
|---|---|---|---|
| CU-PED-01 | Consultar menú disponible | ✅ | `cliente:menu` — solo platillos disponibles de la sucursal de la mesa. |
| CU-PED-02 | Seleccionar platillos | ✅ | Selector de cantidades del autopedido; `operativo:agregar_producto` para el mesero. |
| CU-PED-03 | Registrar pedido en mesa | ✅ | `operativo:crear_orden`. |
| CU-PED-04 | Asignar mesa a cliente | 🟡 | Ocurre implícitamente al crear la orden (mesa → OCUPADA). No hay acción propia ni flujo para `RESERVADA`. |
| CU-PED-05 | Realizar autopedido | ✅ | `cliente:autopedido` (incluye 02 y 08). |
| CU-PED-06 | Modificar pedido | 🟡 | Solo *agregar* productos mientras la orden está PENDIENTE. Falta quitar productos o cambiar cantidades. |
| CU-PED-07 | Cancelar pedido | ✅ | Mesero, solo con la orden PENDIENTE (antes de prepararse). |
| CU-PED-08 | Enviar pedido a cocina | ✅ | Toda orden nueva entra PENDIENTE a la cola de `cocina`. |
| CU-PED-09 | Consultar pedidos en cola | ✅ | `cocina:cocina`. |
| CU-PED-10 | Actualizar estado de preparación | ✅ | `cocina:actualizar_estado` (solo Chef/Admin). |
| CU-PED-11 | Confirmar pedido listo | ✅ | Acción "Marcar listo" en el ticket. |
| CU-PED-12 | Reportar insumo faltante | 🟡 | El ticket muestra "Stock insuficiente: …". No genera un aviso registrado para Inventario. |
| CU-PED-13 | Consultar estado del pedido | ✅ | `cliente:pedido` (se actualiza cada 30 s, muestra hora estimada). |
| CU-PED-14 | Solicitar cuenta | ✅ | `operativo:solicitar_cuenta` (orden LISTA). |
| CU-PED-15 | Enviar total del pedido | ✅ | La orden aparece en `caja:por_cobrar` con su total. |
| CU-PED-16 | Escanear código QR de mesa | ✅ | `cliente:mesa`; el QR de `operativo:generar_qr` apunta ahí. `/menu/?mesa=N` redirige (QR ya impresos). |
| CU-PED-17 | Enviar retroalimentación | ✅ | `cliente:retroalimentacion` (modelo `Retroalimentacion`). |
| CU-PED-18 | Enviar sugerencia | ✅ | Tipo `SUGERENCIA`. |
| CU-PED-19 | Registrar denuncia | ✅ | Tipo `DENUNCIA`. |
| CU-PED-20 | Consultar pedidos pendientes | 🟡 | La vista Mesas muestra la orden activa de cada mesa. Falta un tablero propio del mesero (p. ej. órdenes LISTAS por servir). |
| CU-PED-21 | Desasignar mesa a cliente | 🟡 | Solo al cancelar o cobrar. Falta liberar una mesa ocupada sin orden. |
| CU-PED-22 | Verificar disponibilidad de ingredientes | ✅ | `cocina.views.insumos_faltantes` (receta × cantidad vs stock). No descuenta stock. |
| CU-PED-23 | Establecer tiempo estimado de preparación | ✅ | Se fija al iniciar la preparación; lo ve el cliente. |

## 2. Pagos

| Código | Caso de uso | Estado | Implementación / qué falta |
|---|---|---|---|
| CU-PAG-01 | Realizar pago | ✅ | `caja:cobrar_orden`. |
| CU-PAG-02 | Pagar en efectivo | ✅ | Método de pago "Efectivo". |
| CU-PAG-03 | Pagar con tarjeta o billetera digital | 🟡 | Se registra el método y la referencia; no hay pasarela. |
| CU-PAG-04 | Enviar datos de pago | ❌ | Requiere integración con pasarela. |
| CU-PAG-05 | Confirmar pago | 🟡 | Implícito al registrar el pago. |
| CU-PAG-06 | Enviar confirmación de pago | 🟡 | La orden pasa a ENTREGADA y la mesa se libera; no hay comprobante. |
| CU-PAG-07 | Aplicar descuento o promoción | ❌ | |
| CU-PAG-08 | Dividir cuenta entre comensales | ❌ | El modelo admite varios `Pago` por orden, pero el cobro cierra la orden con el primero. |
| CU-PAG-09 | Solicitar factura | ❌ | Depende del módulo de Facturación. |
| CU-PAG-10 | Registrar venta | ✅ | Pago + orden ENTREGADA = venta (`caja:ventas_list`). |
| CU-PAG-11 | Actualizar venta | ❌ | |
| CU-PAG-12 | Enviar datos de venta | 🟡 | El dashboard y los reportes leen las ventas; no hay envío explícito. |
| CU-PAG-13 | Consultar historial de ventas | ✅ | `caja:ventas_list`, `caja:pagos_list`. |
| CU-PAG-14 | Abrir caja | ❌ | |
| CU-PAG-15 | Cerrar caja | ❌ | |
| CU-PAG-16 | Confirmar pedido | ✅ | `caja:por_cobrar`. |

## 3. Facturación

Ningún caso de uso implementado (CU-FAC-01 a CU-FAC-10: generar, calcular
impuestos, validar y emitir ante la DIAN, factura física y por correo, anular,
historial, reportar rechazo). Requiere un módulo nuevo y la integración con un
proveedor tecnológico de facturación electrónica de la DIAN.

## 4. Administración

| Código | Caso de uso | Estado | Implementación / qué falta |
|---|---|---|---|
| CU-ADM-01 | Registrar usuario | ✅ | `cuentas:usuario_crear`. |
| CU-ADM-02 | Consultar usuario | ✅ | `cuentas:usuarios_list`. |
| CU-ADM-03 | Actualizar usuario | ✅ | `cuentas:usuario_editar`. |
| CU-ADM-04 | Eliminar usuario | 🟡 | La ruta `usuario_eliminar` existe, pero la lista solo ofrece activar/desactivar. |
| CU-ADM-05 | Asignar rol | ✅ | Campo `rol` del formulario de usuario. |
| CU-ADM-06 | Gestionar permisos | ✅ | `cuentas:rol_permisos`. |
| CU-ADM-07 | Consultar actividad del sistema | ❌ | No hay bitácora. |
| CU-ADM-08 | Configurar sistema | ❌ | Solo el admin de Django. |
| CU-ADM-09 | Gestionar información del restaurante | ✅ | `restaurantes`. |
| CU-ADM-10 | Generar reporte administrativo | 🟡 | Dashboard y reportes en pantalla; sin exportar. |
| CU-ADM-11 | Gestionar turnos de trabajo | ❌ | |
| CU-ADM-12 | Consultar ventas | ✅ | Dashboard, reportes, ventas. |
| CU-ADM-13 | Consultar inventario | ✅ | Dashboard (stock bajo) e inventario. |
| CU-ADM-14 | Consultar indicadores de desempeño | 🟡 | KPIs del día en el dashboard; sin históricos. |
| CU-ADM-15 | Definir promociones y descuentos | ❌ | |
| CU-ADM-16 | Revisar sugerencias y denuncias | ✅ | `cliente:retroalimentacion_list` (marcar revisada). |

## 5. Inventario

| Código | Caso de uso | Estado | Implementación / qué falta |
|---|---|---|---|
| CU-INV-01 | Registrar producto | ✅ | `inventario:item_crear`. |
| CU-INV-02 | Consultar inventario | ✅ | `inventario:inventario_list`. |
| CU-INV-03 | Actualizar producto | ✅ | `inventario:item_editar`. |
| CU-INV-04 | Controlar existencias | ✅ | `ItemInventario.stock_bajo`. |
| CU-INV-05 | Registrar entrada de inventario | ✅ | Ajuste de entrada y recepción de compra. |
| CU-INV-06 | Registrar salida de inventario | ✅ | Ajuste de salida. |
| CU-INV-07 | Consultar movimientos de inventario | ✅ | `inventario:movimientos_list`. |
| CU-INV-08 | Realizar ajuste de inventario | ✅ | `inventario:item_ajustar`. |
| CU-INV-09 | Controlar productos próximos a vencer | ❌ | No hay fecha de vencimiento en el modelo. |
| CU-INV-10 | Registrar pérdida de producto | 🟡 | Se puede registrar como salida con motivo; no hay tipo "pérdida". |
| CU-INV-11 | Consultar stock mínimo | ✅ | Campo `stock_minimo`. |
| CU-INV-12 | Generar reporte de inventario | 🟡 | Solo el listado de stock bajo del dashboard. |
| CU-INV-13 | Clasificar producto por categoría | ❌ | `ItemInventario` no tiene categoría. |
| CU-INV-14 | Consultar stock disponible | ✅ | Inventario y recetas. |
| CU-INV-15 | Enviar solicitud de reabastecimiento | 🟡 | Se crea una compra a mano; no hay solicitud automática desde el stock mínimo. |
| CU-INV-16 | Desactivar producto | ❌ | `ItemInventario` no tiene campo `activo`. |
| CU-INV-17 | Registrar movimiento de inventario | ✅ | `MovimientoInventario`. |

## 6. Menú

| Código | Caso de uso | Estado | Implementación / qué falta |
|---|---|---|---|
| CU-MEN-01 | Gestionar catálogo de platillos | ✅ | `catalogo` (Administrador y Chef). |
| CU-MEN-02 | Agregar platillo | ✅ | |
| CU-MEN-03 | Definir receta e insumos | ✅ | `recetas` (Chef). |
| CU-MEN-04 | Actualizar platillo | ✅ | |
| CU-MEN-05 | Eliminar platillo | ✅ | |
| CU-MEN-06 | Actualizar menú | ✅ | Implícito: el menú del cliente se arma en vivo. |
| CU-MEN-07 | Definir precio de platillo | 🟡 | El precio va en el formulario del producto; sin aprobación del Administrador. |
| CU-MEN-08 | Consultar disponibilidad de platillo | ✅ | Flag `disponible` + stock de receta en cocina. |
| CU-MEN-09 | Consultar platillo | ✅ | |
| CU-MEN-10 | Enviar disponibilidad del platillo | ✅ | El menú del cliente solo muestra los disponibles. |
| CU-MEN-11 | Enviar información del platillo | ✅ | |
| CU-MEN-12 | Diseñar menú de temporada o promoción | ❌ | |

## 7. Compras

| Código | Caso de uso | Estado | Implementación / qué falta |
|---|---|---|---|
| CU-COM-11 | Generar orden de compra | ✅ | `inventario:compra_crear`. |
| CU-COM-13 | Recibir productos entregados | ✅ | `inventario:compra_recibir` (suma stock). |
| CU-COM-20 | Consultar historial de compras | ✅ | `inventario:compras_list`. |
| CU-COM-01…10, 16, 17 | Casos del actor Proveedor | ❌ | No hay portal ni integración con proveedores. |
| CU-COM-12 | Aprobar orden de compra | ❌ | La compra pasa de PENDIENTE a RECIBIDA sin aprobación del Administrador. |
| CU-COM-14 | Verificar calidad de insumos | ❌ | |
| CU-COM-15 | Solicitar devolución de producto | ❌ | Solo existe "anular compra". |
| CU-COM-18 | Registrar pago a proveedor | ❌ | |
| CU-COM-19 | Evaluar desempeño del proveedor | ❌ | |
