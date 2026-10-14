# Auditoría de Calidad y Seguridad — SmartBite

> Documento de auditoría que identifica hallazgos de seguridad, integridad de datos y mantenibilidad en el proyecto SmartBite.

---

## Tabla de Contenido

- [Contexto del Proyecto](#contexto-del-proyecto)
- [Hallazgos Propios del Proyecto](#hallazgos-propios-del-proyecto)
  - [Seguridad y Acceso (H1-H7)](#seguridad-y-acceso)
  - [Modelos y Validación (H8-H14)](#modelos-y-validación)
- [Hallazgos Generales](#hallazgos-generales)
  - [Configuración Django (G1-G5)](#configuración-django)
  - [Calidad del Código (G6-G10)](#calidad-del-código)
- [Resumen por Prioridad](#resumen-por-prioridad)
- [Plan de Acción Sugerido](#plan-de-acción-sugerido)

---

## Contexto del Proyecto

| Aspecto       | Detalle                                                  |
|---------------|----------------------------------------------------------|
| **Stack**     | Django 5.2 (Python), patrón MVT, server-rendered         |
| **BD**        | SQLite (db.sqlite3) en desarrollo                        |
| **Auth**      | Modelo propio `cuentas.Usuario` + sesiones de Django     |
| **QR**        | qrcode + Pillow                                          |
| **Frontend**  | Templates Django, CSS propio (theme.css), sin framework JS |
| **Apps**      | 11: core, cuentas, restaurantes, catalogo, inventario, recetas, operativo, caja, cocina, menu_cliente, reportes |
| **Roles**     | ADMINISTRADOR, JEFE_INVENTARIO, JEFE_COCINA, MESERO, CAJERO |
| **Dependencias** | Solo 3: Django>=5.2, qrcode>=7.4, Pillow>=10.0       |

---

## Hallazgos Propios del Proyecto

### Seguridad y Acceso

#### H1. Transiciones de estado de Orden sin validar
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `operativo/views.py:118-129` (`cambiar_estado_orden`) y `operativo/forms.py:39-40` |
| **Problema** | El formulario acepta cualquier estado. No valida transiciones: se puede cambiar de CANCELADA a EN_PREPARACION. |
| **Riesgo** | Reabrir órdenes canceladas, corromper historial de ventas, generar pagos duplicados. |
| **Prioridad** | CRÍTICA |
| **Corrección** | Validar transiciones en la vista con un diccionario `TRANSICIONES_VALIDAS`. |

#### H2. Cobrar orden sin verificar estado ni pagos previos
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `caja/views.py:22-46` (`cobrar_orden`) |
| **Problema** | No verifica estado LISTA ni si ya existe pago. El monto es editable sin validación. |
| **Riesgo** | Cobro de órdenes no preparadas, pagos duplicados, montos fraudulentos. |
| **Prioridad** | CRÍTICA |
| **Corrección** | Verificar estado, unicidad de pago y monto >= total. |

#### H3. `generar_qr` sin autenticación
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `operativo/views.py:132-145` |
| **Problema** | Sin `@login_required` ni `@rol_requerido`. Cualquiera genera QR de cualquier mesa. |
| **Riesgo** | Generación no autorizada de QRs, phishing. |
| **Prioridad** | ALTA |
| **Corrección** | Agregar `@rol_requerido("ADMINISTRADOR", "MESERO")`. |

#### H4. `crear_cliente_rapido` sin control de rol
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `operativo/views.py:80-85` |
| **Problema** | Sin autenticación ni control de rol. Usa `HTTP_REFERER` para redirect (open redirect). |
| **Riesgo** | Creación masiva de clientes, open redirect. |
| **Prioridad** | ALTA |
| **Corrección** | Agregar `@rol_requerido` y redirect a URL fija. |

#### H5. `crear_orden` sin protección atómica
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `operativo/views.py:54-77` |
| **Problema** | No verifica `mesa.orden_activa`, no usa `select_for_update()`, sin `transaction.atomic()`. |
| **Riesgo** | Dos órdenes activas en la misma mesa, datos inconsistentes. |
| **Prioridad** | ALTA |
| **Corrección** | Usar transacción atómica y bloqueo selectivo. |

#### H6. Compras con ítems de sucursales mixtas
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `inventario/views.py:123-140` |
| **Problema** | No asocia compra a sucursal. Permite ítems de sucursales diferentes. |
| **Riesgo** | Stock sumado a sucursal incorrecta, datos corruptos. |
| **Prioridad** | ALTA |
| **Corrección** | Asociar compra a sucursal y filtrar ítems. |

#### H7. Salida de inventario sin validar stock
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `inventario/views.py:42-65` |
| **Problema** | Stock se pone en 0 silenciosamente si `cantidad > stock_actual`. |
| **Riesgo** | Pérdida de integridad de datos de inventario. |
| **Prioridad** | ALTA |
| **Corrección** | Validar `cantidad <= stock_actual` antes de salida. |

---

### Modelos y Validación

#### H8. Auto-desactivación de cuenta
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `cuentas/views.py:57-64` |
| **Problema** | Admin puede desactivar su propia cuenta. |
| **Riesgo** | Auto-bloqueo del único administrador. |
| **Prioridad** | MEDIA |
| **Corrección** | Validar `usuario.pk != request.user.pk`. |

#### H9. Cantidad de ingrediente sin mínimo
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `recetas/models.py:6-22` |
| **Problema** | `cantidad_requerida` sin `min_value`. Unidades sin coherencia con inventario. |
| **Riesgo** | Recetas con cantidades negativas o cero. |
| **Prioridad** | MEDIA |
| **Corrección** | Agregar `MinValueValidator(0.001)`. |

#### H10. Clientes sin unicidad
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `operativo/models.py:28-38` |
| **Problema** | Sin `unique_together`. Duplicación masiva posible. |
| **Riesgo** | BD saturada de registros duplicados. |
| **Prioridad** | MEDIA |
| **Corrección** | Agregar `unique_together = [("nombre", "telefono", "email")]`. |

#### H11. Productos sin unicidad por sucursal
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `catalogo/models.py:16-31` |
| **Problema** | Sin `unique_together` en `(nombre, sucursal)`. |
| **Riesgo** | Productos duplicados en menú, confusión en órdenes. |
| **Prioridad** | MEDIA |
| **Corrección** | Agregar `unique_together = [("nombre", "sucursal")]`. |

#### H12. Sin paginación en listados
| Campo | Detalle |
|-------|---------|
| **Ubicación** | Todas las `ListView` |
| **Problema** | Ninguna vista usa `paginate_by`. |
| **Riesgo** | Degradación de rendimiento con datos crecientes. |
| **Prioridad** | MEDIA |
| **Corrección** | Agregar `paginate_by = 25`. |

#### H13. Menú público sin validación robusta
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `menu_cliente/views.py:7-20` |
| **Problema** | Parámetro `mesa` no valida `ValueError`. Sin rate limiting. |
| **Riesgo** | Error 500 explotable, exposición del catálogo completo. |
| **Prioridad** | MEDIA |
| **Corrección** | Capturar `ValueError` y validar parámetro. |

#### H14. Logout acepta GET
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `cuentas/views.py:21-22` |
| **Problema** | `LogoutView` acepta GET (CSRF logout attack). |
| **Riesgo** | Cierre de sesión no autorizado vía `<img>` tag. |
| **Prioridad** | BAJA |
| **Corrección** | Sobreescribir GET para que use POST. |

---

## Hallazgos Generales

### Configuración Django

#### G1. `SECRET_KEY` hardcodeada
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `smartbite/settings.py:23` |
| **Problema** | Clave secreta embebida en código fuente. |
| **Riesgo** | Forjado de sesiones y cookies CSRF. |
| **Prioridad** | CRÍTICA |
| **Corrección** | Leer de variable de entorno `DJANGO_SECRET_KEY`. |

#### G2. `DEBUG=True` hardcodeado
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `smartbite/settings.py:26` |
| **Problema** | Sin control por entorno. |
| **Riesgo** | Stack traces completos expuestos en errores. |
| **Prioridad** | CRÍTICA |
| **Corrección** | Leer de variable de entorno. |

#### G3. `ALLOWED_HOSTS` vacío
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `smartbite/settings.py:28` |
| **Problema** | Lista vacía. |
| **Riesgo** | Host header injection, sitio no funciona con `DEBUG=False`. |
| **Prioridad** | ALTA |
| **Corrección** | Configurar desde variable de entorno. |

#### G4. Sin configuración HTTPS/cookies seguras
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `smartbite/settings.py` (falta bloque completo) |
| **Problema** | No hay `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_*`. |
| **Riesgo** | Cookies robables via sniffing, clickjacking, MitM. |
| **Prioridad** | CRÍTICA |
| **Corrección** | Agregar bloque de seguridad condicional a `DEBUG`. |

#### G5. Sin rate limiting
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `cuentas/views.py` + `settings.py` |
| **Problema** | No hay throttolding en login ni endpoints. |
| **Riesgo** | Fuerza bruta, denegación de servicio. |
| **Prioridad** | ALTA |
| **Corrección** | Instalar `django-axes`. |

---

### Calidad del Código

#### G6. Tests completamente vacíos
| Campo | Detalle |
|-------|---------|
| **Ubicación** | Todos los `tests.py` (11 archivos) |
| **Problema** | No hay UN SOLO test en todo el proyecto. |
| **Riesgo** | Imposible detectar regresiones, refactorizar con confianza. |
| **Prioridad** | CRÍTICA |
| **Corrección** | Crear tests para flujos críticos. |

#### G7. Sin `LOGGING` configurado
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `smartbite/settings.py` |
| **Problema** | No existe bloque `LOGGING`. |
| **Riesgo** | Imposible investigar incidentes, debug en producción. |
| **Prioridad** | ALTA |
| **Corrección** | Configurar logging básico. |

#### G8. Sin validadores custom en formularios
| Campo | Detalle |
|-------|---------|
| **Ubicación** | Múltiples `forms.py` |
| **Problema** | Sin validación de NIF, teléfono, email, URL de logo. |
| **Riesgo** | Datos inválidos en campos críticos. |
| **Prioridad** | MEDIA |
| **Corrección** | Agregar validadores y hacer campos críticos `required=True`. |

#### G9. Falta `STATIC_ROOT`
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `smartbite/settings.py` |
| **Problema** | No definido. |
| **Riesgo** | `collectstatic` falla en producción. |
| **Prioridad** | BAJA |
| **Corrección** | `STATIC_ROOT = BASE_DIR / 'staticfiles'`. |

#### G10. `DetalleOrden` sin `TimestampedModel`
| Campo | Detalle |
|-------|---------|
| **Ubicación** | `operativo/models.py:76-87` |
| **Problema** | Hereda de `models.Model` directamente, sin trazabilidad temporal. |
| **Riesgo** | Sin auditoría de cambios. |
| **Prioridad** | BAJA |
| **Corrección** | Cambiar herencia a `TimestampedModel`. |

---

## Resumen por Prioridad

### CRÍTICA (6)

| # | Hallazgo | Ubicación |
|---|----------|-----------|
| H1 | Transiciones de Orden sin validar | `operativo/views.py:118` |
| H2 | Cobrar sin verificar estado/montos | `caja/views.py:22` |
| G1 | SECRET_KEY hardcodeada | `settings.py:23` |
| G2 | DEBUG=True hardcodeado | `settings.py:26` |
| G4 | Sin config HTTPS/cookies | `settings.py` |
| G6 | Tests completamente vacíos | Todos `tests.py` |

### ALTA (7)

| # | Hallazgo | Ubicación |
|---|----------|-----------|
| H3 | `generar_qr` sin autenticación | `operativo/views.py:132` |
| H4 | `crear_cliente_rapido` sin rol | `operativo/views.py:80` |
| H5 | `crear_orden` sin protección atómica | `operativo/views.py:54` |
| H6 | Compras con ítems mixtos | `inventario/views.py:123` |
| H7 | Salida sin validar stock | `inventario/views.py:42` |
| G3 | ALLOWED_HOSTS vacío | `settings.py:28` |
| G7 | Sin LOGGING | `settings.py` |
| G5 | Sin rate limiting | `cuentas/views.py + settings.py` |

### MEDIA (7)

| # | Hallazgo | Ubicación |
|---|----------|-----------|
| H8 | Auto-desactivación | `cuentas/views.py:57` |
| H9 | Cantidad sin mínimo | `recetas/models.py:13` |
| H10 | Clientes sin unicidad | `operativo/models.py:28` |
| H11 | Productos sin unicidad | `catalogo/models.py:16` |
| H12 | Sin paginación | Todas `ListView` |
| H13 | Menú público sin validación | `menu_cliente/views.py:7` |
| G8 | Sin validadores custom | Múltiples `forms.py` |

### BAJA (3)

| # | Hallazgo | Ubicación |
|---|----------|-----------|
| H14 | Logout acepta GET | `cuentas/views.py:21` |
| G9 | Falta STATIC_ROOT | `settings.py` |
| G10 | DetalleOrden sin TimestampedModel | `operativo/models.py:76` |

---

## Plan de Acción Sugerido

### Fase 1 — Seguridad inmediata (Sprint 1)
1. Mover `SECRET_KEY` a variable de entorno (G1)
2. Controlar `DEBUG` por variable de entorno (G2)
3. Configurar `ALLOWED_HOSTS` (G3)
4. Agregar bloque de seguridad HTTPS/cookies (G4)
5. Proteger `generar_qr` con `@rol_requerido` (H3)
6. Proteger `crear_cliente_rapido` y cerrar open redirect (H4)
7. Instalar `django-axes` para rate limiting (G5)

### Fase 2 — Integridad de datos (Sprint 2)
1. Validar transiciones de estado de Orden (H1)
2. Validar estado y monto al cobrar (H2)
3. Validar stock antes de salida de inventario (H7)
4. Proteger `crear_orden` con transacción atómica (H5)
5. Validar consistencia de sucursal en compras (H6)

### Fase 3 — Calidad y mantenibilidad (Sprint 3)
1. Escribir tests mínimos para flujos críticos (G6)
2. Agregar paginación a vistas de listado (H12)
3. Agregar `unique_together` a Cliente y Producto (H10, H11)
4. Agregar validadores a formularios (G8)
5. Configurar LOGGING (G7)
6. Prevenir auto-desactivación (H8)

### Fase 4 — Pulido y deuda técnica (Sprint 4)
1. Corregir validación de parámetro `mesa` en menú público (H13)
2. Agregar `min_value` a `cantidad_requerida` (H9)
3. Hacer `LogoutView` reject GET (H14)
4. Agregar `STATIC_ROOT` (G9)
5. Hacer `DetalleOrden` y `DetalleCompra` heredar de `TimestampedModel` (G10)
