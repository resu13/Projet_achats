from urllib.parse import urlsplit

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_BROWSER_XSS_FILTER = True


def _require_production_value(name, value, placeholders=()):
    normalized = str(value or "").strip().lower()
    if not normalized or any(placeholder in normalized for placeholder in placeholders):
        raise ImproperlyConfigured(
            f"{name} must be set to a real production value."
        )


_require_production_value(
    "SECRET_KEY",
    SECRET_KEY,
    ("dev-secret", "changez-cette-cle", "votre-cle"),
)
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("SECRET_KEY must contain at least 50 characters.")
if not ALLOWED_HOSTS or any("*" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("ALLOWED_HOSTS must list the production hostnames.")
_require_production_value(
    "ALLOWED_HOSTS",
    ",".join(ALLOWED_HOSTS),
    ("votre-", "example", "localhost", "127.0.0.1"),
)
_require_production_value(
    "DB_PASSWORD",
    DATABASES["default"]["PASSWORD"],
    ("postgres", "mot-de-passe", "changez"),
)
if len(DATABASES["default"]["PASSWORD"]) < 20:
    raise ImproperlyConfigured("DB_PASSWORD must contain at least 20 characters.")
_require_production_value("ENTREPRISE", ENTREPRISE, ("default_co",))
_require_production_value("NOM_ENTREPRISE", NOM_ENTREPRISE, ("mon entreprise",))
if ERP_TYPE.lower() not in {"odoo", "urium"}:
    raise ImproperlyConfigured("ERP_TYPE must be either 'odoo' or 'urium'.")

_require_production_value(
    "DRIVE_FOLDER_ID",
    DRIVE_FOLDER_ID,
    ("fake", "exemple", "votre-"),
)
if not Path(GOOGLE_KEY_FILE).is_file():
    raise ImproperlyConfigured(
        "GOOGLE_KEY_FILE must point to the mounted Google service-account JSON."
    )

if ERP_TYPE.lower() == "odoo":
    odoo_url = urlsplit(ODOO_URL)
    if odoo_url.scheme != "https" or not odoo_url.netloc:
        raise ImproperlyConfigured("ODOO_URL must be an HTTPS URL.")
    for setting_name in ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_KEY"):
        _require_production_value(
            setting_name,
            globals()[setting_name],
            ("votre-", "exemple", "changez"),
        )
