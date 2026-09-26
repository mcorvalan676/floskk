import os

os.environ["CLOUDFLARE_WORKERS"] = "1"
os.environ["USE_SQLITE"] = "0"

from app import app
from cloudflare_runtime import CloudflareEnvironmentMiddleware, CloudflareTemplateLoader
from workers import wsgi

app.jinja_loader = CloudflareTemplateLoader(app.jinja_loader)

Default = wsgi.entrypoint(CloudflareEnvironmentMiddleware(app))
