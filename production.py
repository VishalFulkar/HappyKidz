"""Production launcher for Happy Kidz Public School.

Run with:
    waitress-serve --listen=127.0.0.1:8000 production:app

For a public deployment, put HTTPS/reverse-proxy in front of Waitress.
"""
import os
from werkzeug.middleware.proxy_fix import ProxyFix

# Production configuration is validated by app.py when this module is imported.
os.environ.setdefault("HKPS_PRODUCTION", "1")
from app import app  # noqa: E402

# Trust one reverse-proxy hop when deployed behind Nginx/Caddy/etc.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
