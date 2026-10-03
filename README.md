# ConectaTalento

Plataforma escolar de reclutamiento y selección que conecta empresas con postulantes. El proyecto usa Flask para autenticación, lógica y páginas, MySQL como base de datos principal y SQLite como opción local de demostración. El módulo PHP ofrece estadísticas públicas por sector desde MySQL.

## Funcionalidades

- Registro, inicio y cierre de sesión con contraseñas hasheadas y roles de postulante, empresa y administrador.
- Perfiles de postulante y empresa.
- Ofertas activas con búsqueda por cargo, ciudad, tipo de contrato, jornada y habilidad.
- Postulaciones sin duplicados; se exige un perfil y un CV PDF.
- Historial de estados, cálculo orientativo de compatibilidad por habilidades y notificaciones al postulante y a la empresa.
- Historial de postulaciones con estado anterior/nuevo y el usuario y rol que realizaron cada cambio.
- Paneles con indicadores reales; el panel del postulante muestra su próxima entrevista y permite marcar notificaciones como leídas.
- Los postulantes pueden guardar ofertas por separado de sus postulaciones y quitarlas cuando quieran.
- Gestión de candidatos limitada a postulaciones en ofertas de la empresa autenticada; filtros por estado, ciudad, habilidad, experiencia y educación.
- CV privado descargable únicamente por su titular y por empresas relacionadas con una postulación.
- Entrevistas con seguimiento de estado.
- Paneles para empresas y postulantes con indicadores de actividad y acceso a sus procesos.
- Panel administrativo con estadísticas y activación/desactivación de cuentas empresariales y postulantes.
- Servicio PHP de solo lectura que devuelve ofertas activas agrupadas por sector.

Los videos se guardan como enlaces HTTP/HTTPS. La compatibilidad es una coincidencia sencilla de habilidades y no utiliza inteligencia artificial.

## Tecnologías

- Python 3, Flask, Werkzeug y `mysql-connector-python`.
- HTML, CSS y JavaScript ES6.
- MySQL 8+ (principal) o SQLite (demo local).
- PHP 8+ con PDO MySQL para el servicio complementario.
- Cloudflare Workers (Python Workers/WSGI) con D1, o Flask en Render con conexión MySQL directa y R2 para CV.

## Ejecución local con SQLite

En PowerShell, desde la carpeta del proyecto:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-local.txt
Copy-Item .env.example .env
python app.py
```

Abre <http://127.0.0.1:5000>. SQLite se inicializa automáticamente en `database/conectatalento.db`; no requiere un servidor MySQL. Para registrar un CV, carga un PDF de hasta 10 MB desde el perfil del postulante. En Cloudflare Workers el límite es 1 MB para respetar el máximo de 2 MB por fila de D1.

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

Para inicializar una instancia TiDB Cloud Starter nueva desde tu equipo, activa un entorno virtual que tenga PyMySQL instalado (por ejemplo, `.venv-workers`) y ejecuta `python scripts/initialize_tidb.py`. El script solicita host y usuario y pide la contraseña sin mostrarla; conecta con TLS, crea `conectatalento` y aplica `database/schema.sql`. Solo inicializa bases sin tablas existentes y no migra registros de SQLite. No pegues la contraseña en comandos, archivos ni el repositorio.

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

La landing consulta `/api/php/sectores` en Flask. En desarrollo local, Flask reenvía la solicitud a `http://127.0.0.1:8000/servicio.php`; en Cloudflare, consulta directamente las ofertas activas en D1. El servicio PHP sigue siendo opcional y se ejecuta de forma independiente.

## Despliegue de Flask en Render con TiDB

Esta alternativa ejecuta Flask/Gunicorn en Render y conecta directamente a TiDB con `mysql-connector-python`; no usa Hyperdrive. El blueprint está en `render.yaml`, usa el plan gratuito para pruebas y sirve `/healthz` como verificación de salud. Los servicios gratuitos de Render pueden suspenderse al quedar inactivos, usan disco efímero y pueden ser limitados por mucho tráfico saliente hacia servicios externos. Para producción de uso continuo, revisa el plan de pago de Render.

