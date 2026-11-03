from .base import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

AXES_ENABLED = False
ERP_TYPE = "odoo"
ENTREPRISE = "test_co"
DRIVE_FOLDER_ID = "fake_folder_id"
GOOGLE_KEY_FILE = "/dev/null"
