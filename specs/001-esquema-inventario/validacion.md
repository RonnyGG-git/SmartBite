# Validación — Spec 001 (Esquema de datos de Inventario)

Fecha: 2026-09-23 · Suite: `pytest sql/tests` → 71 tests en verde, contra la
rama de Neon `test-inventario-jose` (no la base real del equipo).

## RF por RF

| RF | Prueba directa | Resultado |
|---|---|---|
| RF-1 | `test_codigo_unico.py::test_genera_codigo_con_prefijo_de_categoria` | OK |
| RF-2 | `test_item_inventario.py::test_rechaza_nombre_duplicado_en_misma_sucursal_sin_importar_mayusculas` | OK |
| RF-3 | `test_item_inventario.py::test_rechaza_insumo_sin_categoria` | OK |
| RF-4 | `test_historial.py::test_actualizar_dos_campos_crea_dos_filas_de_historial` | OK |
| RF-5 | `test_item_inventario.py::test_desactivar_insumo` | OK |
| RF-6 | — | **No implementado**: depende de la tabla `compra`, que no existe (fuera de esta ronda). Documentado desde T3, no es un olvido. |
| RF-7 | `test_item_inventario.py::test_rechaza_redesactivar_insumo_ya_inactivo` | OK |
| RF-8 | `test_item_inventario.py::test_consultar_insumos_filtrando_por_nombre` + `test_consultar_insumos_filtrando_por_categoria_estado_y_sucursal` | OK |
| RF-9 | `test_item_inventario.py::test_configurar_stock_minimo_por_insumo` | OK |
| RF-10 | `test_consultas_derivadas.py::test_control_existencias_incluye_insumo_bajo_minimo` + `test_control_existencias_respeta_sucursal` | OK |
| RF-11 | `test_consultas_derivadas.py::test_control_existencias_excluye_insumo_sin_minimo_configurado` | OK |
| RF-12 | `test_aplicar_movimiento.py::test_entrada_incrementa_stock_real` + `test_entrada_sin_compra_cubre_el_stock_inicial` + `test_entrada_con_compra_id_se_guarda` | OK |
| RF-13 | `test_aplicar_movimiento.py::test_salida_descuenta_stock_real` | OK |
| RF-14 | `test_aplicar_movimiento.py::test_salida_rechaza_si_excede_stock_disponible` | OK |
| RF-15 | `test_movimiento_inventario.py::test_insertar_ajuste_valido_con_motivo` + `test_ajuste_aprobacion.py::test_ajuste_bajo_el_umbral_se_aplica_de_inmediato` | OK |
| RF-16 | `test_movimiento_inventario.py::test_rechaza_ajuste_sin_motivo` | OK |
| RF-17 | `test_ajuste_aprobacion.py` (4 tests: umbral, pendiente, aprobación, umbral configurable) | OK |
| RF-18 | `test_movimiento_inventario.py::test_kardex_registra_fecha_usuario_insumo_tipo_y_cantidad` | OK |
| RF-19 | `test_movimiento_inventario.py::test_consultar_movimientos_filtrando_por_insumo_tipo_y_fecha` | OK |
| RF-20 | `test_item_inventario.py::test_rechaza_stock_negativo` + `test_aplicar_movimiento.py::test_dos_salidas_concurrentes_no_dejan_stock_negativo` | OK |
| RF-21 | `test_consultas_derivadas.py::test_proximos_a_vencer_incluye_insumo_dentro_del_rango` + `test_proximos_a_vencer_excluye_insumo_sin_fecha_vencimiento` | OK |
| RF-22 | `test_consultas_derivadas.py::test_proximos_a_vencer_usa_default_de_7_dias_si_no_esta_configurado` | OK |
| RF-23 | `test_consultas_derivadas.py::test_proximos_a_vencer_incluye_insumo_dentro_del_rango` + `test_proximos_a_vencer_excluye_insumo_fuera_del_rango` | OK |
| RF-24 | `test_perdidas.py::test_perdida_manual_descuenta_stock` | OK |
| RF-25 | `test_perdidas.py::test_perdida_manual_rechaza_si_excede_stock` | OK |
| RF-26 | `test_perdidas.py::test_generar_perdidas_vencimiento_insumo_vencido_sin_usar` | OK |
| RF-27 | `test_consultas_derivadas.py::test_disponibilidad_*` (4 tests) | OK |
| RF-28 | `test_solicitud_reabastecimiento.py::test_salida_bajo_minimo_genera_solicitud` | OK |
| RF-29 | `test_solicitud_reabastecimiento.py::test_no_genera_segunda_solicitud_mientras_la_primera_sigue_pendiente` | OK |
| RF-30 | `test_reporte_inventario.py` (filtra por categoría/estado/fechas, 3 tests) | OK |
| RF-31 | — | **Fuera de alcance del esquema** (spec, "Fuera de alcance"): exportación es de la capa de aplicación. No aplica una prueba SQL. |
| RF-32 | `test_reporte_inventario.py::test_reporte_sin_coincidencias_devuelve_vacio` | OK |
| RF-33 | `test_consultas_derivadas.py::test_control_existencias_excluye_insumo_inactivo` | OK |
| RF-34 | `test_consultas_derivadas.py::test_proximos_a_vencer_excluye_insumo_inactivo` | OK |
| RF-35 | `test_consultas_derivadas.py::test_disponibilidad_insumo_inactivo_siempre_false` | OK |
| RF-36 | `test_solicitud_reabastecimiento.py::test_dos_salidas_concurrentes_generan_una_sola_solicitud` (concurrencia real, 2 conexiones) | OK |
| RF-37 | `test_codigo_unico.py::test_rechaza_modificar_codigo_unico` | OK |
| RF-38 | `test_perdidas.py::test_rechaza_segunda_perdida_manual_por_vencimiento_el_mismo_dia` + `test_permite_perdida_manual_por_otra_causa_el_mismo_dia` | OK |

