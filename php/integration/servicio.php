<?php
header('Content-Type: application/json; charset=utf-8');
$allowedOrigins = ['http://127.0.0.1:5000', 'http://localhost:5000'];
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if (in_array($origin, $allowedOrigins, true)) {
    header("Access-Control-Allow-Origin: {$origin}");
    header('Vary: Origin');
}

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    http_response_code(405);
    echo json_encode(['success' => false, 'message' => 'Método no permitido'], JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    $host = getenv('MYSQL_HOST') ?: '127.0.0.1';
    $database = getenv('MYSQL_DATABASE') ?: 'conectatalento';
    $username = getenv('MYSQL_USER') ?: 'root';
    $password = getenv('MYSQL_PASSWORD') ?: '';
    $pdo = new PDO(
        "mysql:host={$host};dbname={$database};charset=utf8mb4",
        $username,
        $password,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]
    );

    $statement = $pdo->query(
        "SELECT COALESCE(e.sector, 'Sin sector') AS sector, COUNT(o.id) AS ofertas_activas
         FROM empresas e
         LEFT JOIN ofertas o ON o.empresa_id = e.id AND o.estado = 'ACTIVA'
         GROUP BY e.sector
         ORDER BY ofertas_activas DESC"
    );
    echo json_encode(
        ['success' => true, 'servicio' => 'ConectaTalento PHP', 'sectores' => $statement->fetchAll()],
        JSON_UNESCAPED_UNICODE
    );
} catch (PDOException $error) {
    error_log('ConectaTalento PHP integration: ' . $error->getMessage());
    http_response_code(503);
    echo json_encode(
        ['success' => false, 'message' => 'Servicio de datos no disponible. Verifica la configuración MySQL.'],
        JSON_UNESCAPED_UNICODE
    );
}
