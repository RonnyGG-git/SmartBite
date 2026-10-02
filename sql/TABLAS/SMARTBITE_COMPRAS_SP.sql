-- Smart Bite — Esquema de Compras
-- Se ejecuta después de sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql, sobre la
-- misma base: usa sus tablas y reutiliza sus funciones genéricas
-- fn_marcar_actualizado_en() y fn_rechazar_cambio_auditoria().

-- Sin el esquema de Inventario, el script fallaría a mitad de camino con un
-- "relation does not exist" poco claro: se corta acá, antes de crear nada.
DO $$
BEGIN
    IF to_regclass('item_inventario') IS NULL
       OR to_regclass('movimiento_inventario') IS NULL
       OR to_regclass('solicitud_reabastecimiento') IS NULL
       OR to_regprocedure('fn_marcar_actualizado_en()') IS NULL
       OR to_regprocedure('fn_rechazar_cambio_auditoria()') IS NULL THEN
        RAISE EXCEPTION 'Falta el esquema de Inventario: aplicar primero sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql';
    END IF;
END;
$$;

-- Usuarios y sucursales son de otros módulos que todavía no tienen sus
-- tablas en Neon: los *_id que los referencian van sin FK por ahora (mismo
-- criterio que Inventario). Las FK hacia tablas de Inventario llevan nombre
-- explícito fk_<tabla>_<columna>.

-- RF-1, RF-2: el proveedor es común a todas las sucursales. Mismos nombres
-- de campo que el Proveedor de Django, más el NIT.
CREATE TABLE proveedor (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nit             VARCHAR(20)  NOT NULL,
    nombre          VARCHAR(150) NOT NULL,
    contacto        VARCHAR(150),
    telefono        VARCHAR(30),
    email           VARCHAR(254),
    direccion       VARCHAR(255),
    activo          BOOLEAN NOT NULL DEFAULT true,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Un NIT que queda vacío al quitarle puntos, guiones y espacios no
    -- identifica a nadie (RF-1 lo exige).
    CONSTRAINT ck_proveedor_nit_no_vacio
        CHECK (regexp_replace(nit, '[^0-9A-Za-z]', '', 'g') <> '')
);

-- RF-74: "900.123.456-7", "9001234567" y "900 123 456 7" son el mismo NIT.
CREATE UNIQUE INDEX uq_proveedor_nit
    ON proveedor (regexp_replace(nit, '[^0-9A-Za-z]', '', 'g'));

CREATE TRIGGER trg_proveedor_actualizado_en
    BEFORE UPDATE ON proveedor
    FOR EACH ROW
    EXECUTE FUNCTION fn_marcar_actualizado_en();

-- RF-4, RF-75: usuarios que actúan en nombre de un proveedor; un usuario
-- pertenece a un solo proveedor.
CREATE TABLE proveedor_usuario (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proveedor_id  BIGINT NOT NULL REFERENCES proveedor(id),
    usuario_id    BIGINT NOT NULL,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_proveedor_usuario_usuario UNIQUE (usuario_id)
);

-- RF-5, RF-6: qué insumos suministra cada proveedor, con un precio vigente
-- opcional. Los insumos son por sucursal, así que un proveedor que abastece
-- tres sucursales tiene tres filas por producto.
CREATE TABLE proveedor_insumo (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proveedor_id        BIGINT NOT NULL REFERENCES proveedor(id),
    item_inventario_id  BIGINT NOT NULL,
    precio_vigente      NUMERIC(10,2) CHECK (precio_vigente >= 0),
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_proveedor_insumo_item_inventario_id
        FOREIGN KEY (item_inventario_id) REFERENCES item_inventario(id),
    CONSTRAINT uq_proveedor_insumo UNIQUE (proveedor_id, item_inventario_id)
);

CREATE TRIGGER trg_proveedor_insumo_actualizado_en
    BEFORE UPDATE ON proveedor_insumo
    FOR EACH ROW
    EXECUTE FUNCTION fn_marcar_actualizado_en();

