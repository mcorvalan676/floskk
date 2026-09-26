# ConectaTalento

Plataforma escolar de reclutamiento y selección que conecta empresas con postulantes. El proyecto usa Flask para autenticación, lógica y páginas, MySQL como base de datos principal y SQLite como opción local de demostración. El módulo PHP ofrece estadísticas públicas por sector desde MySQL.

## Funcionalidades

- Registro, inicio y cierre de sesión con contraseñas hasheadas y roles de postulante, empresa y administrador.
- Perfiles de postulante y empresa.
- Ofertas activas con búsqueda por cargo, ciudad, tipo de contrato, jornada y habilidad.
- Postulaciones sin duplicados; se exige un perfil y un CV PDF.
- Historial de estados, cálculo orientativo de compatibilidad por habilidades y notificaciones al postulante y a la empresa.
- Gestión de candidatos limitada a postulaciones en ofertas de la empresa autenticada; filtros por estado, ciudad, habilidad, experiencia y educación.
- CV privado descargable únicamente por su titular y por empresas relacionadas con una postulación.
- Entrevistas con seguimiento de estado.
- Panel administrativo con estadísticas y activación/desactivación de cuentas empresariales y postulantes.
- Servicio PHP de solo lectura que devuelve ofertas activas agrupadas por sector.

Los videos se guardan como enlaces HTTP/HTTPS. La compatibilidad es una coincidencia sencilla de habilidades y no utiliza inteligencia artificial.

## Tecnologías

- Python 3, Flask, Werkzeug y `mysql-connector-python`.
- HTML, CSS y JavaScript ES6.
- MySQL 8+ (principal) o SQLite (demo local).
- PHP 8+ con PDO MySQL para el servicio complementario.

## Ejecución local con SQLite

En PowerShell, desde la carpeta del proyecto:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Abre <http://127.0.0.1:5000>. SQLite se inicializa automáticamente en `database/conectatalento.db`; no requiere un servidor MySQL. Para registrar un CV, carga un PDF de hasta 10 MB desde el perfil del postulante.

## Ejecución con MySQL

1. Crea una base de datos MySQL llamada `conectatalento`.
2. En `.env`, configura las credenciales:

```dotenv
SECRET_KEY=define-una-clave-local-segura
USE_SQLITE=0
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=tu-clave
MYSQL_DATABASE=conectatalento
```

3. Inicializa el esquema (desde la consola MySQL):

```sql
SOURCE C:/ruta/al/proyecto/database/schema.sql;
```

4. Carga datos ficticios opcionales:

```sql
SOURCE C:/ruta/al/proyecto/database/seed.sql;
```

5. Ejecuta Flask con `python app.py`.

La aplicación también crea sus tablas principales al arrancar; `schema.sql` documenta las relaciones y se puede usar para preparar la base de datos manualmente.

## Servicio PHP opcional

Requiere PHP con la extensión `pdo_mysql` activa y una base MySQL configurada con las mismas variables `MYSQL_*`. Desde `php\integration`:

```powershell
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_DATABASE = "conectatalento"
$env:MYSQL_USER = "root"
$env:MYSQL_PASSWORD = "tu-clave"
php -S 127.0.0.1:8000
```

La landing consulta `http://127.0.0.1:8000/servicio.php` para mostrar el recuento de ofertas por sector. La respuesta informa errores de configuración sin exponer detalles de la conexión. Sin PHP/MySQL, el resto de la aplicación Flask sigue funcionando; la landing muestra que el servicio no está disponible.

## Usuarios demo

Al iniciar Flask se crean si no existen:

| Rol | Correo | Contraseña local |
|---|---|---|
| Empresa | `empresa@demo.cl` | `demo123` |
| Postulante | `postulante@demo.cl` | `demo123` |
| Administrador | `admin@demo.cl` | `demo123` |

Estas credenciales son exclusivamente para desarrollo local. El postulante demo debe cargar un PDF para poder postular.

## Arquitectura y POO

- `app.py`: creación de la aplicación, conexión a datos y rutas.
- `models/`: clases `Usuario`, `Postulante`, `Empresa`, `OfertaLaboral`, `Postulacion`, `Curriculum`, `Entrevista`, `Notificacion` y `ProcesoSeleccion`.
- `services/compatibilidad.py`: algoritmo simple de coincidencia de habilidades.
- `database/schema.sql` y `database/seed.sql`: estructura relacional y datos ficticios de ejemplo.
- `templates/`: landing, autenticación, paneles y vistas por rol.
- `static/`: estilos responsive y JavaScript para la integración de estadísticas.
- `php/integration/servicio.php`: endpoint auxiliar JSON.
- `uploads/cv/`: almacenamiento privado de CV; nunca se sirve como contenido estático.

La herencia se representa mediante `Postulante` y `Empresa`, que especializan `Usuario`. `Postulacion` valida sus estados y `ProcesoSeleccion` registra los avances, mientras `Curriculum` encapsula la validación del formato.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

El conjunto automatizado valida rutas de perfil, cambios de estado, notificaciones y entrevistas. La conexión real a MySQL y el endpoint PHP requieren servicios instalados localmente; no se simulan como si estuvieran disponibles.
