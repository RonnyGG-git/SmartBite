CREATE OR REPLACE FUNCTION fn_marcar_actualizado_en()
RETURNS TRIGGER AS $$
BEGIN
    NEW.actualizado_en := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_rechazar_cambio_auditoria()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% es de solo agregar (auditoría): no se permite %. Para corregir el stock, registrar un AJUSTE',
        TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE categoria_insumo (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_categoria_insumo_nombre UNIQUE (nombre)
);

CREATE TRIGGER trg_categoria_insumo_actualizado_en
    BEFORE UPDATE ON categoria_insumo
    FOR EACH ROW
    EXECUTE FUNCTION fn_marcar_actualizado_en();

CREATE TABLE item_inventario (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_unico            VARCHAR(30) NOT NULL,
    nombre                  VARCHAR(150) NOT NULL,
    descripcion             VARCHAR(255),
    unidad_medida           VARCHAR(20) NOT NULL,
    categoria_id            BIGINT NOT NULL REFERENCES categoria_insumo(id),
    sucursal_id             BIGINT NOT NULL,
    stock_actual            NUMERIC(12,3) NOT NULL DEFAULT 0,
    stock_minimo            NUMERIC(12,3),
    costo_unitario          NUMERIC(10,2) NOT NULL DEFAULT 0,
    fecha_vencimiento       DATE,
    dias_alerta_vencimiento INTEGER,
    activo                  BOOLEAN NOT NULL DEFAULT true,
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_item_inventario_codigo UNIQUE (sucursal_id, codigo_unico),
    CONSTRAINT ck_item_inventario_stock_no_negativo CHECK (stock_actual >= 0),
    CONSTRAINT ck_item_inventario_costo_no_negativo CHECK (costo_unitario >= 0),
    CONSTRAINT ck_item_inventario_minimo_no_negativo CHECK (stock_minimo >= 0),
    CONSTRAINT ck_item_inventario_dias_alerta_no_negativo CHECK (dias_alerta_vencimiento >= 0)
);

CREATE UNIQUE INDEX uq_item_inventario_nombre_sucursal
    ON item_inventario (sucursal_id, lower(btrim(nombre)));

CREATE TRIGGER trg_item_inventario_actualizado_en
    BEFORE UPDATE ON item_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_marcar_actualizado_en();

CREATE OR REPLACE FUNCTION fn_item_inventario_validar_desactivacion()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.activo = false AND NEW.activo = false THEN
        RAISE EXCEPTION 'El insumo % ya está inactivo', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_item_inventario_validar_desactivacion
    BEFORE UPDATE OF activo ON item_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_item_inventario_validar_desactivacion();

CREATE OR REPLACE FUNCTION fn_item_inventario_proteger_stock()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.stock_actual > 0 THEN
        RAISE EXCEPTION 'Un insumo se crea con stock 0: el stock inicial se registra con un movimiento ENTRADA (RF-12)';
    ELSIF TG_OP = 'UPDATE' AND NEW.stock_actual IS DISTINCT FROM OLD.stock_actual
          AND pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'stock_actual del insumo % solo cambia registrando un movimiento de inventario', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_item_inventario_proteger_stock
    BEFORE INSERT OR UPDATE ON item_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_item_inventario_proteger_stock();

CREATE OR REPLACE FUNCTION fn_item_inventario_generar_codigo()
RETURNS TRIGGER AS $$
DECLARE
    prefijo   VARCHAR(3);
    siguiente INTEGER;
BEGIN
    SELECT left(regexp_replace(upper(translate(nombre, 'ÁÉÍÓÚÑÜáéíóúñü', 'AEIOUNUaeiounu')),
                               '[^A-Z]', '', 'g'), 3)
    INTO prefijo
    FROM categoria_insumo WHERE id = NEW.categoria_id;
    prefijo := COALESCE(NULLIF(prefijo, ''), 'INS');

    PERFORM pg_advisory_xact_lock(hashtext('item_inventario.codigo_unico:' || NEW.sucursal_id || ':' || prefijo));

    SELECT COALESCE(MAX(CAST(split_part(codigo_unico, '-', 2) AS INTEGER)), 0) + 1
    INTO siguiente
    FROM item_inventario
    WHERE sucursal_id = NEW.sucursal_id
      AND codigo_unico LIKE prefijo || '-%';

    NEW.codigo_unico := prefijo || '-' || lpad(siguiente::text, 5, '0');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_item_inventario_generar_codigo
    BEFORE INSERT ON item_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_item_inventario_generar_codigo();

