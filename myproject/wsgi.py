"""
WSGI config for myproject project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/

NOTE: monkey.patch_all() and patch_psycopg() MUST run before any other import
that touches socket/ssl/threading. Putting them above `import os` is the only
safe placement — even stdlib `os` triggers transitive imports that cache
pre-patched references and silently break gevent cooperation.
"""

# --- gevent monkey patching (must be first, before any other import) ---
from gevent import monkey  # noqa: E402

monkey.patch_all()
from psycogreen.gevent import patch_psycopg  # noqa: E402

patch_psycopg()
# ----------------------------------------------------------------------

import os  # noqa: E402

from django.core.wsgi import get_wsgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

application = get_wsgi_application()

# Wrap with Sentry WSGI middleware if SDK is active
try:
    from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware

    application = SentryWsgiMiddleware(application)
except ImportError:
    pass
