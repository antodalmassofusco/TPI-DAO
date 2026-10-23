-- Esquema de la base de datos (SQLite)
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------
-- Estructura de la red
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clinica (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL UNIQUE,
    direccion   TEXT NOT NULL,
    telefono    TEXT
);

CREATE TABLE IF NOT EXISTS laboratorio (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL UNIQUE,
    direccion   TEXT NOT NULL,
    telefono    TEXT
);

CREATE TABLE IF NOT EXISTS veterinario (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT NOT NULL,
    apellido     TEXT NOT NULL,
    matricula    TEXT NOT NULL UNIQUE,
    especialidad TEXT,
    clinica_id   INTEGER NOT NULL REFERENCES clinica(id),
    activo       INTEGER NOT NULL DEFAULT 1
);

-- ------------------------------------------------------------------
-- Clientes y mascotas
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cliente (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dni         TEXT NOT NULL UNIQUE,
    nombre      TEXT NOT NULL,
    apellido    TEXT NOT NULL,
    telefono    TEXT,
    email       TEXT,
    direccion   TEXT,
    activo      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mascota (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre           TEXT NOT NULL,
    especie          TEXT NOT NULL,
    raza             TEXT,
    sexo             TEXT NOT NULL CHECK (sexo IN ('M', 'H')),
    fecha_nacimiento TEXT NOT NULL,
    peso             REAL,
    -- Validación de negocio: toda mascota debe tener un responsable
    cliente_id       INTEGER NOT NULL REFERENCES cliente(id),
    activo           INTEGER NOT NULL DEFAULT 1
);

-- ------------------------------------------------------------------
-- Agenda y atención clínica
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turno (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    veterinario_id INTEGER NOT NULL REFERENCES veterinario(id),
    mascota_id     INTEGER NOT NULL REFERENCES mascota(id),
    inicio         TEXT NOT NULL,
    fin            TEXT NOT NULL,
    motivo         TEXT,
    estado         TEXT NOT NULL DEFAULT 'PENDIENTE'
                   CHECK (estado IN ('PENDIENTE', 'ATENDIDO', 'CANCELADO')),
    CHECK (fin > inicio)
);

CREATE TABLE IF NOT EXISTS consulta (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    mascota_id     INTEGER NOT NULL REFERENCES mascota(id),
    veterinario_id INTEGER NOT NULL REFERENCES veterinario(id),
    clinica_id     INTEGER NOT NULL REFERENCES clinica(id),
    turno_id       INTEGER REFERENCES turno(id),
    fecha_hora     TEXT NOT NULL,
    tipo           TEXT NOT NULL CHECK (tipo IN ('CONSULTA', 'CONTROL', 'URGENCIA')),
    motivo         TEXT NOT NULL,
    diagnostico    TEXT,
    tratamiento    TEXT,
    peso           REAL,
    precio         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tipo_vacuna (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre                   TEXT NOT NULL,
    especie                  TEXT NOT NULL,
    obligatoria              INTEGER NOT NULL DEFAULT 1,
    edad_minima_meses        INTEGER NOT NULL DEFAULT 0,
    intervalo_refuerzo_meses INTEGER,          -- NULL = dosis única
    precio                   REAL NOT NULL,
    UNIQUE (nombre, especie)
);

CREATE TABLE IF NOT EXISTS vacuna_aplicada (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id    INTEGER NOT NULL REFERENCES consulta(id),
    mascota_id     INTEGER NOT NULL REFERENCES mascota(id),
    tipo_vacuna_id INTEGER NOT NULL REFERENCES tipo_vacuna(id),
    fecha          TEXT NOT NULL,
    lote           TEXT,
    precio         REAL NOT NULL
);

-- ------------------------------------------------------------------
-- Derivación a laboratorio y cadena de custodia
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tipo_analisis (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre           TEXT NOT NULL UNIQUE,
    tipo_muestra     TEXT NOT NULL,
    temp_min         REAL NOT NULL,          -- °C admisibles durante el transporte
    temp_max         REAL NOT NULL,
    horas_viabilidad INTEGER NOT NULL,       -- horas máximas desde la extracción
    precio           REAL NOT NULL,
    CHECK (temp_min < temp_max)
);

CREATE TABLE IF NOT EXISTS orden_derivacion (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id    INTEGER NOT NULL REFERENCES consulta(id),
    laboratorio_id INTEGER NOT NULL REFERENCES laboratorio(id),
    fecha_hora     TEXT NOT NULL,
    prioridad      TEXT NOT NULL DEFAULT 'NORMAL' CHECK (prioridad IN ('NORMAL', 'URGENTE')),
    observaciones  TEXT
);

-- Conservadoras isotérmicas (contenedores reutilizables)
CREATE TABLE IF NOT EXISTS contenedor (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    clinica_id  INTEGER NOT NULL REFERENCES clinica(id),
    temp_min    REAL NOT NULL,
    temp_max    REAL NOT NULL,
    capacidad   INTEGER NOT NULL CHECK (capacidad > 0),
    estado      TEXT NOT NULL DEFAULT 'DISPONIBLE' CHECK (estado IN ('DISPONIBLE', 'EN_USO', 'BAJA')),
    CHECK (temp_min < temp_max)
);

CREATE TABLE IF NOT EXISTS remito (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    numero         TEXT NOT NULL UNIQUE,
    clinica_id     INTEGER NOT NULL REFERENCES clinica(id),
    laboratorio_id INTEGER NOT NULL REFERENCES laboratorio(id),
    contenedor_id  INTEGER NOT NULL REFERENCES contenedor(id),
    fecha_emision  TEXT NOT NULL,
    responsable    TEXT NOT NULL,
    estado         TEXT NOT NULL DEFAULT 'EMITIDO'
                   CHECK (estado IN ('EMITIDO', 'EN_TRANSITO', 'RECIBIDO', 'RECHAZADO'))
);

CREATE TABLE IF NOT EXISTS precinto (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo             TEXT NOT NULL UNIQUE,
    remito_id          INTEGER NOT NULL UNIQUE REFERENCES remito(id),
    fecha_colocacion   TEXT NOT NULL,
    estado             TEXT NOT NULL DEFAULT 'COLOCADO' CHECK (estado IN ('COLOCADO', 'INTACTO', 'ROTO')),
    fecha_verificacion TEXT,
    observacion        TEXT
);

CREATE TABLE IF NOT EXISTS muestra (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo           TEXT NOT NULL UNIQUE,
    orden_id         INTEGER NOT NULL REFERENCES orden_derivacion(id),
    tipo_analisis_id INTEGER NOT NULL REFERENCES tipo_analisis(id),
    fecha_extraccion TEXT NOT NULL,
    estado           TEXT NOT NULL DEFAULT 'EXTRAIDA'
                     CHECK (estado IN ('EXTRAIDA', 'EMPAQUETADA', 'EN_TRANSITO',
                                       'RECIBIDA', 'ANALIZADA', 'RECHAZADA')),
    remito_id        INTEGER REFERENCES remito(id),
    motivo_rechazo   TEXT
);

-- Trazabilidad: bitácora de estados de cada muestra (solo inserción)
CREATE TABLE IF NOT EXISTS historial_estado_muestra (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    muestra_id      INTEGER NOT NULL REFERENCES muestra(id),
    estado_anterior TEXT,
    estado_nuevo    TEXT NOT NULL,
    fecha_hora      TEXT NOT NULL,
    detalle         TEXT
);

CREATE TRIGGER IF NOT EXISTS trg_historial_inmutable_upd
BEFORE UPDATE ON historial_estado_muestra
BEGIN
    SELECT RAISE(ABORT, 'La trazabilidad de estados de la muestra es inmutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_historial_inmutable_del
BEFORE DELETE ON historial_estado_muestra
BEGIN
    SELECT RAISE(ABORT, 'La trazabilidad de estados de la muestra es inmutable');
END;

-- Una muestra en estado final (Analizada o Rechazada) no puede volver a cambiar
CREATE TRIGGER IF NOT EXISTS trg_muestra_estado_final
BEFORE UPDATE OF estado ON muestra
WHEN OLD.estado IN ('ANALIZADA', 'RECHAZADA') AND NEW.estado <> OLD.estado
BEGIN
    SELECT RAISE(ABORT, 'La muestra está en un estado final y no puede modificarse');
END;

CREATE TABLE IF NOT EXISTS envio (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    remito_id     INTEGER NOT NULL UNIQUE REFERENCES remito(id),
    transportista TEXT NOT NULL,
    vehiculo      TEXT,
    fecha_salida  TEXT NOT NULL,
    fecha_llegada TEXT
);

CREATE TABLE IF NOT EXISTS evento_envio (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    envio_id    INTEGER NOT NULL REFERENCES envio(id),
    fecha_hora  TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('SALIDA', 'PUNTO_CONTROL', 'LLEGADA')),
    ubicacion   TEXT NOT NULL,
    temperatura REAL NOT NULL,
    responsable TEXT,
    observacion TEXT
);

CREATE TABLE IF NOT EXISTS recepcion (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    remito_id           INTEGER NOT NULL UNIQUE REFERENCES remito(id),
    fecha_hora          TEXT NOT NULL,
    recibido_por        TEXT NOT NULL,
    estado_precinto     TEXT NOT NULL CHECK (estado_precinto IN ('INTACTO', 'ROTO')),
    temperatura_llegada REAL NOT NULL,
    muestras_aceptadas  INTEGER NOT NULL DEFAULT 0,
    muestras_rechazadas INTEGER NOT NULL DEFAULT 0,
    observaciones       TEXT
);

CREATE TABLE IF NOT EXISTS resultado (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    muestra_id    INTEGER NOT NULL UNIQUE REFERENCES muestra(id),
    fecha_hora    TEXT NOT NULL,
    profesional   TEXT NOT NULL,
    valores       TEXT NOT NULL,
    conclusion    TEXT NOT NULL,
    observaciones TEXT
);

-- ------------------------------------------------------------------
-- Facturación y avisos
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comprobante (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    numero      TEXT NOT NULL UNIQUE,
    consulta_id INTEGER NOT NULL UNIQUE REFERENCES consulta(id),
    cliente_id  INTEGER NOT NULL REFERENCES cliente(id),
    clinica_id  INTEGER NOT NULL REFERENCES clinica(id),
    fecha_hora  TEXT NOT NULL,
    total       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS item_comprobante (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comprobante_id  INTEGER NOT NULL REFERENCES comprobante(id),
    tipo_servicio   TEXT NOT NULL CHECK (tipo_servicio IN ('CONSULTA', 'VACUNA', 'LABORATORIO')),
    descripcion     TEXT NOT NULL,
    cantidad        INTEGER NOT NULL,
    precio_unitario REAL NOT NULL,
    subtotal        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS notificacion (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora   TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    destinatario TEXT NOT NULL,
    mensaje      TEXT NOT NULL,
    cliente_id   INTEGER REFERENCES cliente(id),
    mascota_id   INTEGER REFERENCES mascota(id),
    enviada      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mascota_cliente ON mascota(cliente_id);
CREATE INDEX IF NOT EXISTS idx_turno_vet ON turno(veterinario_id, inicio);
CREATE INDEX IF NOT EXISTS idx_consulta_mascota ON consulta(mascota_id, fecha_hora);
CREATE INDEX IF NOT EXISTS idx_muestra_estado ON muestra(estado);
CREATE INDEX IF NOT EXISTS idx_historial_muestra ON historial_estado_muestra(muestra_id, id);
CREATE INDEX IF NOT EXISTS idx_evento_envio ON evento_envio(envio_id, fecha_hora);