No uses el despliegue Cloudflare Workers de abajo para esta instancia TiDB: la conexión anterior con Hyperdrive falló porque no admite el mensaje de autenticación `AuthSwitchRequest` que devuelve TiDB Starter. Cloudflare ahora usa su base D1 independiente; Render conserva la conexión MySQL directa.

1. En Cloudflare R2, crea un bucket privado para los currículums y una API token con permisos de lectura/escritura de objetos limitado a ese bucket. Ten a mano el Account ID, Access Key ID, Secret Access Key y nombre del bucket. R2 evita guardar CV en el disco efímero de Render.
2. En TiDB Cloud, conserva la instancia y base `conectatalento`. En Networking/IP Access List, autoriza las direcciones de salida de Render para la región `Ohio`, consultándolas en el panel del servicio Render. No uses `0.0.0.0/0`; permite solo las IPs/rangos publicados por Render. La conexión MySQL se hace por TLS con verificación de certificado e identidad.
3. Importa el repositorio de GitHub en Render usando **New → Blueprint** y selecciona `render.yaml`. Revisa que el servicio sea `conectatalento` y que el plan sea Free antes de crearlo.
4. En Environment del servicio, completa las variables marcadas para carga manual:

   | Variable | Valor |
   |---|---|
   | `SECRET_KEY` | Clave aleatoria larga, única y privada para Flask. |
   | `MYSQL_HOST` | Host del endpoint TiDB, sin `https://`. |
   | `MYSQL_USER` | Usuario TiDB con su prefijo de instancia. |
   | `MYSQL_PASSWORD` | Contraseña de TiDB; no la guardes en Git. |
   | `R2_ACCOUNT_ID` | Account ID de Cloudflare. |
   | `R2_ACCESS_KEY_ID` | Access Key ID del token R2. |
   | `R2_SECRET_ACCESS_KEY` | Secret Access Key del token R2. |
   | `R2_BUCKET` | Nombre exacto del bucket privado. |

   `USE_SQLITE=0`, `MYSQL_DATABASE=conectatalento` y `CV_STORAGE=r2` ya los fija el blueprint. `MYSQL_SSL_CA` es opcional; por defecto el driver valida contra el almacén de certificados del sistema.

5. Espera el primer deploy y verifica `/healthz` y luego `/`. Si Render no puede conectar a MySQL, revisa la lista IP de TiDB y el log del servicio; no abras el acceso a todas las IPs.
6. Crea la cuenta administradora con `python -m flask --app app create-admin` desde un equipo que tenga Python y pueda conectar a TiDB. Usa temporalmente la IP pública de ese equipo en la lista IP de TiDB y elimina esa regla cuando termines. Configura localmente `USE_SQLITE=0`, `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` y `SECRET_KEY`; no compartas secretos.
7. Los registros de SQLite local y los CV que estén únicamente en `uploads/cv/` no se migran automáticamente. Exporta/importa los datos de forma controlada y carga los CV a R2 antes de usarlos en producción.

El build de Render instala `requirements-hosted.txt`; no cambia las dependencias que usa Wrangler/PyWrangler. Los secretos se configuran en Render, nunca en `render.yaml`, `.env` versionado o GitHub.

## Despliegue en Cloudflare Workers

El Worker usa Flask/WSGI y Cloudflare D1 para los datos y los CV. Las plantillas Jinja y los recursos CSS/JS se empaquetan como assets internos. La integración de sectores consulta directamente las ofertas en D1 y no requiere publicar el servicio PHP. Como D1 limita cada fila a 2 MB, los CV de esta modalidad se limitan a 1 MB; el despliegue local y Render mantienen sus límites actuales.

Los formularios que modifican datos usan protección CSRF. En D1, el registro, el alta inicial de administración, las postulaciones, las entrevistas y los cambios de estado agrupan sus escrituras relacionadas en lotes transaccionales.

### Requisitos y preparación

