# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for psycopg2 and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt /app/

# after COPY requirements.txt /app/
RUN python - <<'PY'
p='requirements.txt'
b=open(p,'rb').read()
# Convert UTF-16LE -> UTF-8; strip UTF-8 BOM if present
if b.startswith(b'\xff\xfe'):
    b = b.decode('utf-16le').encode('utf-8')
elif b.startswith(b'\xef\xbb\xbf'):
    b = b[3:]
open(p,'wb').write(b)
print('Normalized requirements.txt to UTF-8')
PY
RUN python -m pip install --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt


RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Paths for static/media; non-root user
RUN mkdir -p /vol/static /vol/media && adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /vol /app

# Entrypoint
COPY compose/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser
EXPOSE 8000

CMD ["/entrypoint.sh"]