-- RF-9, RF-11, RF-13: una orden va dirigida a un solo proveedor y a una
-- sola sucursal, y nace en BORRADOR. Su estado solo cambia registrando una
-- transición (orden_compra_transicion): un UPDATE directo se rechaza, igual
-- que el de stock_actual en Inventario.
CREATE TABLE orden_compra (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proveedor_id    BIGINT NOT NULL REFERENCES proveedor(id),
    sucursal_id     BIGINT NOT NULL,
    estado          VARCHAR(25) NOT NULL DEFAULT 'BORRADOR' CHECK (estado IN (
                        'BORRADOR', 'PENDIENTE_APROBACION', 'APROBADA', 'RECHAZADA',
                        'CONFIRMADA', 'CONFIRMADA_PARCIAL', 'ACEPTADA_PARCIAL',
                        'EN_RECEPCION', 'RECIBIDA', 'CERRADA_FALTANTES', 'CANCELADA')),
    creado_por      BIGINT NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- El proveedor y la sucursal no cambian después de crear la orden: si
-- cambiaran, las líneas ya cargadas dejarían de cumplir RF-10 y RF-11. Una
-- orden tampoco se borra: la que no sigue se cancela.
CREATE OR REPLACE FUNCTION fn_orden_compra_proteger()
RETURNS TRIGGER AS $$
DECLARE
    proveedor_activo BOOLEAN;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'La orden % no se borra: se cancela registrando una transición a CANCELADA', OLD.id;
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.estado <> 'BORRADOR' THEN
            RAISE EXCEPTION 'Una orden de compra se crea en BORRADOR; los demás estados se alcanzan registrando transiciones';
        END IF;
        -- RF-3. Un proveedor inexistente no entra acá: lo rechaza la FK.
        SELECT activo INTO proveedor_activo FROM proveedor WHERE id = NEW.proveedor_id;
        IF proveedor_activo = false THEN
            RAISE EXCEPTION 'El proveedor % está inactivo: no se le pueden generar órdenes de compra', NEW.proveedor_id;
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE. El trigger de transiciones actualiza el estado desde otro
    -- trigger (pg_trigger_depth() >= 2); un cliente, nunca.
    IF NEW.estado IS DISTINCT FROM OLD.estado AND pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'El estado de la orden % solo cambia registrando una transición (orden_compra_transicion)', OLD.id;
    END IF;
    IF (NEW.proveedor_id, NEW.sucursal_id, NEW.creado_por, NEW.creado_en)
       IS DISTINCT FROM (OLD.proveedor_id, OLD.sucursal_id, OLD.creado_por, OLD.creado_en) THEN
        RAISE EXCEPTION 'El proveedor, la sucursal y la autoría de la orden % no se modifican', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orden_compra_proteger
    BEFORE INSERT OR UPDATE OR DELETE ON orden_compra
    FOR EACH ROW
    EXECUTE FUNCTION fn_orden_compra_proteger();

CREATE TRIGGER trg_orden_compra_actualizado_en
    BEFORE UPDATE ON orden_compra
    FOR EACH ROW
    EXECUTE FUNCTION fn_marcar_actualizado_en();

-- Una línea por insumo (RF-82), con cantidad positiva (RF-83). La
-- disponibilidad y el precio confirmado los informa el proveedor al
-- confirmar la orden; la cantidad confirmada es la pedida si el insumo está
-- DISPONIBLE, 0 si no (todo o nada, CU-COM-04).
CREATE TABLE orden_compra_linea (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    orden_compra_id       BIGINT NOT NULL REFERENCES orden_compra(id),
    item_inventario_id    BIGINT NOT NULL,
    cantidad              NUMERIC(12,3) NOT NULL CHECK (cantidad > 0),
    precio_estimado       NUMERIC(10,2) CHECK (precio_estimado >= 0),
    disponibilidad        VARCHAR(15) NOT NULL DEFAULT 'PENDIENTE'
                              CHECK (disponibilidad IN ('PENDIENTE', 'DISPONIBLE', 'NO_DISPONIBLE')),
    motivo_no_disponible  VARCHAR(255),
    precio_confirmado     NUMERIC(10,2) CHECK (precio_confirmado >= 0),
    creado_en             TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_orden_compra_linea_item_inventario_id
        FOREIGN KEY (item_inventario_id) REFERENCES item_inventario(id),
    CONSTRAINT uq_orden_compra_linea_item UNIQUE (orden_compra_id, item_inventario_id),
    CONSTRAINT ck_linea_motivo_no_disponible
        CHECK (disponibilidad <> 'NO_DISPONIBLE' OR motivo_no_disponible IS NOT NULL)
);

-- RF-10, RF-11, RF-76, RF-84: al agregar un insumo a una orden, o cambiar el
-- de una línea. La orden se bloquea FOR SHARE para que una transición
-- simultánea espere, y el insumo también, para que no se desactive entre la
-- validación y el commit.
CREATE OR REPLACE FUNCTION fn_orden_compra_linea_validar_insumo()
RETURNS TRIGGER AS $$
DECLARE
    orden_proveedor_id  BIGINT;
    orden_sucursal_id   BIGINT;
    insumo_activo       BOOLEAN;
    insumo_sucursal_id  BIGINT;
    precio_vigente      NUMERIC(10,2);
BEGIN
    SELECT proveedor_id, sucursal_id INTO orden_proveedor_id, orden_sucursal_id
    FROM orden_compra WHERE id = NEW.orden_compra_id
    FOR SHARE;

    SELECT activo, sucursal_id INTO insumo_activo, insumo_sucursal_id
    FROM item_inventario WHERE id = NEW.item_inventario_id
    FOR SHARE;

    -- Una orden o un insumo inexistentes los rechaza la FK.
    IF orden_proveedor_id IS NULL OR insumo_activo IS NULL THEN
        RETURN NEW;
    END IF;
    -- Un UPDATE que menciona el insumo sin cambiarlo (p. ej. un save()
    -- completo de Django) no tiene nada que validar.
    IF TG_OP = 'UPDATE' AND NEW.item_inventario_id IS NOT DISTINCT FROM OLD.item_inventario_id THEN
        RETURN NEW;
    END IF;

    IF NOT insumo_activo THEN
        RAISE EXCEPTION 'El insumo % está inactivo: no se puede incluir en una orden de compra', NEW.item_inventario_id;
    END IF;
    IF insumo_sucursal_id <> orden_sucursal_id THEN
        RAISE EXCEPTION 'El insumo % es de la sucursal % y la orden % es de la sucursal %',
            NEW.item_inventario_id, insumo_sucursal_id, NEW.orden_compra_id, orden_sucursal_id;
    END IF;

    SELECT pi.precio_vigente INTO precio_vigente
    FROM proveedor_insumo pi
    WHERE pi.proveedor_id = orden_proveedor_id AND pi.item_inventario_id = NEW.item_inventario_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El proveedor % no suministra el insumo %', orden_proveedor_id, NEW.item_inventario_id;
    END IF;

    IF NEW.precio_estimado IS NULL THEN
        NEW.precio_estimado := precio_vigente;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orden_compra_linea_validar_insumo
    BEFORE INSERT OR UPDATE OF item_inventario_id ON orden_compra_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_orden_compra_linea_validar_insumo();

CREATE TRIGGER trg_orden_compra_linea_actualizado_en
    BEFORE UPDATE ON orden_compra_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_marcar_actualizado_en();

-- RF-81: los insumos, cantidades y precios estimados de una orden solo se
-- editan mientras está en BORRADOR. Una línea tampoco se mueve a otra
-- orden: se saltearía las validaciones de la orden de destino.
CREATE OR REPLACE FUNCTION fn_orden_compra_linea_editar_solo_en_borrador()
RETURNS TRIGGER AS $$
DECLARE
    orden_id      BIGINT;
    estado_orden  VARCHAR(25);
BEGIN
    IF TG_OP = 'DELETE' THEN
        orden_id := OLD.orden_compra_id;
    ELSE
        orden_id := NEW.orden_compra_id;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.orden_compra_id IS DISTINCT FROM OLD.orden_compra_id THEN
        RAISE EXCEPTION 'Una línea no se mueve de la orden % a otra', OLD.orden_compra_id;
    END IF;
    -- UPDATE OF dispara con solo mencionar la columna: un save() completo de
    -- Django manda todas. Lo que cuenta es si algo cambió de verdad.
    IF TG_OP = 'UPDATE'
       AND (NEW.item_inventario_id, NEW.cantidad, NEW.precio_estimado)
           IS NOT DISTINCT FROM (OLD.item_inventario_id, OLD.cantidad, OLD.precio_estimado) THEN
        RETURN NEW;
    END IF;

    SELECT estado INTO estado_orden FROM orden_compra WHERE id = orden_id FOR SHARE;
    IF estado_orden IS NOT NULL AND estado_orden <> 'BORRADOR' THEN
        RAISE EXCEPTION 'Los insumos y cantidades de la orden % solo se editan en borrador (está en %)',
            orden_id, estado_orden;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orden_compra_linea_editar_solo_en_borrador
    BEFORE INSERT OR DELETE
        OR UPDATE OF orden_compra_id, item_inventario_id, cantidad, precio_estimado
    ON orden_compra_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_orden_compra_linea_editar_solo_en_borrador();

-- RF-20, RF-22, RF-26, RF-87: la disponibilidad, el motivo y el precio
-- confirmado los informa el proveedor mientras la orden está APROBADA; al
-- confirmarla quedan congelados. Una línea nace sin esos datos.
CREATE OR REPLACE FUNCTION fn_orden_compra_linea_datos_confirmacion()
RETURNS TRIGGER AS $$
DECLARE
    estado_orden VARCHAR(25);
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.disponibilidad <> 'PENDIENTE' OR NEW.precio_confirmado IS NOT NULL
           OR NEW.motivo_no_disponible IS NOT NULL THEN
            RAISE EXCEPTION 'La disponibilidad y el precio confirmado los informa el proveedor al confirmar la orden, no al cargar la línea';
        END IF;
        RETURN NEW;
    END IF;

    IF (NEW.disponibilidad, NEW.motivo_no_disponible, NEW.precio_confirmado)
       IS NOT DISTINCT FROM (OLD.disponibilidad, OLD.motivo_no_disponible, OLD.precio_confirmado) THEN
        RETURN NEW;  -- se mencionaron sin cambiarlos
    END IF;

    SELECT estado INTO estado_orden FROM orden_compra WHERE id = NEW.orden_compra_id FOR SHARE;
    IF estado_orden <> 'APROBADA' THEN
        RAISE EXCEPTION 'La disponibilidad y los precios de la orden % se informan solo mientras está aprobada y sin confirmar (está en %)',
            NEW.orden_compra_id, estado_orden;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orden_compra_linea_datos_confirmacion
    BEFORE INSERT OR UPDATE OF disponibilidad, motivo_no_disponible, precio_confirmado
    ON orden_compra_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_orden_compra_linea_datos_confirmacion();

-- RF-30, RF-31: fechas de entrega por lote, como calendario informativo
-- (cada entrega real se registra aparte). Se informan con la orden APROBADA,
-- igual que la disponibilidad y los precios, y quedan congeladas al
-- confirmar. "Hoy" es CURRENT_DATE de la base.
CREATE TABLE orden_compra_fecha_entrega (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    orden_compra_id  BIGINT NOT NULL REFERENCES orden_compra(id),
    fecha            DATE NOT NULL,
    usuario_id       BIGINT NOT NULL,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION fn_orden_compra_fecha_entrega_validar()
RETURNS TRIGGER AS $$
DECLARE
    orden_id      BIGINT;
    estado_orden  VARCHAR(25);
BEGIN
    IF TG_OP = 'DELETE' THEN
        orden_id := OLD.orden_compra_id;
    ELSE
        orden_id := NEW.orden_compra_id;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.orden_compra_id IS DISTINCT FROM OLD.orden_compra_id THEN
        RAISE EXCEPTION 'Una fecha de entrega no se mueve de la orden % a otra', OLD.orden_compra_id;
    END IF;

    SELECT estado INTO estado_orden FROM orden_compra WHERE id = orden_id FOR SHARE;
    IF estado_orden IS NOT NULL AND estado_orden <> 'APROBADA' THEN
        RAISE EXCEPTION 'Las fechas de entrega de la orden % se informan solo mientras está aprobada y sin confirmar (está en %)',
            orden_id, estado_orden;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NEW.fecha < CURRENT_DATE THEN
        RAISE EXCEPTION 'La fecha de entrega % es anterior a hoy (%)', NEW.fecha, CURRENT_DATE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orden_compra_fecha_entrega_validar
    BEFORE INSERT OR UPDATE OR DELETE ON orden_compra_fecha_entrega
    FOR EACH ROW
    EXECUTE FUNCTION fn_orden_compra_fecha_entrega_validar();

-- RF-34, RF-35: entregas del proveedor, varias por orden. Una entrega no se
-- edita ni se borra: solo se anula, con motivo (RF-91); la fecha de
-- anulación la pone la base.
CREATE TABLE entrega (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    orden_compra_id   BIGINT NOT NULL REFERENCES orden_compra(id),
    registrada_por    BIGINT NOT NULL,
    registrada_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    anulada_por       BIGINT,
    anulada_en        TIMESTAMPTZ,
    motivo_anulacion  VARCHAR(255),
    CONSTRAINT ck_entrega_anulacion_completa CHECK (
        (anulada_en IS NULL) = (anulada_por IS NULL)
        AND (anulada_en IS NULL) = (motivo_anulacion IS NULL))
);

-- La orden se bloquea FOR UPDATE, no FOR SHARE: la primera línea entregada
-- dispara el paso a EN_RECEPCION (que bloquea FOR UPDATE), y con FOR SHARE
-- dos entregas simultáneas de la misma orden se trabarían entre sí.
CREATE OR REPLACE FUNCTION fn_entrega_proteger()
RETURNS TRIGGER AS $$
DECLARE
    estado_orden VARCHAR(25);
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'La entrega % no se borra: se anula con motivo', OLD.id;
    END IF;

    IF TG_OP = 'INSERT' THEN
        SELECT estado INTO estado_orden FROM orden_compra WHERE id = NEW.orden_compra_id FOR UPDATE;
        IF estado_orden NOT IN ('CONFIRMADA', 'ACEPTADA_PARCIAL', 'EN_RECEPCION') THEN
            RAISE EXCEPTION 'La orden % no admite entregas (está en %): tiene que estar confirmada, o aceptada si se confirmó en parte',
                NEW.orden_compra_id, estado_orden;                                     -- RF-33, RF-110
        END IF;
        IF NEW.anulada_por IS NOT NULL OR NEW.anulada_en IS NOT NULL OR NEW.motivo_anulacion IS NOT NULL THEN
            RAISE EXCEPTION 'Una entrega se registra sin anular';
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE: solo la anulación, una vez.
    IF (NEW.orden_compra_id, NEW.registrada_por, NEW.registrada_en)
       IS DISTINCT FROM (OLD.orden_compra_id, OLD.registrada_por, OLD.registrada_en) THEN
        RAISE EXCEPTION 'La entrega % no se modifica: solo se anula con motivo', OLD.id;
    END IF;
    IF (NEW.anulada_por, NEW.anulada_en, NEW.motivo_anulacion)
       IS NOT DISTINCT FROM (OLD.anulada_por, OLD.anulada_en, OLD.motivo_anulacion) THEN
        RETURN NEW;  -- sin cambios (p. ej. un save() completo)
    END IF;
    IF OLD.anulada_en IS NOT NULL THEN
        RAISE EXCEPTION 'La entrega % ya está anulada', OLD.id;
    END IF;
    IF EXISTS (SELECT 1 FROM recepcion WHERE entrega_id = OLD.id) THEN
        RAISE EXCEPTION 'La entrega % ya se recibió: no se puede anular', OLD.id;              -- RF-91
    END IF;
    IF NEW.anulada_por IS NOT NULL THEN
        NEW.anulada_en := now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entrega_proteger
    BEFORE INSERT OR UPDATE OR DELETE ON entrega
    FOR EACH ROW
    EXECUTE FUNCTION fn_entrega_proteger();

-- Insumos y cantidades de cada entrega (RF-34), con cantidad positiva
-- (RF-89). Solo de líneas de la misma orden que el proveedor confirmó como
-- disponibles (RF-88): lo que llegue de más va como discrepancia.
CREATE TABLE entrega_linea (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entrega_id             BIGINT NOT NULL REFERENCES entrega(id),
    orden_compra_linea_id  BIGINT NOT NULL REFERENCES orden_compra_linea(id),
    cantidad_entregada     NUMERIC(12,3) NOT NULL CHECK (cantidad_entregada > 0),
    CONSTRAINT uq_entrega_linea UNIQUE (entrega_id, orden_compra_linea_id)
);

-- Orden de bloqueo en todos los triggers de Compras: primero la orden,
-- después la entrega. Cancelar bloquea la orden y después anula sus
-- entregas; si otro trigger bloqueara la entrega antes que la orden, los
-- dos podrían quedar esperándose (deadlock).
CREATE OR REPLACE FUNCTION fn_entrega_linea_validar()
RETURNS TRIGGER AS $$
DECLARE
    entrega_orden      BIGINT;
    entrega_anulada    TIMESTAMPTZ;
    estado_orden       VARCHAR(25);
    linea_orden        BIGINT;
    linea_disponible   VARCHAR(15);
BEGIN
    SELECT orden_compra_id INTO entrega_orden FROM entrega WHERE id = NEW.entrega_id;
    IF entrega_orden IS NULL THEN
        RETURN NEW;  -- una entrega inexistente la rechaza la FK
    END IF;

    SELECT estado INTO estado_orden FROM orden_compra WHERE id = entrega_orden FOR UPDATE;
    SELECT anulada_en INTO entrega_anulada FROM entrega WHERE id = NEW.entrega_id FOR SHARE;

    IF entrega_anulada IS NOT NULL THEN
        RAISE EXCEPTION 'La entrega % está anulada: no se le agregan insumos', NEW.entrega_id;
    END IF;
    IF estado_orden NOT IN ('CONFIRMADA', 'ACEPTADA_PARCIAL', 'EN_RECEPCION') THEN
        RAISE EXCEPTION 'La orden % no admite entregas (está en %)', entrega_orden, estado_orden;  -- RF-110
    END IF;
    IF EXISTS (SELECT 1 FROM recepcion WHERE entrega_id = NEW.entrega_id) THEN
        RAISE EXCEPTION 'La entrega % ya se recibió: no se le agregan insumos', NEW.entrega_id;
    END IF;

    SELECT orden_compra_id, disponibilidad INTO linea_orden, linea_disponible
    FROM orden_compra_linea WHERE id = NEW.orden_compra_linea_id;
    IF linea_orden IS DISTINCT FROM entrega_orden THEN
        RAISE EXCEPTION 'La línea % no es de la orden % de la entrega %',
            NEW.orden_compra_linea_id, entrega_orden, NEW.entrega_id;
    END IF;
    IF linea_disponible <> 'DISPONIBLE' THEN
        RAISE EXCEPTION 'El insumo de la línea % no está confirmado como disponible: no entra en la entrega (registrarlo como discrepancia)',
            NEW.orden_compra_linea_id;                                                 -- RF-88
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entrega_linea_validar
    BEFORE INSERT ON entrega_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_entrega_linea_validar();

-- RF-46: con el primer insumo entregado, la orden pasa sola a EN_RECEPCION,
-- con el usuario que registró la entrega.
CREATE OR REPLACE FUNCTION fn_entrega_linea_pasar_a_en_recepcion()
RETURNS TRIGGER AS $$
DECLARE
    entrega_orden    BIGINT;
    registrada_por_  BIGINT;
BEGIN
    SELECT e.orden_compra_id, e.registrada_por INTO entrega_orden, registrada_por_
    FROM entrega e WHERE e.id = NEW.entrega_id;
    IF (SELECT estado FROM orden_compra WHERE id = entrega_orden) <> 'EN_RECEPCION' THEN
        INSERT INTO orden_compra_transicion (orden_compra_id, estado_nuevo, usuario_id)
        VALUES (entrega_orden, 'EN_RECEPCION', registrada_por_);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entrega_linea_pasar_a_en_recepcion
    AFTER INSERT ON entrega_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_entrega_linea_pasar_a_en_recepcion();

CREATE TRIGGER trg_entrega_linea_solo_agregar
    BEFORE UPDATE OR DELETE ON entrega_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria(
        'Lo entregado no se corrige: se anula la entrega y se registra otra');

-- RF-38, RF-88: diferencias entre lo entregado y lo ordenado.
CREATE TABLE entrega_discrepancia (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entrega_id   BIGINT NOT NULL REFERENCES entrega(id),
    descripcion  VARCHAR(500) NOT NULL,
    usuario_id   BIGINT NOT NULL,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_entrega_discrepancia_descripcion CHECK (btrim(descripcion) <> '')
);

CREATE TRIGGER trg_entrega_discrepancia_solo_agregar
    BEFORE UPDATE OR DELETE ON entrega_discrepancia
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria('Una discrepancia registrada no se modifica');

-- RF-36, RF-37: el Jefe de Almacén confirma lo que recibió de una entrega,
-- una sola vez (el UNIQUE lo garantiza también ante recepciones
-- simultáneas). Lo recibido puede diferir de lo entregado: se guarda lo que
-- llegó y la diferencia va como discrepancia.
CREATE TABLE recepcion (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entrega_id  BIGINT NOT NULL REFERENCES entrega(id),
    usuario_id  BIGINT NOT NULL,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_recepcion_entrega UNIQUE (entrega_id)
);

CREATE OR REPLACE FUNCTION fn_recepcion_validar()
RETURNS TRIGGER AS $$
DECLARE
    entrega_orden    BIGINT;
    entrega_anulada  TIMESTAMPTZ;
    estado_orden     VARCHAR(25);
BEGIN
    SELECT orden_compra_id INTO entrega_orden FROM entrega WHERE id = NEW.entrega_id;
    IF entrega_orden IS NULL THEN
        RETURN NEW;  -- una entrega inexistente la rechaza la FK
    END IF;

    -- Primero la orden, después la entrega (ver fn_entrega_linea_validar).
    SELECT estado INTO estado_orden FROM orden_compra WHERE id = entrega_orden FOR SHARE;
    SELECT anulada_en INTO entrega_anulada FROM entrega WHERE id = NEW.entrega_id FOR UPDATE;

    IF estado_orden <> 'EN_RECEPCION' THEN
        RAISE EXCEPTION 'La orden % no admite recepciones (está en %)', entrega_orden, estado_orden;  -- RF-110
    END IF;
    IF entrega_anulada IS NOT NULL THEN
        RAISE EXCEPTION 'La entrega % está anulada: no se puede recibir', NEW.entrega_id;        -- RF-115
    END IF;
    IF NOT EXISTS (SELECT 1 FROM entrega_linea WHERE entrega_id = NEW.entrega_id) THEN
        RAISE EXCEPTION 'La entrega % no tiene insumos: no hay nada que recibir', NEW.entrega_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_recepcion_validar
    BEFORE INSERT ON recepcion
    FOR EACH ROW
    EXECUTE FUNCTION fn_recepcion_validar();

CREATE TRIGGER trg_recepcion_solo_agregar
    BEFORE UPDATE OR DELETE ON recepcion
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria(
        'Una recepción confirmada no se corrige: las diferencias se registran como discrepancia');

-- Cantidad efectivamente recibida de cada insumo de la entrega (RF-36; cero
-- vale, negativa no: RF-90) y su fecha de vencimiento (RF-92). Una por
-- línea entregada.
CREATE TABLE recepcion_linea (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recepcion_id       BIGINT NOT NULL REFERENCES recepcion(id),
    entrega_linea_id   BIGINT NOT NULL REFERENCES entrega_linea(id),
    cantidad_recibida  NUMERIC(12,3) NOT NULL CHECK (cantidad_recibida >= 0),
    fecha_vencimiento  DATE,
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_recepcion_linea UNIQUE (entrega_linea_id)
);

CREATE OR REPLACE FUNCTION fn_recepcion_linea_validar()
RETURNS TRIGGER AS $$
DECLARE
    recepcion_entrega  BIGINT;
    linea_entrega      BIGINT;
    entrega_orden      BIGINT;
    estado_orden       VARCHAR(25);
BEGIN
    SELECT entrega_id INTO recepcion_entrega FROM recepcion WHERE id = NEW.recepcion_id;
    SELECT entrega_id INTO linea_entrega FROM entrega_linea WHERE id = NEW.entrega_linea_id;
    IF recepcion_entrega IS NULL OR linea_entrega IS NULL THEN
        RETURN NEW;  -- las rechaza la FK
    END IF;
    IF linea_entrega <> recepcion_entrega THEN
        RAISE EXCEPTION 'La línea entregada % no es de la entrega % de esta recepción',
            NEW.entrega_linea_id, recepcion_entrega;
    END IF;

    SELECT e.orden_compra_id INTO entrega_orden FROM entrega e WHERE e.id = recepcion_entrega;
    SELECT estado INTO estado_orden FROM orden_compra WHERE id = entrega_orden FOR SHARE;
    IF estado_orden <> 'EN_RECEPCION' THEN
        RAISE EXCEPTION 'La orden % no admite recepciones (está en %)', entrega_orden, estado_orden;  -- RF-110
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_recepcion_linea_validar
    BEFORE INSERT ON recepcion_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_recepcion_linea_validar();

CREATE TRIGGER trg_recepcion_linea_solo_agregar
    BEFORE UPDATE OR DELETE ON recepcion_linea
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria(
        'Una recepción confirmada no se corrige: las diferencias se registran como discrepancia');

-- La trazabilidad del kardex hacia la compra pasa a ser una FK real (en
-- Inventario quedaba como número suelto hasta que existiera Compras).
ALTER TABLE movimiento_inventario
    ADD CONSTRAINT fk_movimiento_inventario_compra_id
    FOREIGN KEY (compra_id) REFERENCES orden_compra(id);

-- RF-39, RF-40, RF-44: resultado del control de calidad de lo recibido:
-- aprobado, rechazado o en cuarentena, en una o varias verificaciones.
-- desde_cuarentena = esta verificación resuelve cantidad que estaba en
-- cuarentena. Lo aprobado entra al stock como una ENTRADA del kardex (RF-42)
-- que genera el trigger; su id queda acá, único, así una cantidad no entra
-- dos veces (RF-93).
CREATE TABLE verificacion_calidad (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recepcion_linea_id        BIGINT NOT NULL REFERENCES recepcion_linea(id),
    cantidad_aprobada         NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (cantidad_aprobada >= 0),
    cantidad_rechazada        NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (cantidad_rechazada >= 0),
    cantidad_cuarentena       NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (cantidad_cuarentena >= 0),
    desde_cuarentena          BOOLEAN NOT NULL DEFAULT false,
    movimiento_inventario_id  BIGINT,
    usuario_id                BIGINT NOT NULL,
    creado_en                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_verificacion_calidad_movimiento_inventario_id
        FOREIGN KEY (movimiento_inventario_id) REFERENCES movimiento_inventario(id),
    CONSTRAINT uq_verificacion_movimiento UNIQUE (movimiento_inventario_id),
    CONSTRAINT ck_verificacion_no_vacia
        CHECK (cantidad_aprobada + cantidad_rechazada + cantidad_cuarentena > 0),
    CONSTRAINT ck_verificacion_resolucion_cuarentena
        CHECK (NOT desde_cuarentena OR cantidad_cuarentena = 0)
);

-- RF-45, RF-46, RF-114, RF-116: saldos de cada insumo de una orden, sumando
-- todas sus entregas.
--   cantidad_confirmada = la pedida si el proveedor la informó DISPONIBLE, 0 si no
--   recibida            = lo cargado en las recepciones
--   aprobada/rechazada  = todo lo clasificado así, también al resolver una cuarentena
--   cuarentena_vigente  = lo puesto en cuarentena − lo que ya se resolvió
--   sin_verificar       = lo recibido que todavía no pasó por calidad
--   pendiente           = confirmada − aprobada (las devoluciones con nota
--                         crédito también la bajan)
-- Es la única definición de "pendiente": la usan el trigger de verificación
-- (con la orden bloqueada), el paso a RECIBIDA y el cierre con faltantes.
CREATE VIEW vista_orden_compra_linea_saldo AS
SELECT l.id AS orden_compra_linea_id,
       l.orden_compra_id,
       l.item_inventario_id,
       c.cantidad_confirmada,
       r.recibida,
       v.aprobada,
       v.rechazada,
       v.cuarentena_vigente,
       r.recibida - v.clasificada AS sin_verificar,
       c.cantidad_confirmada - v.aprobada AS pendiente
FROM orden_compra_linea l
CROSS JOIN LATERAL (
    SELECT CASE WHEN l.disponibilidad = 'DISPONIBLE' THEN l.cantidad ELSE 0 END::NUMERIC(12,3)
               AS cantidad_confirmada
) c
CROSS JOIN LATERAL (
    SELECT COALESCE(sum(rl.cantidad_recibida), 0)::NUMERIC(12,3) AS recibida
    FROM entrega_linea el
    JOIN recepcion_linea rl ON rl.entrega_linea_id = el.id
    WHERE el.orden_compra_linea_id = l.id
) r
CROSS JOIN LATERAL (
    SELECT COALESCE(sum(vc.cantidad_aprobada), 0)::NUMERIC(12,3) AS aprobada,
           COALESCE(sum(vc.cantidad_rechazada), 0)::NUMERIC(12,3) AS rechazada,
           (COALESCE(sum(vc.cantidad_cuarentena) FILTER (WHERE NOT vc.desde_cuarentena), 0)
          - COALESCE(sum(vc.cantidad_aprobada + vc.cantidad_rechazada) FILTER (WHERE vc.desde_cuarentena), 0)
           )::NUMERIC(12,3) AS cuarentena_vigente,
           COALESCE(sum(vc.cantidad_aprobada + vc.cantidad_rechazada + vc.cantidad_cuarentena)
                        FILTER (WHERE NOT vc.desde_cuarentena), 0)::NUMERIC(12,3) AS clasificada
    FROM entrega_linea el
    JOIN recepcion_linea rl ON rl.entrega_linea_id = el.id
    JOIN verificacion_calidad vc ON vc.recepcion_linea_id = rl.id
    WHERE el.orden_compra_linea_id = l.id
) v;

-- Reglas de cantidades (RF-41, RF-44, RF-114) y entrada al stock (RF-42,
-- RF-43). La orden se bloquea FOR UPDATE: las verificaciones de una misma
-- orden van de a una — así una segunda no puede aprobar lo que la primera
-- ya aprobó (RF-93), y se respeta el orden de bloqueo (primero la orden).
-- Los saldos se leen después del bloqueo, así que incluyen lo que otra
-- verificación ya confirmó.
--
-- Lo que está en cuarentena reserva pendiente: una verificación nueva no
-- puede aprobar ni poner en cuarentena más que (pendiente − cuarentena
-- vigente). Así la orden no puede quedar recibida con cantidad todavía en
-- cuarentena.
CREATE OR REPLACE FUNCTION fn_verificacion_calidad_aplicar()
RETURNS TRIGGER AS $$
DECLARE
    recibida        NUMERIC(12,3);
    linea_orden_id  BIGINT;
    orden_id        BIGINT;
    estado_orden    VARCHAR(25);
    insumo_id       BIGINT;
    clasificado_rl  NUMERIC(12,3);
    cuarentena_rl   NUMERIC(12,3);
    cuarentena_ol   NUMERIC(12,3);
    pendiente       NUMERIC(12,3);
BEGIN
    IF NEW.movimiento_inventario_id IS NOT NULL THEN
        RAISE EXCEPTION 'El movimiento de inventario de una verificación lo registra la base, no se indica';
    END IF;

    SELECT rl.cantidad_recibida, el.orden_compra_linea_id, e.orden_compra_id
    INTO recibida, linea_orden_id, orden_id
    FROM recepcion_linea rl
    JOIN entrega_linea el ON el.id = rl.entrega_linea_id
    JOIN entrega e ON e.id = el.entrega_id
    WHERE rl.id = NEW.recepcion_linea_id;
    IF orden_id IS NULL THEN
        RETURN NEW;  -- una línea recibida inexistente la rechaza la FK
    END IF;

    SELECT estado INTO estado_orden FROM orden_compra WHERE id = orden_id FOR UPDATE;
    IF estado_orden <> 'EN_RECEPCION' THEN
        RAISE EXCEPTION 'La orden % no admite verificaciones (está en %)', orden_id, estado_orden;  -- RF-110
    END IF;

    SELECT item_inventario_id, s.pendiente, s.cuarentena_vigente
    INTO insumo_id, pendiente, cuarentena_ol
    FROM vista_orden_compra_linea_saldo s WHERE s.orden_compra_linea_id = linea_orden_id;

    -- Saldos de esta línea recibida.
    SELECT COALESCE(sum(cantidad_aprobada + cantidad_rechazada + cantidad_cuarentena)
                        FILTER (WHERE NOT desde_cuarentena), 0),
           COALESCE(sum(cantidad_cuarentena) FILTER (WHERE NOT desde_cuarentena), 0)
         - COALESCE(sum(cantidad_aprobada + cantidad_rechazada) FILTER (WHERE desde_cuarentena), 0)
    INTO clasificado_rl, cuarentena_rl
    FROM verificacion_calidad WHERE recepcion_linea_id = NEW.recepcion_linea_id;

    IF NEW.desde_cuarentena THEN
        IF NEW.cantidad_aprobada + NEW.cantidad_rechazada > cuarentena_rl THEN
            RAISE EXCEPTION 'En esta línea recibida hay % en cuarentena: no se pueden resolver %',
                cuarentena_rl, NEW.cantidad_aprobada + NEW.cantidad_rechazada;           -- RF-44
        END IF;
    ELSE
        IF clasificado_rl + NEW.cantidad_aprobada + NEW.cantidad_rechazada + NEW.cantidad_cuarentena > recibida THEN
            RAISE EXCEPTION 'Se recibieron % y ya se verificaron %: no alcanzan para verificar % más',
                recibida, clasificado_rl,
                NEW.cantidad_aprobada + NEW.cantidad_rechazada + NEW.cantidad_cuarentena; -- RF-41
        END IF;
        IF NEW.cantidad_aprobada + NEW.cantidad_cuarentena > pendiente - cuarentena_ol THEN
            RAISE EXCEPTION 'Del insumo quedan % pendientes y % reservados en cuarentena: no se pueden aprobar ni poner en cuarentena % (el exceso se rechaza)',
                pendiente, cuarentena_ol, NEW.cantidad_aprobada + NEW.cantidad_cuarentena; -- RF-114
        END IF;
    END IF;

    IF NEW.cantidad_aprobada > 0 THEN
        INSERT INTO movimiento_inventario
            (item_inventario_id, tipo, cantidad_movimiento, compra_id, usuario_id, motivo)
        VALUES
            (insumo_id, 'ENTRADA', NEW.cantidad_aprobada, orden_id, NEW.usuario_id,
             'Compra: orden ' || orden_id || ', aprobado en control de calidad')
        RETURNING id INTO NEW.movimiento_inventario_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_verificacion_calidad_aplicar
    BEFORE INSERT ON verificacion_calidad
    FOR EACH ROW
    EXECUTE FUNCTION fn_verificacion_calidad_aplicar();

-- RF-45: cuando se aprueba lo último que faltaba, la orden pasa sola a
-- RECIBIDA, con el usuario de esa verificación. Va en un AFTER: recién ahí
-- la verificación nueva cuenta en los saldos. Solo aprobar baja lo
-- pendiente; rechazar o poner en cuarentena no puede completar la orden.
CREATE OR REPLACE FUNCTION fn_verificacion_calidad_completar_orden()
RETURNS TRIGGER AS $$
DECLARE
    orden_id BIGINT;
BEGIN
    IF NEW.cantidad_aprobada = 0 THEN
        RETURN NULL;
    END IF;
    SELECT e.orden_compra_id INTO orden_id
    FROM recepcion_linea rl
    JOIN entrega_linea el ON el.id = rl.entrega_linea_id
    JOIN entrega e ON e.id = el.entrega_id
    WHERE rl.id = NEW.recepcion_linea_id;

    -- La orden ya está bloqueada por el trigger BEFORE de esta misma fila.
    IF (SELECT estado FROM orden_compra WHERE id = orden_id) = 'EN_RECEPCION'
       AND NOT EXISTS (SELECT 1 FROM vista_orden_compra_linea_saldo
                       WHERE orden_compra_id = orden_id AND pendiente > 0) THEN
        INSERT INTO orden_compra_transicion (orden_compra_id, estado_nuevo, usuario_id)
        VALUES (orden_id, 'RECIBIDA', NEW.usuario_id);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_verificacion_calidad_completar_orden
    AFTER INSERT ON verificacion_calidad
    FOR EACH ROW
    EXECUTE FUNCTION fn_verificacion_calidad_completar_orden();

CREATE TRIGGER trg_verificacion_calidad_solo_agregar
    BEFORE UPDATE OR DELETE ON verificacion_calidad
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria(
        'Una verificación no se corrige: lo aprobado ya entró al stock (una corrección se hace con un AJUSTE en Inventario)');

-- Historial de estados de una orden. Para cambiar el estado se inserta una
-- fila acá; un trigger valida la transición y actualiza orden_compra.estado
-- (única vía). Queda quién hizo cada cambio, cuándo y por qué (RF-15, RF-16,
-- RF-108). Rechazar, cancelar y cerrar con faltantes exigen motivo (RF-17,
-- RF-19, RF-94); una confirmación parcial también, y ahí el motivo son sus
-- observaciones (RF-24; en CU-COM-03 el proveedor "lo indica en las
-- observaciones").
CREATE TABLE orden_compra_transicion (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    orden_compra_id  BIGINT NOT NULL REFERENCES orden_compra(id),
    estado_anterior  VARCHAR(25) NOT NULL,
    estado_nuevo     VARCHAR(25) NOT NULL CHECK (estado_nuevo IN (
                         'BORRADOR', 'PENDIENTE_APROBACION', 'APROBADA', 'RECHAZADA',
                         'CONFIRMADA', 'CONFIRMADA_PARCIAL', 'ACEPTADA_PARCIAL',
                         'EN_RECEPCION', 'RECIBIDA', 'CERRADA_FALTANTES', 'CANCELADA')),
    motivo           VARCHAR(255),
    usuario_id       BIGINT NOT NULL,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_transicion_motivo CHECK (
        estado_nuevo NOT IN ('RECHAZADA', 'CANCELADA', 'CERRADA_FALTANTES', 'CONFIRMADA_PARCIAL')
        OR motivo IS NOT NULL)
);

-- La orden se bloquea FOR UPDATE: de dos transiciones simultáneas, la
-- segunda espera, ve el estado que dejó la primera y se valida contra él
-- (RF-112). estado_anterior lo completa el trigger, no el cliente.
CREATE OR REPLACE FUNCTION fn_orden_compra_transicion_aplicar()
RETURNS TRIGGER AS $$
DECLARE
    estado_actual   VARCHAR(25);
    orden_proveedor BIGINT;
    permitida       BOOLEAN;
    pendientes      INTEGER;
    disponibles     INTEGER;
    no_disponibles  INTEGER;
    sin_precio      INTEGER;
    sin_recibir     INTEGER;
    en_cuarentena   NUMERIC(12,3);
    sin_verificar   NUMERIC(12,3);
BEGIN
    SELECT estado, proveedor_id INTO estado_actual, orden_proveedor
    FROM orden_compra WHERE id = NEW.orden_compra_id
    FOR UPDATE;
    IF estado_actual IS NULL THEN
        RETURN NEW;  -- una orden inexistente la rechaza la FK
    END IF;
    NEW.estado_anterior := estado_actual;

    -- Matriz de transiciones (RF-18, RF-110: los estados finales no tienen
    -- salida).
    permitida := CASE estado_actual
        WHEN 'BORRADOR'             THEN NEW.estado_nuevo IN ('PENDIENTE_APROBACION', 'CANCELADA')
        WHEN 'PENDIENTE_APROBACION' THEN NEW.estado_nuevo IN ('APROBADA', 'RECHAZADA', 'CANCELADA')
        WHEN 'APROBADA'             THEN NEW.estado_nuevo IN ('CONFIRMADA', 'CONFIRMADA_PARCIAL', 'CANCELADA')
        WHEN 'CONFIRMADA_PARCIAL'   THEN NEW.estado_nuevo IN ('ACEPTADA_PARCIAL', 'CANCELADA')
        WHEN 'CONFIRMADA'           THEN NEW.estado_nuevo IN ('EN_RECEPCION', 'CANCELADA')
        WHEN 'ACEPTADA_PARCIAL'     THEN NEW.estado_nuevo IN ('EN_RECEPCION', 'CANCELADA')
        WHEN 'EN_RECEPCION'         THEN NEW.estado_nuevo IN ('RECIBIDA', 'CERRADA_FALTANTES', 'CANCELADA')
        ELSE false
    END;
    IF NOT permitida THEN
        RAISE EXCEPTION 'La orden % no puede pasar de % a %',
            NEW.orden_compra_id, estado_actual, NEW.estado_nuevo;
    END IF;

    IF NEW.estado_nuevo = 'PENDIENTE_APROBACION' THEN
        IF NOT EXISTS (SELECT 1 FROM proveedor WHERE id = orden_proveedor AND activo) THEN
            RAISE EXCEPTION 'El proveedor % está inactivo: la orden % no se puede enviar a aprobación',
                orden_proveedor, NEW.orden_compra_id;                                    -- RF-3
        END IF;
        IF NOT EXISTS (SELECT 1 FROM orden_compra_linea WHERE orden_compra_id = NEW.orden_compra_id) THEN
            RAISE EXCEPTION 'La orden % no tiene insumos: no se puede enviar a aprobación',
                NEW.orden_compra_id;                                                     -- RF-106
        END IF;
        IF EXISTS (SELECT 1 FROM orden_compra_linea
                   WHERE orden_compra_id = NEW.orden_compra_id AND precio_estimado IS NULL) THEN
            RAISE EXCEPTION 'La orden % tiene insumos sin precio estimado: no se puede enviar a aprobación',
                NEW.orden_compra_id;                                                     -- RF-107
        END IF;
    END IF;

    -- Confirmación del proveedor. "Confirmada" = todo disponible;
    -- "confirmada en parte" = algo no disponible (vocabulario de la spec).
    IF NEW.estado_nuevo IN ('CONFIRMADA', 'CONFIRMADA_PARCIAL') THEN
        SELECT count(*) FILTER (WHERE disponibilidad = 'PENDIENTE'),
               count(*) FILTER (WHERE disponibilidad = 'DISPONIBLE'),
               count(*) FILTER (WHERE disponibilidad = 'NO_DISPONIBLE'),
               count(*) FILTER (WHERE disponibilidad = 'DISPONIBLE' AND precio_confirmado IS NULL)
        INTO pendientes, disponibles, no_disponibles, sin_precio
        FROM orden_compra_linea WHERE orden_compra_id = NEW.orden_compra_id;

        IF pendientes > 0 THEN
            RAISE EXCEPTION 'La orden % tiene % insumo(s) sin informar: no se puede confirmar',
                NEW.orden_compra_id, pendientes;                                          -- RF-86
        END IF;
        IF disponibles = 0 THEN
            RAISE EXCEPTION 'Ningún insumo de la orden % está disponible: no se puede confirmar (corresponde cancelarla)',
                NEW.orden_compra_id;                                                      -- RF-25
        END IF;
        IF sin_precio > 0 THEN
            RAISE EXCEPTION 'La orden % tiene % insumo(s) disponibles sin precio: no se puede confirmar',
                NEW.orden_compra_id, sin_precio;                                          -- RF-28
        END IF;
        IF NOT EXISTS (SELECT 1 FROM orden_compra_fecha_entrega WHERE orden_compra_id = NEW.orden_compra_id) THEN
            RAISE EXCEPTION 'La orden % no tiene fecha de entrega: no se puede confirmar',
                NEW.orden_compra_id;                                                      -- RF-113
        END IF;
        IF NEW.estado_nuevo = 'CONFIRMADA' AND no_disponibles > 0 THEN
            RAISE EXCEPTION 'La orden % tiene insumos no disponibles: se confirma en parte (CONFIRMADA_PARCIAL)',
                NEW.orden_compra_id;
        END IF;
        IF NEW.estado_nuevo = 'CONFIRMADA_PARCIAL' AND no_disponibles = 0 THEN
            RAISE EXCEPTION 'Todos los insumos de la orden % están disponibles: se confirma completa (CONFIRMADA)',
                NEW.orden_compra_id;
        END IF;
    END IF;

    -- RF-46: "en recepción" = tiene entregas registradas con algún insumo.
    -- La inserta sola la primera línea entregada.
    IF NEW.estado_nuevo = 'EN_RECEPCION' AND NOT EXISTS (
        SELECT 1 FROM entrega e JOIN entrega_linea el ON el.entrega_id = e.id
        WHERE e.orden_compra_id = NEW.orden_compra_id AND e.anulada_en IS NULL
    ) THEN
        RAISE EXCEPTION 'La orden % no tiene insumos entregados: no está en recepción', NEW.orden_compra_id;
    END IF;

    -- RF-45: la inserta sola la verificación que aprueba lo último pendiente.
    IF NEW.estado_nuevo = 'RECIBIDA' AND EXISTS (
        SELECT 1 FROM vista_orden_compra_linea_saldo
        WHERE orden_compra_id = NEW.orden_compra_id AND pendiente > 0
    ) THEN
        RAISE EXCEPTION 'A la orden % todavía le quedan insumos con cantidad pendiente: no está recibida',
            NEW.orden_compra_id;
    END IF;

    -- RF-94, RF-116: se cierra con faltantes solo cuando todo lo que llegó
    -- ya se procesó. Además de lo que pide el RF-116 (entregas sin recibir,
    -- cuarentena), tampoco con lo recibido sin verificar: después del cierre
    -- no se verifica (RF-110) y esa mercadería quedaría fuera del stock.
    IF NEW.estado_nuevo = 'CERRADA_FALTANTES' THEN
        SELECT count(*) INTO sin_recibir
        FROM entrega e
        WHERE e.orden_compra_id = NEW.orden_compra_id AND e.anulada_en IS NULL
          AND NOT EXISTS (SELECT 1 FROM recepcion r WHERE r.entrega_id = e.id);
        IF sin_recibir > 0 THEN
            RAISE EXCEPTION 'La orden % tiene % entrega(s) sin recibir: no se puede cerrar con faltantes (recibirlas o anularlas primero)',
                NEW.orden_compra_id, sin_recibir;
        END IF;

        SELECT COALESCE(sum(cuarentena_vigente), 0), COALESCE(sum(s.sin_verificar), 0)
        INTO en_cuarentena, sin_verificar
        FROM vista_orden_compra_linea_saldo s WHERE s.orden_compra_id = NEW.orden_compra_id;
        IF en_cuarentena > 0 THEN
            RAISE EXCEPTION 'La orden % tiene % en cuarentena: no se puede cerrar con faltantes (resolver la cuarentena primero)',
                NEW.orden_compra_id, en_cuarentena;
        END IF;
        IF sin_verificar > 0 THEN
            RAISE EXCEPTION 'La orden % tiene % recibido sin verificar: no se puede cerrar con faltantes (registrar primero el control de calidad)',
                NEW.orden_compra_id, sin_verificar;
        END IF;
    END IF;

    -- RF-85: con algo ya recibido, la orden no se cancela; un faltante
    -- definitivo se resuelve cerrándola con faltantes.
    IF NEW.estado_nuevo = 'CANCELADA' AND EXISTS (
        SELECT 1 FROM recepcion r JOIN entrega e ON e.id = r.entrega_id
        WHERE e.orden_compra_id = NEW.orden_compra_id
    ) THEN
        RAISE EXCEPTION 'La orden % ya tiene recepciones: no se puede cancelar (un faltante definitivo se resuelve cerrándola con faltantes)',
            NEW.orden_compra_id;
    END IF;

    UPDATE orden_compra SET estado = NEW.estado_nuevo WHERE id = NEW.orden_compra_id;

    -- RF-111: cancelar anula las entregas que todavía no se recibieron (por
    -- RF-85, a esta altura ninguna lo está; la condición queda explícita).
    IF NEW.estado_nuevo = 'CANCELADA' THEN
        UPDATE entrega e
        SET anulada_por = NEW.usuario_id,
            motivo_anulacion = left('Orden cancelada: ' || NEW.motivo, 255)
        WHERE e.orden_compra_id = NEW.orden_compra_id
          AND e.anulada_en IS NULL
          AND NOT EXISTS (SELECT 1 FROM recepcion r WHERE r.entrega_id = e.id);
    END IF;

    -- RF-78: una orden cancelada o rechazada suelta sus solicitudes de
    -- reabastecimiento, que siguen pendientes para otra orden.
    IF NEW.estado_nuevo IN ('CANCELADA', 'RECHAZADA') THEN
        UPDATE solicitud_orden_compra v
        SET desvinculada_en = now()
        FROM orden_compra_linea l
        WHERE l.id = v.orden_compra_linea_id
          AND l.orden_compra_id = NEW.orden_compra_id
          AND v.desvinculada_en IS NULL;
    END IF;

    -- RF-77: una orden completada (recibida o cerrada con faltantes) deja
    -- atendidas sus solicitudes de reabastecimiento. Solo las que siguen
    -- PENDIENTE: una que Inventario ya canceló no se toca.
    IF NEW.estado_nuevo IN ('RECIBIDA', 'CERRADA_FALTANTES') THEN
        UPDATE solicitud_reabastecimiento s
        SET estado = 'ATENDIDA'
        FROM solicitud_orden_compra v
        JOIN orden_compra_linea l ON l.id = v.orden_compra_linea_id
        WHERE v.solicitud_reabastecimiento_id = s.id
          AND l.orden_compra_id = NEW.orden_compra_id
          AND v.desvinculada_en IS NULL
          AND s.estado = 'PENDIENTE';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orden_compra_transicion_aplicar
    BEFORE INSERT ON orden_compra_transicion
    FOR EACH ROW
    EXECUTE FUNCTION fn_orden_compra_transicion_aplicar();

CREATE TRIGGER trg_orden_compra_transicion_solo_agregar
    BEFORE UPDATE OR DELETE ON orden_compra_transicion
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria(
        'Una transición no se corrige: el estado se cambia registrando otra transición');

-- RF-12, RF-29, RF-70, RF-72: resumen por orden y base del historial de
-- compras. Los filtros (proveedor, rango de fechas de creación, estado) los
-- arma quien consulta, con WHERE. Montos redondeados a centavos. Si alguna
-- línea no tiene precio estimado (posible en borrador), el valor estimado
-- queda en NULL: una suma parcial parecería completa. El valor confirmado
-- cuenta solo lo DISPONIBLE (cantidad confirmada = la pedida, o 0), y queda
-- en NULL hasta que la orden se confirma: antes, 0 se leería como
-- "confirmada por $0".
CREATE VIEW vista_orden_compra_resumen AS
SELECT o.id,
       o.proveedor_id,
       p.nombre AS proveedor,
       o.sucursal_id,
       o.estado,
       o.creado_por,
       o.creado_en,
       CASE WHEN bool_or(l.id IS NOT NULL AND l.precio_estimado IS NULL) THEN NULL
            ELSE round(COALESCE(sum(l.cantidad * l.precio_estimado), 0), 2)
       END AS valor_estimado,
       CASE WHEN EXISTS (SELECT 1 FROM orden_compra_transicion t
                         WHERE t.orden_compra_id = o.id
                           AND t.estado_nuevo IN ('CONFIRMADA', 'CONFIRMADA_PARCIAL'))
            THEN round(COALESCE(sum(l.cantidad * l.precio_confirmado)
                                    FILTER (WHERE l.disponibilidad = 'DISPONIBLE'), 0), 2)
       END AS valor_confirmado
FROM orden_compra o
JOIN proveedor p ON p.id = o.proveedor_id
LEFT JOIN orden_compra_linea l ON l.orden_compra_id = o.id
GROUP BY o.id, p.nombre;

-- RF-8: que un proveedor revisó una solicitud de reabastecimiento. No
-- cambia el estado de la solicitud; una fila por proveedor y solicitud, y
-- solo de insumos que ese proveedor suministra (los únicos que ve, RF-7).
CREATE TABLE solicitud_consulta_proveedor (
    id                            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    solicitud_reabastecimiento_id BIGINT NOT NULL,
    proveedor_id                  BIGINT NOT NULL REFERENCES proveedor(id),
    usuario_id                    BIGINT NOT NULL,
    creado_en                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_solicitud_consulta_proveedor_solicitud_reabastecimiento_id
        FOREIGN KEY (solicitud_reabastecimiento_id) REFERENCES solicitud_reabastecimiento(id),
    CONSTRAINT uq_solicitud_consulta UNIQUE (solicitud_reabastecimiento_id, proveedor_id)
);

CREATE OR REPLACE FUNCTION fn_solicitud_consulta_proveedor_validar()
RETURNS TRIGGER AS $$
DECLARE
    insumo_solicitud BIGINT;
BEGIN
    SELECT item_inventario_id INTO insumo_solicitud
    FROM solicitud_reabastecimiento WHERE id = NEW.solicitud_reabastecimiento_id;
    IF insumo_solicitud IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM proveedor_insumo
        WHERE proveedor_id = NEW.proveedor_id AND item_inventario_id = insumo_solicitud
    ) THEN
        RAISE EXCEPTION 'El proveedor % no suministra el insumo % de la solicitud %',
            NEW.proveedor_id, insumo_solicitud, NEW.solicitud_reabastecimiento_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_solicitud_consulta_proveedor_validar
    BEFORE INSERT ON solicitud_consulta_proveedor
    FOR EACH ROW
    EXECUTE FUNCTION fn_solicitud_consulta_proveedor_validar();

CREATE TRIGGER trg_solicitud_consulta_proveedor_solo_agregar
    BEFORE UPDATE OR DELETE ON solicitud_consulta_proveedor
    FOR EACH ROW
    EXECUTE FUNCTION fn_rechazar_cambio_auditoria('Una consulta registrada no se modifica');

-- RF-7: las solicitudes pendientes de los insumos de cada proveedor, con
-- la marca de si ya las consultó. Filtrar por proveedor_id.
CREATE VIEW vista_solicitudes_por_proveedor AS
SELECT pi.proveedor_id,
       s.id AS solicitud_id,
       s.item_inventario_id,
       i.nombre AS insumo,
       i.sucursal_id,
       s.cantidad_sugerida,
       s.creado_en,
       EXISTS (SELECT 1 FROM solicitud_consulta_proveedor c
               WHERE c.solicitud_reabastecimiento_id = s.id
                 AND c.proveedor_id = pi.proveedor_id) AS consultada
FROM solicitud_reabastecimiento s
JOIN proveedor_insumo pi ON pi.item_inventario_id = s.item_inventario_id
JOIN item_inventario i ON i.id = s.item_inventario_id
WHERE s.estado = 'PENDIENTE';

-- RF-14, RF-79, RF-80, RF-109: qué solicitudes atiende una orden, línea por
-- línea. El índice único parcial deja un solo vínculo vigente por
-- solicitud, también ante vinculaciones simultáneas. La solicitud sigue en
-- PENDIENTE mientras dura la compra (no usa ENVIADA: el índice único de
-- Inventario solo cubre PENDIENTE, y con ENVIADA un movimiento posterior
-- generaría una solicitud duplicada).
CREATE TABLE solicitud_orden_compra (
    id                            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    solicitud_reabastecimiento_id BIGINT NOT NULL,
    -- ON DELETE CASCADE: borrar una línea (solo posible en borrador) borra su vínculo.
    orden_compra_linea_id         BIGINT NOT NULL REFERENCES orden_compra_linea(id) ON DELETE CASCADE,
    vinculada_en                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    desvinculada_en               TIMESTAMPTZ,
    CONSTRAINT fk_solicitud_orden_compra_solicitud_reabastecimiento_id
        FOREIGN KEY (solicitud_reabastecimiento_id) REFERENCES solicitud_reabastecimiento(id)
);

CREATE UNIQUE INDEX uq_solicitud_orden_compra_vigente
    ON solicitud_orden_compra (solicitud_reabastecimiento_id) WHERE desvinculada_en IS NULL;

-- Se vincula al generar la orden, o sea mientras está en BORRADOR: después
-- su contenido queda congelado (RF-81).
CREATE OR REPLACE FUNCTION fn_solicitud_orden_compra_validar()
RETURNS TRIGGER AS $$
DECLARE
    estado_solicitud  VARCHAR(10);
    insumo_solicitud  BIGINT;
    insumo_linea      BIGINT;
    orden_id          BIGINT;
    estado_orden      VARCHAR(25);
BEGIN
    SELECT estado, item_inventario_id INTO estado_solicitud, insumo_solicitud
    FROM solicitud_reabastecimiento WHERE id = NEW.solicitud_reabastecimiento_id;

    SELECT l.item_inventario_id, o.id, o.estado INTO insumo_linea, orden_id, estado_orden
    FROM orden_compra_linea l
    JOIN orden_compra o ON o.id = l.orden_compra_id
    WHERE l.id = NEW.orden_compra_linea_id
    FOR SHARE OF o;

    IF estado_solicitud IS NULL OR insumo_linea IS NULL THEN
        RETURN NEW;  -- una solicitud o una línea inexistentes las rechaza la FK
    END IF;
    IF estado_orden <> 'BORRADOR' THEN
        RAISE EXCEPTION 'Las solicitudes se vinculan mientras la orden está en borrador (la orden % está en %)',
            orden_id, estado_orden;
    END IF;
    IF estado_solicitud <> 'PENDIENTE' THEN
        RAISE EXCEPTION 'La solicitud % no está pendiente (está en %): no se puede vincular a una orden',
            NEW.solicitud_reabastecimiento_id, estado_solicitud;
    END IF;
    IF insumo_solicitud <> insumo_linea THEN
        RAISE EXCEPTION 'La solicitud % es del insumo % y la línea % es del insumo %',
            NEW.solicitud_reabastecimiento_id, insumo_solicitud, NEW.orden_compra_linea_id, insumo_linea;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_solicitud_orden_compra_validar
    BEFORE INSERT ON solicitud_orden_compra
    FOR EACH ROW
    EXECUTE FUNCTION fn_solicitud_orden_compra_validar();

-- Un vínculo no se edita. Se borra solo junto con su línea (en borrador), y
-- se desvincula solo cuando la orden se cancela o se rechaza (lo hace el
-- trigger de transiciones, desde otro trigger: pg_trigger_depth() >= 2). Si
-- se pudiera desvincular a mano una orden abierta, la solicitud quedaría
-- libre para otra orden mientras esta sigue comprando el insumo.
CREATE OR REPLACE FUNCTION fn_solicitud_orden_compra_proteger()
RETURNS TRIGGER AS $$
DECLARE
    estado_orden VARCHAR(25);
BEGIN
    IF TG_OP = 'DELETE' THEN
        -- En un ON DELETE CASCADE la línea ya no está: no hay estado que mirar.
        SELECT o.estado INTO estado_orden
        FROM orden_compra_linea l JOIN orden_compra o ON o.id = l.orden_compra_id
        WHERE l.id = OLD.orden_compra_linea_id;
        IF estado_orden IS NOT NULL AND estado_orden <> 'BORRADOR' THEN
            RAISE EXCEPTION 'El vínculo % no se borra: la orden está en %; se desvincula solo al cancelarla o rechazarla',
                OLD.id, estado_orden;
        END IF;
        RETURN OLD;
    END IF;

    IF (NEW.solicitud_reabastecimiento_id, NEW.orden_compra_linea_id, NEW.vinculada_en)
           IS DISTINCT FROM (OLD.solicitud_reabastecimiento_id, OLD.orden_compra_linea_id, OLD.vinculada_en)
       OR OLD.desvinculada_en IS NOT NULL
       OR pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'El vínculo % no se modifica: se desvincula solo al cancelar o rechazar la orden', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_solicitud_orden_compra_proteger
    BEFORE UPDATE OR DELETE ON solicitud_orden_compra
    FOR EACH ROW
    EXECUTE FUNCTION fn_solicitud_orden_compra_proteger();
