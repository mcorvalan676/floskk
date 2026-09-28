from dataclasses import dataclass
from pathlib import PurePosixPath

import pymysql
from flask import has_request_context, request
from jinja2 import BaseLoader, TemplateNotFound
from pyodide.ffi import JsException, run_sync, to_js
from js import fetch, Response as JSResponse


@dataclass
class WorkerAsset:
    status: int
    headers: dict[str, str]
    body: bytes


def connect_hyperdrive(worker_env):
    binding = worker_env.HYPERDRIVE
    return pymysql.connect(
        host=binding.host,
        port=int(binding.port),
        user=binding.user,
        password=binding.password,
        database=binding.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


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


def save_cv_object(worker_env, key, content):
    run_sync(worker_env.CV_BUCKET.put(key, to_js(content)))


def load_cv_object(worker_env, key):
    stored_object = run_sync(worker_env.CV_BUCKET.get(key))
    if stored_object is None:
        raise FileNotFoundError("Curriculum not found in R2.")
    response = JSResponse.new(stored_object.body)
    return bytes(run_sync(response.bytes()))


def fetch_php_service(worker_env):
    url = getattr(worker_env, "PHP_SERVICE_URL", "")
    if not url.startswith("https://"):
        return {
            "success": False,
            "message": "Configura PHP_SERVICE_URL con la URL HTTPS del servicio PHP.",
        }, 503

    try:
        response = run_sync(fetch(url))
    except JsException:
        return {
            "success": False,
            "message": "El servicio PHP no está disponible.",
        }, 503

    if not response.ok:
        return {
            "success": False,
            "message": f"El servicio PHP respondió HTTP {response.status}.",
        }, 503

    payload = run_sync(response.json())
    if hasattr(payload, "to_py"):
        payload = payload.to_py()
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return {
            "success": False,
            "message": "El servicio PHP devolvió una respuesta no válida.",
        }, 502
    return payload, 200


class CloudflareEnvironmentMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        worker_env = environ.get("workers.env")
        secret_key = getattr(worker_env, "SECRET_KEY", None)
        from app import app

        app.secret_key = secret_key or None
        return self.wsgi_app(environ, start_response)
