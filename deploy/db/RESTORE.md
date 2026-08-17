# Restore from wal-g backups (issue #62)

> **Implementation note — how this differs from the issue text.**
> Issue #62 assumes PostgreSQL runs directly on a bare-metal Ubuntu server
> (`/etc/postgresql/16/main`, systemd, host cron). In practice the DB runs in
> Docker on that box (`docker-compose.data.yml`, container `db`, with the
> `postgres_data` named volume). The goal is unchanged — continuous WAL
> archiving + weekly base backups to Cloudflare R2 for point-in-time recovery —
> but the mechanics are adapted:
>
> - wal-g is baked into the image via `Dockerfile.walg` instead of installed on
>   the host (wal-g has no Alpine builds, so the DB image is the Debian-based
>   `postgres:16`; the data volume is untouched).
> - WAL archiving is enabled with `-c` flags in the compose `command:` rather
>   than editing `postgresql.conf` + systemd restart.
> - R2 credentials are injected into the server `.env` by the CI/CD deploy
>   pipeline from GitHub Secrets instead of hand-written `/etc/wal-g.env`.
> - The config lives in the git repo (branch `issue62/db_backup`) rather than
>   only on the box — so the whole setup can be rebuilt on a fresh server
>   (see Scenario A). This is infra-as-code: merging to `main` only deploys the
>   wal-g-enabled container; **backups themselves run on a cron schedule on the
>   server, never from CI.**
> - Cron jobs still follow the issue's cadence (weekly full, keep last 4,
>   daily freshness) — see "Cron" below.

All restores run against R2 via the `createscale-postgres-walg:16` image.
The live DB is a container named `db` (`db-db-1`) from `docker-compose.data.yml`;
data lives in the `postgres_data` named volume.

Everything below is a **read-only** operation against R2 backups, except where
noted. The live database container is never touched during drills.

---

## Scenario A — DB server died, recover on a fresh server

1. Provision a new Hetzner server, install Docker + Compose, and rebuild the
   DB stack from the repo (this is why infra lives in git):

   ```bash
   git clone git@github.com:datatwine/CreateScale.git ~/AK
   cd ~/AK/deploy/db
   # populate .env (same values as the old box — incl. R2_BACKUP_* and DB creds)
   docker compose -f docker-compose.data.yml up -d --build
   ```

   This boots an **empty** `postgres_data` volume with a fresh Postgres.

2. Restore the latest base backup into the data dir (still stopped):

   ```bash
   docker compose -f docker-compose.data.yml stop db
   docker compose -f docker-compose.data.yml run --rm \
     -v ${PWD}/restore/:/restore:z db \
     wal-g backup-fetch /restore LATEST
   ```

3. Prepare recovery so Postgres replays WAL on next start:

   ```bash
   touch restore/recovery.signal
   cat >> restore/postgresql.auto.conf <<'EOF'
   restore_command = '/usr/local/bin/wal-g wal-fetch %f %p'
   recovery_target = 'immediate'
   EOF
   ```

4. Swap the restored data into the volume and start:

   ```bash
   docker compose -f docker-compose.data.yml exec -T db bash -c \
     "rm -rf /var/lib/postgresql/data/* && cp -a /restore/* /var/lib/postgresql/data/ && chown -R postgres:postgres /var/lib/postgresql/data"
   docker compose -f docker-compose.data.yml up -d db
   ```

5. Watch recovery complete, then point the app at the new host (DB_HOST in
   the app's env / k3s secrets) and re-apply the cron jobs (see below).

---

## Scenario B — Accidental data loss, roll back to a point in time

1. Stop the app so no new writes land during restore.
2. Recover time target: check app/PG logs for when the bad statement ran,
   pick 1–2 minutes **before** it, IST:

   ```
   recovery_target_time = '2026-07-17 14:25:00+05:30'
   ```

3. Same fetch + recovery prep as Scenario A, but with:

   ```
   restore_command = '/usr/local/bin/wal-g wal-fetch %f %p'
   recovery_target_time = '2026-07-17 14:25:00+05:30'
   recovery_target_inclusive = false
   recovery_target_action = 'promote'
   ```

   (`recovery_target_action='promote'` — once the target is reached, exit
   recovery and become a normal writable DB.)

4. Verify the bad data is gone, then point the app back (it was never moved)
   and delete any `main.bad`-style copy of the pre-restore data dir.

---

## Scenario C — Monthly sanity drill (port 5433, live DB untouched)

Run on the DB box itself against a scratch volume — the real container is
never touched.

```bash
set -a; source .env; set +a
docker compose -f docker-compose.data.yml run -d --rm \
  --name restore-drill \
  -e POSTGRES_PASSWORD="$DB_PASSWORD" \
  -e WALG_S3_PREFIX="$R2_BACKUP_S3_PREFIX" \
  -e AWS_REGION=auto -e AWS_S3_FORCE_PATH_STYLE=true \
  -e AWS_ENDPOINT="$R2_BACKUP_ENDPOINT" \
  -e AWS_ACCESS_KEY_ID="$R2_BACKUP_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$R2_BACKUP_SECRET_ACCESS_KEY" \
  -v drill_data:/var/lib/postgresql/data \
  createscale-postgres-walg:16 \
  wal-g backup-fetch /var/lib/postgresql/data LATEST
```

Then start a **separate** Postgres on the fetched data, port 5433:

```bash
docker run -d --name drill-pg \
  -v drill_data:/var/lib/postgresql/data \
  -p 5433:5432 \
  createscale-postgres-walg:16 \
  -c port=5432 \
  -c restore_command='wal-g wal-fetch %f %p' \
  -c recovery_target='immediate'
```

Wait for `database system is ready to accept connections`, then compare:

```bash
docker exec drill-pg psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT count(*) FROM bookings_engagement;"
docker exec db-db-1 psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT count(*) FROM bookings_engagement;"
```

Counts should match (or differ by only rows written since the last WAL
archive). Tear down:

```bash
docker rm -f drill-pg
docker volume rm drill_data
```

---

## Cron (apply once setup is verified)

```
0 3 * * 0  root  cd /root/AK/deploy/db && ./wal-g-backup.sh backup
0 4 * * *  root  cd /root/AK/deploy/db && ./wal-g-backup.sh cleanup
0 5 * * *  root  cd /root/AK/deploy/db && ./wal-g-backup.sh freshness || echo "WARNING: DB backup stale" | mail -s "DB backup stale (issue 62)" root
```

Freshness alert (email if the latest backup is older than 8 days) — the
`freshness` target in `wal-g-backup.sh` exits nonzero when stale:

```bash
./wal-g-backup.sh freshness       # prints age; exit 1 if > 8 days
```

(see the cron block above for the automated daily check)