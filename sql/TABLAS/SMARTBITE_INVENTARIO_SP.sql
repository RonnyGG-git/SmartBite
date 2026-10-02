-- Smart Bite — Esquema de Inventario
-- Fuente: specs/001-esquema-inventario/plan.md (Spec 001, aprobada 2026-09-23)
-- Se ejecuta una sola vez sobre una base Postgres vacía.

-- actualizado_en lo fija la base en cada UPDATE, sin depender de que el
-- cliente se acuerde de mandarlo (vista_reporte_inventario filtra por él).
CREATE OR REPLACE FUNCTION fn_marcar_actualizado_en()
RETURNS TRIGGER AS $$
BEGIN
    NEW.actualizado_en := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Tablas de auditoría (historial y kardex, y las de Compras): solo se
-- agregan filas. El argumento opcional del trigger es un texto de ayuda
-- para quien choque con la regla — el de cada tabla es distinto (el kardex
-- sugiere un AJUSTE; eso no aplica, por ejemplo, a una factura).
CREATE OR REPLACE FUNCTION fn_rechazar_cambio_auditoria()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% es de solo agregar (auditoría): no se permite %.%',
        TG_TABLE_NAME, TG_OP, COALESCE(' ' || TG_ARGV[0], '');
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

-- sucursal_id: sin FK todavía — restaurantes_sucursal no existe en Neon
-- (verificado 2026-09-23); ver Decisión #4 del plan.
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

-- RF-7: rechaza intentar desactivar un insumo que ya está inactivo.
-- `UPDATE OF activo`: el trigger solo corre si el UPDATE menciona la
-- columna activo — así no bloquea editar otros datos de un insumo inactivo
-- ni los movimientos que actualizan su stock. (Desde Django, un save()
-- completo manda todas las columnas: para editar un insumo inactivo usar
-- save(update_fields=[...]) sin activo.)
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

-- Trazabilidad (requisito no funcional + RF-12): stock_actual solo cambia a
-- través de movimiento_inventario. Un insumo nace con stock 0 (el stock
-- inicial es una ENTRADA) y un UPDATE directo del stock se rechaza. Los
-- triggers de movimiento actualizan item_inventario desde dentro de otro
-- trigger, por eso ahí pg_trigger_depth() vale 2 o más.
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

-- RF-1 / ADR 0002: codigo_unico = <3 letras de categoria>-<secuencial de
-- 5 digitos, por sucursal>. El cliente no lo especifica, el trigger lo
-- calcula siempre. El prefijo toma solo letras (sin tildes, guiones ni
-- espacios); el bloqueo consultivo serializa las altas del mismo prefijo y
-- sucursal para que dos transacciones simultáneas no calculen el mismo
-- secuencial (con READ COMMITTED, el MAX que corre después del bloqueo ya
-- ve la fila que la otra transacción confirmó).
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

-- RF-37: codigo_unico es inmutable una vez asignado.
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

-- RF-4: historial de cambios (changelog) de item_inventario.
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
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria('El historial lo registra la base al editar el insumo');

-- El cliente debe hacer `SET LOCAL app.usuario_actual = <id>` antes del
-- UPDATE; si no lo hace, usuario_id queda NULL y el INSERT falla por la
-- constraint NOT NULL (falla clara, no un cambio de historial silencioso).
-- NULLIF: después de un SET LOCAL, en el resto de la sesión Postgres
-- devuelve '' (no NULL) para la variable, y ''::BIGINT fallaría en cada
-- UPDATE de item_inventario — incluidos los que hacen los movimientos.
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

-- Kardex unificado (ENTRADA / SALIDA / AJUSTE). stock_anterior/stock_nuevo
-- los calculan los triggers de más abajo (fn_movimiento_inventario_aplicar
-- y fn_movimiento_inventario_aprobar). compra_id, aprobado_por y
-- usuario_id sin FK: ver Decisión #4.
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

-- RF-12/13/14/17/20: aplica ENTRADA/SALIDA/AJUSTE sobre
-- item_inventario.stock_actual con bloqueo de fila (evita perder
-- actualizaciones con concurrencia). Umbral de aprobación de AJUSTE
-- configurable vía `SET app.umbral_ajuste_aprobacion = <valor>`; si no se
-- fija, usa 20 (unidades) como valor por defecto — es un placeholder
-- razonable, la spec lo deja explícitamente pendiente de que Ronny/el
-- Administrador confirmen el valor real de negocio.
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
            -- RF-14: mensaje con cifras. Mismo SQLSTATE que el CHECK de
            -- stock_actual, que sigue ahí como última barrera.
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
        -- NULLIF: mismo caso que app.usuario_actual ('' tras un SET LOCAL previo).
        umbral := COALESCE(NULLIF(current_setting('app.umbral_ajuste_aprobacion', true), '')::NUMERIC, 20);

        IF diferencia > umbral THEN
            NEW.requiere_aprobacion := true;
            NEW.stock_nuevo := NULL;
            -- No se toca item_inventario todavía: RF-17 exige aprobación
            -- primero (ver fn_movimiento_inventario_aprobar).
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

-- Prefijo numérico a propósito: Postgres corre los triggers BEFORE del
-- mismo evento en orden alfabético, y la validación de RF-38 tiene que
-- correr ANTES de aplicar el movimiento (si no, una pérdida duplicada
-- fallaría con "stock insuficiente" en vez del error específico de RF-38).
CREATE TRIGGER trg_movimiento_inventario_20_aplicar
    BEFORE INSERT ON movimiento_inventario
    FOR EACH ROW
    EXECUTE FUNCTION fn_movimiento_inventario_aplicar();