CREATE OR REPLACE FUNCTION fn_item_inventario_codigo_inmutable()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.codigo_unico IS DISTINCT FROM OLD.codigo_unico THEN
        RAISE EXCEPTION 'codigo_unico es inmutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_item_inventario_codigo_inmutable
    BEFORE UPDATE ON item_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_item_inventario_codigo_inmutable();

CREATE TABLE item_inventario_historial (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_inventario_id  BIGINT NOT NULL REFERENCES item_inventario(id),
    campo               VARCHAR(50) NOT NULL,
    valor_anterior      TEXT,
    valor_nuevo         TEXT,
    usuario_id          BIGINT NOT NULL,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_item_inventario_historial_solo_agregar
    BEFORE UPDATE OR DELETE ON item_inventario_historial
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria();

CREATE OR REPLACE FUNCTION fn_item_inventario_registrar_historial()
RETURNS TRIGGER AS $$
DECLARE
    usuario_actual BIGINT := NULLIF(current_setting('app.usuario_actual', true), '')::BIGINT;
BEGIN
    IF NEW.nombre IS DISTINCT FROM OLD.nombre THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'nombre', OLD.nombre, NEW.nombre, usuario_actual);
    END IF;
    IF NEW.descripcion IS DISTINCT FROM OLD.descripcion THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'descripcion', OLD.descripcion, NEW.descripcion, usuario_actual);
    END IF;
    IF NEW.unidad_medida IS DISTINCT FROM OLD.unidad_medida THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'unidad_medida', OLD.unidad_medida, NEW.unidad_medida, usuario_actual);
    END IF;
    IF NEW.sucursal_id IS DISTINCT FROM OLD.sucursal_id THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'sucursal_id', OLD.sucursal_id::text, NEW.sucursal_id::text, usuario_actual);
    END IF;
    IF NEW.categoria_id IS DISTINCT FROM OLD.categoria_id THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'categoria_id', OLD.categoria_id::text, NEW.categoria_id::text, usuario_actual);
    END IF;
    IF NEW.stock_minimo IS DISTINCT FROM OLD.stock_minimo THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'stock_minimo', OLD.stock_minimo::text, NEW.stock_minimo::text, usuario_actual);
    END IF;
    IF NEW.costo_unitario IS DISTINCT FROM OLD.costo_unitario THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'costo_unitario', OLD.costo_unitario::text, NEW.costo_unitario::text, usuario_actual);
    END IF;
    IF NEW.fecha_vencimiento IS DISTINCT FROM OLD.fecha_vencimiento THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'fecha_vencimiento', OLD.fecha_vencimiento::text, NEW.fecha_vencimiento::text, usuario_actual);
    END IF;
    IF NEW.dias_alerta_vencimiento IS DISTINCT FROM OLD.dias_alerta_vencimiento THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'dias_alerta_vencimiento', OLD.dias_alerta_vencimiento::text, NEW.dias_alerta_vencimiento::text, usuario_actual);
    END IF;
    IF NEW.activo IS DISTINCT FROM OLD.activo THEN
        INSERT INTO item_inventario_historial (item_inventario_id, campo, valor_anterior, valor_nuevo, usuario_id)
        VALUES (OLD.id, 'activo', OLD.activo::text, NEW.activo::text, usuario_actual);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_item_inventario_registrar_historial
    AFTER UPDATE ON item_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_item_inventario_registrar_historial();

