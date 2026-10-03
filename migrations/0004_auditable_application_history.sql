ALTER TABLE seguimiento ADD COLUMN estado_anterior TEXT;
ALTER TABLE seguimiento ADD COLUMN usuario_id INTEGER
    REFERENCES usuarios(id) ON DELETE SET NULL;
ALTER TABLE seguimiento ADD COLUMN rol_actor TEXT
    CHECK (rol_actor IN ('POSTULANTE', 'EMPRESA', 'ADMIN'));
