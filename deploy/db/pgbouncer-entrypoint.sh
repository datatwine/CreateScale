#!/bin/sh
set -e

# Generate userlist.txt — printf handles special characters in DB_PASSWORD
# safely (no URL encoding, no heredoc escaping issues).
printf '"%s" "%s"\n' "$DB_USER" "$DB_PASSWORD" > /etc/pgbouncer/userlist.txt

# Generate pgbouncer.ini
cat > /etc/pgbouncer/pgbouncer.ini <<EOF
[databases]
$DB_NAME = host=db port=5432 dbname=$DB_NAME

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 5432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
default_pool_size = 50
max_client_conn = 5000
max_db_connections = 150
ignore_startup_parameters = extra_float_digits
admin_users = $DB_USER
EOF

exec pgbouncer /etc/pgbouncer/pgbouncer.ini
