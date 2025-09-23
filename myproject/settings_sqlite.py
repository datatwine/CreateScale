# myproject/settings_sqlite.py
from .settings import *  # reuse everything (INSTALLED_APPS, etc.)

# Force SQLite (local file next to manage.py / BASE_DIR)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "db.sqlite3"),  # adjust path if your sqlite file lives elsewhere
    }
}

# Optional: keep it clearly "local"
DEBUG = True
