CREATE TABLE IF NOT EXISTS ofertas_favoritas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulante_id INTEGER NOT NULL,
    oferta_id INTEGER NOT NULL,
    creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(postulante_id, oferta_id),
    FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE,
    FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ofertas_favoritas_postulante
    ON ofertas_favoritas(postulante_id, creado_en);