1. Instala [Node.js](https://nodejs.org/) y [uv](https://docs.astral.sh/uv/), inicia sesión y crea la base D1:

   ```powershell
   uv sync
   npx wrangler login
   npx wrangler d1 create conectatalento
   ```

2. Copia el `database_id` que devuelve D1 y reemplaza `REPLACE_WITH_D1_DATABASE_ID` en `wrangler.jsonc`. Conserva el nombre de binding `DB`.

3. Aplica el esquema inicial a la base remota:

   ```powershell
   npx wrangler d1 migrations apply conectatalento --remote
   ```

4. Configura dos secretos distintos. Wrangler los solicita de forma interactiva; no los guardes en archivos versionados:

   ```powershell
   npx wrangler secret put SECRET_KEY
   npx wrangler secret put INITIAL_ADMIN_TOKEN
   ```

   Usa una clave larga y aleatoria para `SECRET_KEY` y un token temporal independiente para `INITIAL_ADMIN_TOKEN`.

5. Despliega el Worker. En Windows, ejecuta `.\scripts\wrangler.ps1 deploy`. También puedes configurar el Worker conectado a GitHub con **Build command** vacío y **Deploy command** `python scripts/wrangler_build.py floskk`. Para validar sin publicar, ejecuta `python scripts/wrangler_build.py floskk --dry-run`.

6. Crea la primera cuenta administradora en `https://<nombre-del-worker>.workers.dev/setup-admin`, usando el token temporal, tu correo y una contraseña de al menos 12 caracteres. Después elimina inmediatamente el secreto de bootstrap:

   ```powershell
   npx wrangler secret delete INITIAL_ADMIN_TOKEN
   ```

   La página de bootstrap queda desactivada al crear la primera cuenta ADMIN y también devuelve 404 si eliminas el token.

### Variables y bindings de producción

| Nombre | Tipo | Uso |
|---|---|---|
| `SECRET_KEY` | Secret de Worker | Firma segura de sesiones Flask. |
| `INITIAL_ADMIN_TOKEN` | Secret temporal | Alta única del primer administrador; eliminar tras usar. |
| `DB` | Binding D1 | Usuarios, perfiles, ofertas, postulaciones, entrevistas, notificaciones y CV PDF. |
| `ASSETS` | Binding de assets | Lectura de templates Jinja y recursos CSS/JS empaquetados. |

Las migraciones versionadas `migrations/` crean el esquema, los CV en D1, las ofertas guardadas y el historial auditable de cambios de postulaciones; las migraciones siguientes deben usar versiones posteriores. D1 tiene cuotas gratuitas y límites de almacenamiento/solicitudes de Cloudflare, sujetos a cambios: compruébalos en el panel antes de operaciones con mucho tráfico. Los registros y CV guardados en SQLite, MySQL o R2 no se copian automáticamente a D1.

En una base MySQL existente, actualiza `seguimiento` antes de desplegar el código que registra actores:

```sql
ALTER TABLE seguimiento
    ADD COLUMN estado_anterior VARCHAR(50) NULL,
    ADD COLUMN usuario_id INT NULL,
    ADD COLUMN rol_actor ENUM('POSTULANTE','EMPRESA','ADMIN') NULL,
    ADD CONSTRAINT fk_seguimiento_actor
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL;
```

El arranque tradicional `python app.py` sigue usando SQLite local por defecto; Render/TiDB y la ejecución local MySQL no cambian. La configuración de Hyperdrive/TiDB no se usa en Cloudflare. En modo limitado, el Worker muestra la portada pero bloquea las demás rutas hasta que estén configurados D1 y `SECRET_KEY`.

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
- `cloudflare_runtime.py`: adaptadores D1 y acceso a assets desde el Worker.
- `migrations/`: migraciones versionadas del esquema Cloudflare D1.
- `pyproject.toml`, `wrangler.jsonc` y `.assetsignore`: dependencias y configuración de Cloudflare.

La herencia se representa mediante `Postulante` y `Empresa`, que especializan `Usuario`. `Postulacion` valida sus estados y `ProcesoSeleccion` registra los avances, mientras `Curriculum` encapsula la validación del formato.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

El conjunto automatizado valida rutas de perfil, cambios de estado, notificaciones, entrevistas, renderizado Jinja, UTF-8, recursos estáticos, la migración D1 y el alta inicial del administrador. Las conexiones reales a D1, MySQL y el endpoint PHP requieren servicios configurados.
