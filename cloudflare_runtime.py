import hmac
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import PurePosixPath

from flask import has_request_context, request
from jinja2 import BaseLoader, TemplateNotFound
from pyodide.ffi import jsnull, run_sync, to_js
from js import Uint8Array, crypto


@dataclass
class WorkerAsset:
    status: int
    headers: dict[str, str]
    body: bytes


PBKDF2_ITERATIONS = 100_000
PBKDF2_ROUNDS = 6


def _derive_pbkdf2(password, salt, iterations):
    derived = password.encode("utf-8")
    for round_number in range(PBKDF2_ROUNDS):
        password_bytes = Uint8Array.new(to_js(list(derived)))
        salt_bytes = Uint8Array.new(
            to_js(list(f"{salt}:{round_number}".encode("utf-8")))
        )
        key = run_sync(
            crypto.subtle.importKey(
                "raw",
                password_bytes,
                to_js({"name": "PBKDF2"}),
                False,
                to_js(["deriveBits"]),
            )
        )
        algorithm = to_js(
            {
                "name": "PBKDF2",
                "salt": salt_bytes,
                "iterations": iterations,
                "hash": "SHA-256",
            }
        )
        derived_bits = run_sync(crypto.subtle.deriveBits(algorithm, key, 256))
        derived = bytes(Uint8Array.new(derived_bits).to_py())
    return derived.hex()


def hash_password_pbkdf2(password):
    import secrets

    salt = secrets.token_urlsafe(12)
    digest = _derive_pbkdf2(password, salt, PBKDF2_ITERATIONS)
    return f"pbkdf2-chain:sha256:{PBKDF2_ROUNDS}:{PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password_pbkdf2(password_hash, password):
    try:
        method, salt, expected_digest = password_hash.split("$", 2)
        algorithm, digest_name, rounds, iterations = method.split(":")
        if (
            algorithm != "pbkdf2-chain"
            or digest_name != "sha256"
            or int(rounds) != PBKDF2_ROUNDS
        ):
            return False
        actual_digest = _derive_pbkdf2(password, salt, int(iterations))
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual_digest, expected_digest)


class D1CursorAdapter:
    def __init__(self, database):
        self._database = database
        self._rows = []
        self._position = 0
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, query, parameters=()):
        statement = _prepare_d1_statement(self._database, query, parameters)

        is_read = query.lstrip().upper().startswith(("SELECT", "WITH"))
        result = run_sync(statement.all() if is_read else statement.run())
        raw_records = getattr(result, "results", [])
        records = raw_records.to_py() if hasattr(raw_records, "to_py") else raw_records
        self._rows = list(records or [])
        self._position = 0
        metadata = result.meta
        if hasattr(metadata, "to_py"):
            metadata = metadata.to_py()
        if isinstance(metadata, dict):
            self.lastrowid = metadata.get("last_row_id")
            self.rowcount = metadata.get("changes", -1)
        else:
            self.lastrowid = getattr(metadata, "last_row_id", None)
            self.rowcount = getattr(metadata, "changes", -1)
        return self

    def executemany(self, query, parameters):
        for values in parameters:
            self.execute(query, values)
        return self

    def fetchone(self):
        if self._position >= len(self._rows):
            return None
        row = self._rows[self._position]
        self._position += 1
        return row

    def fetchall(self):
        rows = self._rows[self._position:]
        self._position = len(self._rows)
        return rows

    def close(self):
        self._rows = []


class D1ConnectionAdapter:
    def __init__(self, database):
        self._database = database

    def cursor(self):
        return D1CursorAdapter(self._database)

    def execute_batch(self, statements):
        prepared = [
            _prepare_d1_statement(self._database, query, parameters)
            for query, parameters in statements
        ]
        return run_sync(self._database.batch(prepared))

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _prepare_d1_statement(database, query, parameters=()):
    statement = database.prepare(query)
    if parameters:
        values = []
        for value in parameters:
            if value is None:
                values.append(jsnull)
            elif isinstance(value, (date, datetime, time)):
                values.append(value.isoformat())
            elif isinstance(value, bool):
                values.append(int(value))
            else:
                values.append(value)
        statement = statement.bind(*values)
    return statement


def connect_d1(worker_env):
    return D1ConnectionAdapter(worker_env.DB)


def get_worker_asset(worker_env, path):
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("Invalid Worker asset path.")
    response = run_sync(
        worker_env.ASSETS.fetch(f"https://assets.local/{normalized.as_posix()}")
    )
    headers = {}
    for name in ("Content-Type", "Cache-Control", "ETag", "Last-Modified"):
        value = response.headers.get(name)
        if value is not None:
            headers[name] = str(value)
    return WorkerAsset(
        status=response.status,
        headers=headers,
        body=bytes(run_sync(response.bytes())),
    )


class CloudflareTemplateLoader(BaseLoader):
    def __init__(self, fallback_loader):
        self.fallback_loader = fallback_loader

    def get_source(self, environment, template):
        if not has_request_context():
            return self.fallback_loader.get_source(environment, template)

        worker_env = request.environ.get("workers.env")
        if worker_env is None:
            return self.fallback_loader.get_source(environment, template)

        path = PurePosixPath(template)
        if path.is_absolute() or ".." in path.parts:
            raise TemplateNotFound(template)

        asset_path = f"templates/{path.as_posix()}"
        response = run_sync(
            worker_env.ASSETS.fetch(f"https://assets.local/{asset_path}")
        )
        if response.status == 404:
            raise TemplateNotFound(template)
        if not response.ok:
            raise OSError(
                f"Could not load template asset {asset_path}: HTTP {response.status}"
            )
        source = run_sync(response.text())
        return source, f"cloudflare://{asset_path}", lambda: True


def save_cv_d1(worker_env, key, content):
    binary_content = Uint8Array.new(to_js(list(content)))
    statement = worker_env.DB.prepare(
        """
        INSERT INTO cv_archivos (archivo, contenido)
        VALUES (?, ?)
        ON CONFLICT(archivo) DO UPDATE SET contenido = excluded.contenido
        """
    ).bind(key, binary_content)
    run_sync(statement.run())


def load_cv_d1(worker_env, key):
    statement = worker_env.DB.prepare(
        "SELECT contenido FROM cv_archivos WHERE archivo = ?"
    ).bind(key)
    result = run_sync(statement.first())
    if result is None:
        raise FileNotFoundError("Curriculum not found in D1.")
    content = result.contenido
    if hasattr(content, "to_py"):
        content = content.to_py()
    return bytes(content)


class CloudflareEnvironmentMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        worker_env = environ.get("workers.env")
        secret_key = getattr(worker_env, "SECRET_KEY", None)
        from app import app

        app.secret_key = secret_key or None
        return self.wsgi_app(environ, start_response)