-- RF-17 + RF-18: el kardex es de solo agregar. Sobre una fila ya
-- registrada lo único permitido es aprobar, una sola vez, un AJUSTE que
-- quedó pendiente (poner aprobado_por); el trigger completa el resto.
-- BEFORE UPDATE (no AFTER, a diferencia de lo que decía el pseudocódigo
-- original del plan) — necesita modificar NEW de la propia fila, y eso
-- solo es válido en un trigger BEFORE. stock_anterior se toma al aprobar
-- (con bloqueo), no al solicitar: si entre medio hubo otros movimientos,
-- el kardex sigue encadenando.
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
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria('Para corregir el stock, registrar un AJUSTE');

-- RF-38: una pérdida por vencimiento (manual o automática) no puede
-- duplicarse el mismo día para el mismo insumo. Solo mira causa_perdida =
-- 'VENCIMIENTO' — otras causas (DANIO, EXTRAVIO) no se ven afectadas.
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

-- RF-28/29/36: solicitud de reabastecimiento. El índice único parcial (solo
-- una fila PENDIENTE por insumo) es lo que hace RF-29/RF-36 atómico de
-- verdad ante concurrencia — nunca un SELECT-antes-de-INSERT desde el
-- trigger, que sí tendría condición de carrera.
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

-- cantidad_sugerida = lo que falta para llegar al mínimo (stock_minimo -
-- stock_nuevo) — no está fijado por ningún RF, es un default razonable
-- documentado en el plan, no una cifra de negocio confirmada.
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
            -- Ya hay una solicitud PENDIENTE para este insumo (RF-29) —
            -- no se genera otra. El índice único parcial es la garantía
            -- real ante concurrencia (RF-36), esto solo evita que el
            -- movimiento entero falle por la excepción.
            NULL;
        END;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- RF-26: genera una pérdida automática (SALIDA por el stock restante
-- completo) para cada insumo activo vencido con stock. Pensada para que la
-- aplicación la invoque periódicamente (`SELECT fn_generar_perdidas_vencimiento();`)
-- — la periodicidad es responsabilidad de la app, no de este esquema.
-- usuario_id = 0 es un placeholder de "proceso automático del sistema"
-- hasta que exista cuentas.Usuario (Decisión #4).
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
            -- Ya existe una pérdida por vencimiento hoy para este insumo
            -- (RF-38) u otro error puntual: se omite y se sigue con el resto.
            CONTINUE;
        END;
    END LOOP;
    RETURN generadas;
END;
$$ LANGUAGE plpgsql;

-- RF-10/11/33: insumos activos, con mínimo configurado, por debajo de él.
CREATE VIEW vista_control_existencias AS
SELECT id, codigo_unico, nombre, sucursal_id, stock_actual, stock_minimo
FROM item_inventario
WHERE activo = true AND stock_minimo IS NOT NULL AND stock_actual < stock_minimo;

-- RF-21/22/23/34: insumos activos con vencimiento dentro del rango de
-- alerta. 7 días es un default razonable si el insumo no tiene su propio
-- dias_alerta_vencimiento configurado — no es una cifra de negocio
-- confirmada, mismo criterio que el umbral de RF-17.
CREATE VIEW vista_proximos_a_vencer AS
SELECT id, codigo_unico, nombre, sucursal_id, fecha_vencimiento,
       COALESCE(dias_alerta_vencimiento, 7) AS dias_alerta_aplicado
FROM item_inventario
WHERE activo = true AND fecha_vencimiento IS NOT NULL
  AND fecha_vencimiento <= CURRENT_DATE + COALESCE(dias_alerta_vencimiento, 7);

-- RF-27/35: disponibilidad de una lista de pares insumo-cantidad (ej. los
-- ingredientes de una receta). Un insumo inactivo siempre da disponible =
-- false, sin importar el stock (RF-35). LEFT JOIN: un insumo inexistente
-- vuelve como no disponible en vez de desaparecer del resultado (si
-- desaparecía, una receta con un ingrediente inválido parecía completa).
CREATE OR REPLACE FUNCTION fn_verificar_disponibilidad(items JSONB)
RETURNS TABLE (item_inventario_id BIGINT, cantidad_requerida NUMERIC, disponible BOOLEAN) AS $$
    SELECT
        (elem->>'item_inventario_id')::BIGINT,
        (elem->>'cantidad_requerida')::NUMERIC,
        COALESCE(i.activo AND i.stock_actual >= (elem->>'cantidad_requerida')::NUMERIC, false)
    FROM jsonb_array_elements(items) AS elem
    LEFT JOIN item_inventario i ON i.id = (elem->>'item_inventario_id')::BIGINT;
$$ LANGUAGE sql STABLE;

-- RF-30/32: reporte de inventario. El filtro por categoría/estado/rango de
-- fechas lo arma quien consulte la vista con WHERE — la vista solo expone
-- las columnas necesarias, no impone los filtros.
CREATE VIEW vista_reporte_inventario AS
SELECT i.id, i.codigo_unico, i.nombre, c.nombre AS categoria, i.activo,
       i.stock_actual, i.stock_minimo, i.fecha_vencimiento, i.sucursal_id,
       i.creado_en, i.actualizado_en
FROM item_inventario i
JOIN categoria_insumo c ON c.id = i.categoria_id;
