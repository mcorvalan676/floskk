CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    correo TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('POSTULANTE', 'EMPRESA', 'ADMIN')),
    activo INTEGER DEFAULT 1,
    creado_en TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS postulantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL UNIQUE,
    telefono TEXT,
    ciudad TEXT,
    region TEXT,
    descripcion TEXT,
    objetivo_profesional TEXT,
    habilidades TEXT DEFAULT '',
    experiencia TEXT,
    educacion TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL UNIQUE,
    nombre_empresa TEXT NOT NULL,
    descripcion TEXT,
    sector TEXT,
    ubicacion TEXT,
    sitio_web TEXT,
    telefono TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ofertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    experiencia_requerida TEXT,
    educacion_requerida TEXT,
    requisitos TEXT,
    habilidades TEXT,
    ubicacion TEXT,
    tipo_contrato TEXT,
    jornada TEXT,
    rango_salarial TEXT,
    fecha_publicacion TEXT DEFAULT CURRENT_DATE,
    fecha_cierre TEXT,
    estado TEXT DEFAULT 'ACTIVA' CHECK (estado IN ('ACTIVA', 'PAUSADA', 'CERRADA')),
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ofertas_estado_ubicacion
    ON ofertas(estado, ubicacion);

CREATE TABLE IF NOT EXISTS postulaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oferta_id INTEGER NOT NULL,
    postulante_id INTEGER NOT NULL,
    fecha_postulacion TEXT DEFAULT CURRENT_TIMESTAMP,
    estado TEXT DEFAULT 'POSTULADO',
    observacion TEXT,
    UNIQUE(oferta_id, postulante_id),
    FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE CASCADE,
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_postulaciones_estado_fecha
    ON postulaciones(estado, fecha_postulacion);

CREATE TABLE IF NOT EXISTS entrevistas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulacion_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    modalidad TEXT NOT NULL DEFAULT 'ONLINE',
    lugar TEXT,
    observaciones TEXT,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
    FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    mensaje TEXT NOT NULL,
    leida INTEGER DEFAULT 0,
    creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS curriculums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulante_id INTEGER NOT NULL UNIQUE,
    archivo TEXT NOT NULL,
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulante_id INTEGER NOT NULL UNIQUE,
    url TEXT NOT NULL,
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seguimiento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulacion_id INTEGER NOT NULL,
    estado TEXT NOT NULL,
    observacion TEXT,
    fecha TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS administradores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL UNIQUE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS habilidades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS postulante_habilidades (
    postulante_id INTEGER NOT NULL,
    habilidad_id INTEGER NOT NULL,
    PRIMARY KEY (postulante_id, habilidad_id),
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE,
    FOREIGN KEY (habilidad_id) REFERENCES habilidades(id) ON DELETE CASCADE
);

INSERT OR IGNORE INTO habilidades (nombre) VALUES
    ('Python'),
    ('Flask'),
    ('MySQL'),
    ('JavaScript'),
    ('HTML'),
    ('CSS');
