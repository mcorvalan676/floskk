USE conectatalento;

INSERT IGNORE INTO habilidades (nombre)
VALUES
    ('Python'),
    ('Flask'),
    ('MySQL'),
    ('JavaScript'),
    ('HTML'),
    ('CSS'),
    ('Análisis de datos'),
    ('Comunicación');

INSERT INTO ofertas (
    empresa_id, titulo, descripcion, requisitos, habilidades, ubicacion,
    tipo_contrato, jornada, rango_salarial, fecha_publicacion, estado
)
SELECT
    e.id,
    'Analista de datos inicial',
    'Oportunidad ficticia para apoyar reportes y análisis de información.',
    'Conocimientos básicos de SQL y hojas de cálculo.',
    'SQL, MySQL, Análisis de datos',
    'Talca',
    'Plazo fijo',
    'Jornada completa',
    'A convenir',
    CURRENT_DATE,
    'ACTIVA'
FROM empresas e
JOIN usuarios u ON u.id = e.usuario_id
WHERE u.correo = 'empresa@demo.cl'
  AND NOT EXISTS (
      SELECT 1 FROM ofertas o
      WHERE o.empresa_id = e.id AND o.titulo = 'Analista de datos inicial'
  );