CREATE TABLE movimiento_inventario (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_inventario_id  BIGINT NOT NULL REFERENCES item_inventario(id),
    tipo                VARCHAR(10) NOT NULL CHECK (tipo IN ('ENTRADA','SALIDA','AJUSTE')),
    cantidad_movimiento NUMERIC(12,3) CHECK (cantidad_movimiento > 0),
    cantidad_objetivo   NUMERIC(12,3) CHECK (cantidad_objetivo >= 0),
    stock_anterior      NUMERIC(12,3) NOT NULL,
    stock_nuevo         NUMERIC(12,3),
    motivo              VARCHAR(255),
    causa_perdida       VARCHAR(20) CHECK (causa_perdida IN ('DANIO','VENCIMIENTO','EXTRAVIO')),
    origen_perdida      VARCHAR(10) CHECK (origen_perdida IN ('MANUAL','AUTOMATICA')),
    compra_id           BIGINT,
    requiere_aprobacion BOOLEAN NOT NULL DEFAULT false,
    aprobado_por        BIGINT,
    aprobado_en         TIMESTAMPTZ,
    usuario_id          BIGINT NOT NULL,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_movimiento_tipo_cantidad CHECK (
        (tipo IN ('ENTRADA','SALIDA') AND cantidad_movimiento IS NOT NULL AND cantidad_objetivo IS NULL)
        OR
        (tipo = 'AJUSTE' AND cantidad_objetivo IS NOT NULL AND cantidad_movimiento IS NULL)
    ),
    CONSTRAINT ck_movimiento_ajuste_motivo CHECK (tipo <> 'AJUSTE' OR motivo IS NOT NULL),
    CONSTRAINT ck_movimiento_perdida_es_salida CHECK (causa_perdida IS NULL OR tipo = 'SALIDA'),
    CONSTRAINT ck_movimiento_origen_requiere_causa CHECK (origen_perdida IS NULL OR causa_perdida IS NOT NULL)
);

CREATE OR REPLACE FUNCTION fn_movimiento_inventario_aplicar()
RETURNS TRIGGER AS $$
DECLARE
    stock_actual_bloqueado NUMERIC(12,3);
    nuevo_stock            NUMERIC(12,3);
    diferencia             NUMERIC(12,3);
    umbral                 NUMERIC(12,3);
BEGIN
    IF NEW.tipo IN ('ENTRADA', 'SALIDA') AND NEW.cantidad_movimiento IS NOT NULL THEN
        SELECT stock_actual INTO stock_actual_bloqueado
        FROM item_inventario WHERE id = NEW.item_inventario_id
        FOR UPDATE;

        NEW.stock_anterior := stock_actual_bloqueado;

        IF NEW.tipo = 'ENTRADA' THEN
            nuevo_stock := stock_actual_bloqueado + NEW.cantidad_movimiento;
        ELSE
            nuevo_stock := stock_actual_bloqueado - NEW.cantidad_movimiento;
            IF nuevo_stock < 0 THEN
                RAISE EXCEPTION 'Stock insuficiente para el insumo %: disponible %, solicitado %',
                    NEW.item_inventario_id, stock_actual_bloqueado, NEW.cantidad_movimiento
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;

        NEW.stock_nuevo := nuevo_stock;

        UPDATE item_inventario
        SET stock_actual = nuevo_stock, actualizado_en = now()
        WHERE id = NEW.item_inventario_id;

        PERFORM fn_generar_solicitud_si_hace_falta(NEW.item_inventario_id, nuevo_stock);

    ELSIF NEW.tipo = 'AJUSTE' AND NEW.cantidad_objetivo IS NOT NULL THEN
        SELECT stock_actual INTO stock_actual_bloqueado
        FROM item_inventario WHERE id = NEW.item_inventario_id
        FOR UPDATE;

        NEW.stock_anterior := stock_actual_bloqueado;
        diferencia := abs(NEW.cantidad_objetivo - stock_actual_bloqueado);
        umbral := COALESCE(NULLIF(current_setting('app.umbral_ajuste_aprobacion', true), '')::NUMERIC, 20);

        IF diferencia > umbral THEN
            NEW.requiere_aprobacion := true;
            NEW.stock_nuevo := NULL;
        ELSE
            NEW.stock_nuevo := NEW.cantidad_objetivo;
            UPDATE item_inventario
            SET stock_actual = NEW.cantidad_objetivo, actualizado_en = now()
            WHERE id = NEW.item_inventario_id;

            PERFORM fn_generar_solicitud_si_hace_falta(NEW.item_inventario_id, NEW.cantidad_objetivo);
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_movimiento_inventario_20_aplicar
    BEFORE INSERT ON movimiento_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_movimiento_inventario_aplicar();

