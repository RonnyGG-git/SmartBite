-- Smart Bite — Datos semilla de Inventario
-- Fuente: specs/001-esquema-inventario/plan.md ("Módulos": categorías base
-- de ejemplo, sin insumos ficticios de negocio real — un insumo real
-- necesita una sucursal real, que todavía no existe en este esquema).
-- Seguro de re-ejecutar (ON CONFLICT DO NOTHING): no duplica categorías
-- si el script se corre más de una vez.

INSERT INTO categoria_insumo (nombre) VALUES
    ('Lácteos'),
    ('Cárnicos'),
    ('Panadería'),
    ('Bebidas'),
    ('Frutas y Verduras'),
    ('Abarrotes'),
    ('Limpieza'),
    ('Desechables')
ON CONFLICT (nombre) DO NOTHING;
