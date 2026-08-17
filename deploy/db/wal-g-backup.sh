#!/usr/bin/env bash
# =============================================================================
# wal-g wrapper for the DB box — drives backups from the host shell / cron.
#
# USAGE:
#   ./wal-g-backup.sh backup      # push a full base backup to R2
#   ./wal-g-backup.sh cleanup     # keep last 4 FULL backups + their WAL
#   ./wal-g-backup.sh list        # show backups in R2
#   ./wal-g-backup.sh verify      # wal-verify integrity (WAL continuity)
#   ./wal-g-backup.sh freshness   # 0 if latest backup < 8 days old (cron check)
#
# Run from deploy/db/ on the box (compose project dir), so compose picks up
# the local .env. All env (R2 creds, PGUSER/PGPASSWORD for wal-g's side
# connection) already live in the container from docker-compose.data.yml.
# =============================================================================
set -euo pipefail

COMPOSE_FILE="docker-compose.data.yml"
LOG_DIR="/var/log/wal-g"

usage() {
    echo "Usage: $0 {backup|cleanup|list|verify}" >&2
    exit 1
}

[ $# -eq 1 ] || usage
CMD="$1"

walg() {
    docker compose -f "$COMPOSE_FILE" exec -T db wal-g "$@"
}

case "$CMD" in
    backup)
        mkdir -p "$LOG_DIR"
        echo "$(date -Is) --- backup-push start" >> "$LOG_DIR/backup.log"
        walg backup-push /var/lib/postgresql/data >> "$LOG_DIR/backup.log" 2>&1
        echo "$(date -Is) --- backup-push done" >> "$LOG_DIR/backup.log"
        ;;
    cleanup)
        mkdir -p "$LOG_DIR"
        echo "$(date -Is) --- cleanup start" >> "$LOG_DIR/cleanup.log"
        walg delete retain FULL 4 --confirm >> "$LOG_DIR/cleanup.log" 2>&1
        echo "$(date -Is) --- cleanup done" >> "$LOG_DIR/cleanup.log"
        ;;
    list)
        walg backup-list
        ;;
    verify)
        walg wal-verify integrity
        ;;
    freshness)
        # Exit nonzero if the newest base backup is older than 8 days.
        LAST=$(walg backup-list --pretty --json 2>/dev/null | tail -1 || true)
        if [ -z "$LAST" ]; then
            echo "ERROR: no backups found (R2 empty or creds bad)" >&2
            exit 1
        fi
        TS=$(echo "$LAST" | python3 -c "import sys,json; b=json.load(sys.stdin); print(b['time'].rstrip('Z') + 'Z')")
        NOW=$(python3 -c "import datetime; print(datetime.datetime.now(datetime.timezone.utc).isoformat())")
        python3 -c "
import datetime
d = datetime.datetime.fromisoformat('$TS')
n = datetime.datetime.fromisoformat('$NOW')
age = (n - d).days
print(f'latest backup: {d.isoformat()} ({age}d old)')
raise SystemExit(0 if age <= 8 else 1)
"
        ;;
    *)
        usage
        ;;
esac