CREATE OR REPLACE FUNCTION fn_movimiento_inventario_aprobar()
RETURNS TRIGGER AS $$
DECLARE
    stock_actual_bloqueado NUMERIC(12,3);
BEGIN
    IF (NEW.item_inventario_id, NEW.tipo, NEW.cantidad_movimiento, NEW.cantidad_objetivo,
        NEW.stock_anterior, NEW.stock_nuevo, NEW.motivo, NEW.causa_perdida,
        NEW.origen_perdida, NEW.compra_id, NEW.requiere_aprobacion, NEW.aprobado_en,
        NEW.usuario_id, NEW.creado_en)
       IS DISTINCT FROM
       (OLD.item_inventario_id, OLD.tipo, OLD.cantidad_movimiento, OLD.cantidad_objetivo,
        OLD.stock_anterior, OLD.stock_nuevo, OLD.motivo, OLD.causa_perdida,
        OLD.origen_perdida, OLD.compra_id, OLD.requiere_aprobacion, OLD.aprobado_en,
        OLD.usuario_id, OLD.creado_en) THEN
        RAISE EXCEPTION 'El movimiento % ya está registrado y no se modifica (kardex de solo agregar); para corregir el stock, registrar un AJUSTE',
            OLD.id;
    END IF;

    IF NEW.aprobado_por IS NOT DISTINCT FROM OLD.aprobado_por THEN
        RETURN NEW;  -- UPDATE sin cambios reales (p. ej. un save() completo de Django)
    END IF;
    IF OLD.aprobado_por IS NOT NULL THEN
        RAISE EXCEPTION 'El movimiento % ya fue aprobado', OLD.id;
    END IF;
    IF NOT OLD.requiere_aprobacion THEN
        RAISE EXCEPTION 'El movimiento % no es un ajuste pendiente de aprobación', OLD.id;
    END IF;

    SELECT stock_actual INTO stock_actual_bloqueado
    FROM item_inventario WHERE id = NEW.item_inventario_id
    FOR UPDATE;

    NEW.stock_anterior := stock_actual_bloqueado;
    NEW.stock_nuevo := NEW.cantidad_objetivo;
    NEW.aprobado_en := now();

    UPDATE item_inventario
    SET stock_actual = NEW.cantidad_objetivo, actualizado_en = now()
    WHERE id = NEW.item_inventario_id;

    PERFORM fn_generar_solicitud_si_hace_falta(NEW.item_inventario_id, NEW.cantidad_objetivo);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_movimiento_inventario_aprobar
    BEFORE UPDATE ON movimiento_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_movimiento_inventario_aprobar();

CREATE TRIGGER trg_movimiento_inventario_no_borrar
    BEFORE DELETE ON movimiento_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria();

CREATE OR REPLACE FUNCTION fn_movimiento_inventario_evitar_perdida_duplicada()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.causa_perdida = 'VENCIMIENTO' AND EXISTS (
        SELECT 1 FROM movimiento_inventario
        WHERE item_inventario_id = NEW.item_inventario_id
          AND causa_perdida = 'VENCIMIENTO'
          AND creado_en::date = CURRENT_DATE
    ) THEN
        RAISE EXCEPTION 'Ya existe una pérdida por vencimiento registrada hoy para el insumo %',
            NEW.item_inventario_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_movimiento_inventario_10_evitar_perdida_duplicada
    BEFORE INSERT ON movimiento_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_movimiento_inventario_evitar_perdida_duplicada();

