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
- Cloudflare Workers (Python Workers/WSGI), Hyperdrive para MySQL y R2 para CV en producción.

## Ejecución local con SQLite

En PowerShell, desde la carpeta del proyecto:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-local.txt
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

4. Opcionalmente, añade habilidades disponibles al catálogo:

```sql
SOURCE C:/ruta/al/proyecto/database/seed.sql;
```

5. Ejecuta Flask con `python app.py`.

En SQLite local, Flask crea las tablas y el catálogo inicial de habilidades al arrancar; no crea usuarios, empresas ni ofertas ficticias. En MySQL, inicializa el esquema manualmente con `schema.sql`; `seed.sql` solo añade habilidades y no se debe usar para cargar datos de producción.

Para crear la primera cuenta administradora, ejecuta `python -m flask --app app create-admin`. El comando solicita los datos y la contraseña sin mostrarla, exige 12 caracteres como mínimo y no crea credenciales predeterminadas. Asegúrate de configurar `SECRET_KEY` y, en MySQL, el esquema antes de ejecutarlo.

## Servicio PHP opcional

Requiere PHP con la extensión `pdo_mysql` activa y una base MySQL configurada con las mismas variables `MYSQL_*`. Desde `php\integration`:

```powershell
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_DATABASE = "conectatalento"
$env:MYSQL_USER = "root"
$env:MYSQL_PASSWORD = "tu-clave"
php -S 127.0.0.1:8000
```

La landing consulta `/api/php/sectores` en Flask. En desarrollo, Flask reenvía la solicitud a `http://127.0.0.1:8000/servicio.php`; en Cloudflare, `PHP_SERVICE_URL` debe apuntar a la URL HTTPS pública del servicio PHP. El PHP permanece como un servicio independiente y necesita conectividad a MySQL. La aplicación Flask muestra un mensaje de indisponibilidad si PHP no responde.

## Despliegue en Cloudflare Workers

El Worker usa el entry point WSGI de Cloudflare para ejecutar Flask. Flask sigue procesando las rutas y todas las plantillas Jinja; `templates/` y `static/` se empaquetan como assets internos y las plantillas no se exponen como archivos públicos. Los CV se guardan en R2, no en el filesystem efímero del Worker.

### Requisitos y preparación

