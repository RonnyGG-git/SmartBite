# ADR 0001 — Tipos de datos para cantidades y montos en Inventario

> Estado: aprobada 2026-09-23

## Contexto
El modelo Django actual (`inventario.ItemInventario.stock_actual`) usa
`PositiveIntegerField`, pero `unidad_medida` incluye `kg` y `L`, que en la
operación real de un restaurante se manejan con fracciones (2.5 kg de
harina, 0.75 L de aceite). La Spec 001 no fija el tipo de dato para
cantidades ni para montos — es una decisión estructural que toca definir
antes de escribir las tablas (constitución, principio 9).

## Opciones
- **A. Enteros** (como hoy): simple, pero no permite unidades fraccionarias
  reales — un insumo medido en kg queda mal representado.
- **B. `NUMERIC` con precisión fija**: soporta decimales con precisión
  exacta, sin errores de redondeo.
- **C. `FLOAT` / `DOUBLE PRECISION`**: descartada de entrada — los errores
  de redondeo de punto flotante son inaceptables para stock y dinero.

## Decisión
Opción B: `NUMERIC(12,3)` para cantidades de insumo (stock, cantidades de
movimiento) y `NUMERIC(10,2)` para montos (costo unitario) — consistente
con el `DecimalField(max_digits=10, decimal_places=2)` que ya usa el resto
del proyecto para precios (`catalogo.Producto.precio`,
`inventario.ItemInventario.costo_unitario`).

## Consecuencias
- Los `models.py` de Django que correspondan migrarán `stock_actual` /
  `stock_minimo` de `PositiveIntegerField` a `DecimalField` para reflejar
  el nuevo esquema (tarea posterior a este plan, no de esta ronda).
- `NUMERIC` admite valores negativos por tipo — la regla "el stock nunca es
  negativo" (RF-20) se aplica con una restricción `CHECK`, no con el tipo
  de dato.
