CREATE TABLE IF NOT EXISTS aplicaciones (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha              DATE,
    rama               TEXT CHECK(rama IN ('A', 'B', 'C')),
    cargo              TEXT,
    empresa            TEXT,
    url                TEXT,
    modalidad          TEXT CHECK(modalidad IN ('Presencial', 'Híbrido', 'Remoto')),
    ubicacion          TEXT,
    match_score        INTEGER CHECK(match_score BETWEEN 0 AND 100),
    status_aplicacion  TEXT CHECK(status_aplicacion IN ('A', 'B', 'C')),
    resultado          TEXT CHECK(resultado IN ('Enviado', 'Pendiente', 'Fallido')),
    cv_generado        TEXT,
    fecha_creacion     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memoria_cargos (
    id_cargo_externo   TEXT PRIMARY KEY,
    cargo              TEXT,
    empresa            TEXT,
    fecha_visto        DATE,
    aplicado           BOOLEAN DEFAULT 0
);