1. Instala [Node.js](https://nodejs.org/) y [uv](https://docs.astral.sh/uv/). En PowerShell, desde la raíz del proyecto:

   ```powershell
   uv sync
   npx wrangler login
   ```

2. Conserva el MySQL existente o prepara una base MySQL accesible desde Cloudflare. Hyperdrive necesita poder conectarse al host. Ejecuta `database/schema.sql` contra esa base antes del despliegue. El Worker no inicializa tablas ni crea usuarios/empresas/ofertas al arrancar. Provisiona una cuenta administradora de forma segura con el comando anterior.

3. En Cloudflare, crea una configuración Hyperdrive que apunte a esa base MySQL. En `wrangler.jsonc`, sustituye `REPLACE_WITH_HYPERDRIVE_ID` por el identificador devuelto por Cloudflare. No guardes la cadena de conexión ni credenciales de MySQL en el repositorio.

4. Crea el bucket R2 especificado en `wrangler.jsonc`:

   ```powershell
   npx wrangler r2 bucket create conectatalento-cv
   ```

5. Actualiza `PHP_SERVICE_URL` en `wrangler.jsonc` con la URL HTTPS del servicio PHP desplegado. El archivo `php/integration/servicio.php` no se ejecuta en el Worker ni se publica como asset; debe desplegarse por separado con PHP 8+, PDO MySQL y acceso a la misma base.

6. Configura el secreto de sesión con Wrangler. Se solicita el valor de forma interactiva:

   ```powershell
   npx wrangler secret put SECRET_KEY
   ```

   Genera una clave aleatoria larga localmente; no la incluyas en comandos compartidos ni en archivos versionados.

7. Configura el Worker conectado a GitHub para que **Build command** esté vacío y **Deploy command** sea `python scripts/wrangler_build.py floskk`. El script sincroniza las dependencias de Python Workers, aparta temporalmente `.venv` y `.venv-workers` para que Wrangler no los incluya como módulos Python y los restaura al terminar. En Windows, usa el script PowerShell equivalente:

   ```powershell
   .\scripts\wrangler.ps1 dry-run
   .\scripts\wrangler.ps1 dev --local --port 8787
   .\scripts\wrangler.ps1 deploy
   ```

   Para validar manualmente el comando de Cloudflare sin subir el Worker, ejecuta `python scripts/wrangler_build.py floskk --dry-run`. `dev` requiere acceso a los bindings configurados. Para Hyperdrive local, define temporalmente `CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE` con una URL MySQL local; no guardes esa cadena en Git. El arranque tradicional `python app.py` y `python -m unittest` siguen usando la configuración local y `requirements-local.txt`. Pywrangler no admite un `requirements.txt` en el raíz del proyecto; las dependencias Worker están declaradas exclusivamente en `pyproject.toml`.

### Variables y bindings de producción

| Nombre | Tipo | Uso |
|---|---|---|
| `SECRET_KEY` | Secret de Worker | Firma segura de sesiones Flask. Crear con `wrangler secret put SECRET_KEY`. |
| `HYPERDRIVE` | Binding Hyperdrive | Conexión agrupada a la base de datos MySQL existente. |
| `CV_BUCKET` | Binding R2 | Almacenamiento persistente privado de currículums. |
| `ASSETS` | Binding de assets | Lectura de templates Jinja y recursos CSS/JS empaquetados. |
| `PHP_SERVICE_URL` | Variable no secreta | URL HTTPS de `servicio.php` desplegado independientemente. |

El Worker conserva MySQL y las tablas: no hay migración automática a D1. `mysql-connector-python` y `python-dotenv` se usan en la ejecución local y están declarados en `requirements-local.txt`; `python-dotenv` también figura en el grupo `dev` de `pyproject.toml` para que `uv sync` permita importar la app fuera del Worker. El bundle necesita Flask y PyMySQL, mientras el SDK/CLI de Workers se declara en el grupo de desarrollo. SQLite y la creación automática del esquema son exclusivamente locales; los usuarios se registran o se crean explícitamente con el comando de administración. En modo MySQL tradicional, configura `SECRET_KEY`; la clave fija de desarrollo solo se permite en modo SQLite local.

`wrangler.jsonc` usa una fecha de compatibilidad vigente para Python Workers y la bandera `python_workers`. `.assetsignore` restringe los assets empaquetados a `templates/` y `static/`.

## Arquitectura y POO

- `app.py`: creación de la aplicación, conexión a datos y rutas.
- `models/`: clases `Usuario`, `Postulante`, `Empresa`, `OfertaLaboral`, `Postulacion`, `Curriculum`, `Entrevista`, `Notificacion` y `ProcesoSeleccion`.
- `services/compatibilidad.py`: algoritmo simple de coincidencia de habilidades.
- `database/schema.sql` y `database/seed.sql`: estructura relacional y catálogo inicial de habilidades, sin cuentas ni ofertas precargadas.
- `templates/`: landing, autenticación, paneles y vistas por rol.
- `static/`: estilos responsive y JavaScript para la integración de estadísticas.
- `php/integration/servicio.php`: endpoint auxiliar JSON.
- `uploads/cv/`: almacenamiento privado de CV; nunca se sirve como contenido estático.
- `worker.py` y `src/worker.py`: entry point de Wrangler y adaptador WSGI.
- `cloudflare_runtime.py`: bindings Hyperdrive/R2/assets y acceso al servicio PHP desde el Worker.
- `pyproject.toml`, `wrangler.jsonc` y `.assetsignore`: dependencias y configuración de Cloudflare.

La herencia se representa mediante `Postulante` y `Empresa`, que especializan `Usuario`. `Postulacion` valida sus estados y `ProcesoSeleccion` registra los avances, mientras `Curriculum` encapsula la validación del formato.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

El conjunto automatizado valida rutas de perfil, cambios de estado, notificaciones, entrevistas, renderizado Jinja, UTF-8 y recursos estáticos. La conexión real a MySQL/Hyperdrive, R2 y el endpoint PHP requieren servicios configurados; no se simulan como si estuvieran disponibles.
