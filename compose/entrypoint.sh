#!/usr/bin/env sh
set -e

# 1) If running as root (UID 0), fix ownership on mounted volumes.
#    New Docker named volumes start root:root, which breaks collectstatic for appuser.
# -p makes parent directories as required, -R recursively applies the preceding command 
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/staticfiles /app/media
  chown -R appuser:appuser /app/staticfiles /app/media
fi

# 2) Wait for Postgres (cold starts can lag a bit)
if [ -n "$DB_HOST" ]; then
  echo "Waiting for database at $DB_HOST:$DB_PORT..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 0.2
  done
fi

# 3) Run Django management commands as the unprivileged user
# Running following commands as appuser(non-root) for safety reasons, "su" = subsitute user here. 
su -s /bin/sh -c "python manage.py migrate --noinput" appuser
su -s /bin/sh -c "python manage.py collectstatic --noinput" appuser

# 4) Start Gunicorn as the unprivileged user (proper signal handling via exec, exec makes sure su and then gunicorn are PID 1)
exec su -s /bin/sh -c "exec gunicorn myproject.wsgi:application \
  --bind 0.0.0.0:8000  \ 
  --workers 3  \ 
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --capture-output" appuser