CREATE TABLE solicitud_reabastecimiento (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_inventario_id  BIGINT NOT NULL REFERENCES item_inventario(id),
    cantidad_sugerida   NUMERIC(12,3) NOT NULL CHECK (cantidad_sugerida > 0),
    estado              VARCHAR(10) NOT NULL DEFAULT 'PENDIENTE'
                            CHECK (estado IN ('PENDIENTE','ENVIADA','ATENDIDA','CANCELADA')),
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_solicitud_reabastecimiento_pendiente
    ON solicitud_reabastecimiento (item_inventario_id) WHERE estado = 'PENDIENTE';

CREATE TRIGGER trg_solicitud_reabastecimiento_actualizado_en
    BEFORE UPDATE ON solicitud_reabastecimiento
    FOR EACH ROW
    EXECUTE FUNCTION fn_marcar_actualizado_en();

CREATE OR REPLACE FUNCTION fn_generar_solicitud_si_hace_falta(
    p_item_inventario_id BIGINT, p_stock_nuevo NUMERIC
) RETURNS VOID AS $$
DECLARE
    v_stock_minimo NUMERIC(12,3);
BEGIN
    SELECT stock_minimo INTO v_stock_minimo
    FROM item_inventario WHERE id = p_item_inventario_id;

    IF v_stock_minimo IS NOT NULL AND p_stock_nuevo < v_stock_minimo THEN
        BEGIN
            INSERT INTO solicitud_reabastecimiento (item_inventario_id, cantidad_sugerida)
            VALUES (p_item_inventario_id, v_stock_minimo - p_stock_nuevo);
        EXCEPTION WHEN unique_violation THEN
            NULL;
        END;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_generar_perdidas_vencimiento()
RETURNS INTEGER AS $$
DECLARE
    insumo     RECORD;
    generadas  INTEGER := 0;
BEGIN
    FOR insumo IN
        SELECT id, stock_actual FROM item_inventario
        WHERE activo = true
          AND fecha_vencimiento IS NOT NULL
          AND fecha_vencimiento < CURRENT_DATE
          AND stock_actual > 0
    LOOP
        BEGIN
            INSERT INTO movimiento_inventario
                (item_inventario_id, tipo, cantidad_movimiento, stock_anterior,
                 motivo, causa_perdida, origen_perdida, usuario_id)
            VALUES
                (insumo.id, 'SALIDA', insumo.stock_actual, insumo.stock_actual,
                 'Vencimiento automático', 'VENCIMIENTO', 'AUTOMATICA', 0);
            generadas := generadas + 1;
        EXCEPTION WHEN OTHERS THEN
            CONTINUE;
        END;
    END LOOP;
    RETURN generadas;
END;
$$ LANGUAGE plpgsql;

CREATE VIEW vista_control_existencias AS
SELECT id, codigo_unico, nombre, sucursal_id, stock_actual, stock_minimo
FROM item_inventario
WHERE activo = true AND stock_minimo IS NOT NULL AND stock_actual < stock_minimo;

CREATE VIEW vista_proximos_a_vencer AS
SELECT id, codigo_unico, nombre, sucursal_id, fecha_vencimiento,
       COALESCE(dias_alerta_vencimiento, 7) AS dias_alerta_aplicado
FROM item_inventario
WHERE activo = true AND fecha_vencimiento IS NOT NULL
  AND fecha_vencimiento <= CURRENT_DATE + COALESCE(dias_alerta_vencimiento, 7);

CREATE OR REPLACE FUNCTION fn_verificar_disponibilidad(items JSONB)
RETURNS TABLE (item_inventario_id BIGINT, cantidad_requerida NUMERIC, disponible BOOLEAN) AS $$
    SELECT
        (elem->>'item_inventario_id')::BIGINT,
        (elem->>'cantidad_requerida')::NUMERIC,
        COALESCE(i.activo AND i.stock_actual >= (elem->>'cantidad_requerida')::NUMERIC, false)
    FROM jsonb_array_elements(items) AS elem
    LEFT JOIN item_inventario i ON i.id = (elem->>'item_inventario_id')::BIGINT;
$$ LANGUAGE sql STABLE;

CREATE VIEW vista_reporte_inventario AS
SELECT i.id, i.codigo_unico, i.nombre, c.nombre AS categoria, i.activo,
       i.stock_actual, i.stock_minimo, i.fecha_vencimiento, i.sucursal_id,
       i.creado_en, i.actualizado_en
FROM item_inventario i
JOIN categoria_insumo c ON c.id = i.categoria_id;
