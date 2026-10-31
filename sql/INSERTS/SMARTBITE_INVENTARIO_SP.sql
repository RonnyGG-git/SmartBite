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
