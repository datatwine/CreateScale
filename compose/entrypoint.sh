#!/usr/bin/env sh
set -e

# 1) If running as root (UID 0), fix ownership on mounted volumes.
#    New Docker named volumes start root:root, which breaks collectstatic for appuser.
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/staticfiles /vol/static
  chown -R appuser:appuser /app/staticfiles /vol/static
fi

# 2) Wait for remote Postgres on the DB Box
if [ -n "$DB_HOST" ]; then
  echo "Waiting for database at $DB_HOST:$DB_PORT..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 0.2
  done
fi

# 3) Run migrations ONLY on the OD instance (RUN_MIGRATIONS=1).
#    Spot instances set RUN_MIGRATIONS=0 (or omit it) to avoid race conditions
#    when 13+ instances boot simultaneously and all try to ALTER TABLE.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "OD instance — running migrations..."
  su -s /bin/sh -c "python manage.py migrate --noinput" appuser
else
  echo "Spot instance — skipping migrations."
fi

# 4) collectstatic runs on ALL instances (OD + Spot).
#    ManifestStaticFilesStorage requires the staticfiles.json manifest to exist,
#    otherwise every {% static %} tag crashes with a 500.
echo "Running collectstatic..."
su -s /bin/sh -c "python manage.py collectstatic --noinput" appuser

# 5) Setup Prometheus multiprocess directory for django-prometheus
export PROMETHEUS_MULTIPROC_DIR=/tmp/metrics
rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
chown -R appuser:appuser "$PROMETHEUS_MULTIPROC_DIR"

# 6) Start Gunicorn as the unprivileged user
#    exec ensures Gunicorn becomes PID 1 for proper signal handling
exec su -s /bin/sh -c "exec gunicorn myproject.wsgi:application \
  --bind 0.0.0.0:8000  \
  --worker-class gthread \
  --workers ${WEB_CONCURRENCY:-3} \
  --threads  ${WEB_THREADS:-2} \
  --timeout  ${WEB_TIMEOUT:-30} \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --capture-output" appuser