**Cobertura indirecta detectada y cerrada en esta fase** (regla de la fase
7: un RF probado solo porque se probó el mecanismo de abajo no cuenta):
RF-3, RF-8 (nombre), RF-9, RF-10 (alcance por sucursal) y RF-18 solo tenían
tests que los ejercitaban de paso, no que los probaran directamente. Se
agregaron 5 tests nuevos para cerrarlos (71 tests en total, antes 66).

## Criterios de finalización (de la spec)
- [x] Cada RF tiene una prueba directa — 36 de 38 (`RF-6` y `RF-31` son
      exclusiones documentadas, no huecos: `RF-6` depende de una tabla que
      no existe todavía en esta ronda; `RF-31` está explícitamente fuera de
      alcance del esquema en la propia spec).
- [x] El script SQL corre limpio contra una base Neon de prueba y soporta
      insertar/consultar/actualizar datos cumpliendo cada RF — confirmado
      en cada tarea (T1 a T13) contra la rama `test-inventario-jose`, nunca
      contra la base real del equipo.
- [ ] Los `models.py` de Django que correspondan quedan alineados con el
      esquema aplicado en Neon — **no se hizo en esta ronda**. Ninguna
      tarea de `tasks.md` (T1-T14) incluyó tocar `inventario/models.py` —
      es un criterio de la spec que quedó fuera del plan de tareas real.
      Se necesita una ronda de trabajo aparte (no forma parte de "spec
      cumplida" a nivel de esquema SQL, que es lo que cubrieron T1-T13).

## Veredicto

**Spec cumplida a nivel de esquema SQL** (36/38 RF con prueba directa en
verde; los 2 restantes son exclusiones explícitas de esta ronda, no
huecos silenciosos). Antes de dar la ronda completa por cerrada, falta un
trabajo aparte y explícito: actualizar `inventario/models.py` (y sus
migraciones) para reflejar `categoria_insumo`, `item_inventario`,
`item_inventario_historial`, `movimiento_inventario` y
`solicitud_reabastecimiento` — el tercer criterio de finalización de la
spec, que ninguna tarea de esta ronda cubrió.
