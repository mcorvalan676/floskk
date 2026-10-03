CREATE DATABASE IF NOT EXISTS conectatalento
CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE conectatalento;

CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol ENUM('POSTULANTE','EMPRESA','ADMIN') NOT NULL,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE postulantes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL UNIQUE,
    telefono VARCHAR(30),
    ciudad VARCHAR(100),
    region VARCHAR(100),
    descripcion TEXT,
    objetivo_profesional TEXT,
    habilidades TEXT,
    experiencia TEXT,
    educacion TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE empresas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL UNIQUE,
    nombre_empresa VARCHAR(150) NOT NULL,
    descripcion TEXT,
    sector VARCHAR(100),
    ubicacion VARCHAR(150),
    sitio_web VARCHAR(255),
    telefono VARCHAR(30),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE ofertas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    titulo VARCHAR(150) NOT NULL,
    descripcion TEXT NOT NULL,
    experiencia_requerida TEXT,
    educacion_requerida TEXT,
    requisitos TEXT,
    habilidades VARCHAR(500),
    ubicacion VARCHAR(150),
    tipo_contrato VARCHAR(80),
    jornada VARCHAR(80),
    rango_salarial VARCHAR(100),
    fecha_publicacion DATE,
    fecha_cierre DATE,
    estado ENUM('ACTIVA','PAUSADA','CERRADA') DEFAULT 'ACTIVA',
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
);

CREATE TABLE ofertas_favoritas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    postulante_id INT NOT NULL,
    oferta_id INT NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY favorita_unica (postulante_id, oferta_id),
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE,
    FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE CASCADE
);

CREATE TABLE postulaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    oferta_id INT NOT NULL,
    postulante_id INT NOT NULL,
    fecha_postulacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    estado ENUM('POSTULADO','REVISION','PRESELECCIONADO','ENTREVISTA','SELECCIONADO','RECHAZADO','FINALIZADO') DEFAULT 'POSTULADO',
    observacion TEXT,
    UNIQUE KEY postulacion_unica (oferta_id, postulante_id),
    FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE CASCADE,
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
);

CREATE INDEX idx_ofertas_estado_ubicacion ON ofertas(estado, ubicacion);
CREATE INDEX idx_postulaciones_estado_fecha ON postulaciones(estado, fecha_postulacion);

CREATE TABLE habilidades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE postulante_habilidades (
    postulante_id INT NOT NULL,
    habilidad_id INT NOT NULL,
    PRIMARY KEY (postulante_id, habilidad_id),
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE,
    FOREIGN KEY (habilidad_id) REFERENCES habilidades(id) ON DELETE CASCADE
);

CREATE TABLE curriculums (
    id INT AUTO_INCREMENT PRIMARY KEY,
    postulante_id INT NOT NULL UNIQUE,
    archivo VARCHAR(255) NOT NULL,
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
);

CREATE TABLE videos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    postulante_id INT NOT NULL UNIQUE,
    url VARCHAR(500) NOT NULL,
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
);

CREATE TABLE entrevistas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    postulacion_id INT NOT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    modalidad ENUM('PRESENCIAL','ONLINE','TELEFONICA') NOT NULL,
    lugar VARCHAR(255),
    observaciones TEXT,
    estado ENUM('PENDIENTE','REALIZADA','CANCELADA') DEFAULT 'PENDIENTE',
    FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id) ON DELETE CASCADE
);

CREATE TABLE notificaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    mensaje VARCHAR(500) NOT NULL,
    leida BOOLEAN DEFAULT FALSE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE seguimiento (
    id INT AUTO_INCREMENT PRIMARY KEY,
    postulacion_id INT NOT NULL,
    estado VARCHAR(50) NOT NULL,
    estado_anterior VARCHAR(50),
    observacion TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_id INT,
    rol_actor ENUM('POSTULANTE','EMPRESA','ADMIN'),
    FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE administradores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL UNIQUE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

INSERT IGNORE INTO habilidades (nombre)
VALUES ('Python'), ('Flask'), ('MySQL'), ('JavaScript'), ('HTML'), ('CSS');
