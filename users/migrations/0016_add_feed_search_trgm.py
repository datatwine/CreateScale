from django.db import migrations
from django.db.utils import IntegrityError


def _is_postgres(schema_editor):
    return schema_editor.connection.vendor == "postgresql"


def add_feed_search_indexes(apps, schema_editor):
    """Create the pg_trgm extension + GIN trigram indexes for feed search.

    GIN trigram indexes (gin_trgm_ops) make ILIKE '%query%' lookups use an
    index scan instead of a sequential scan. We add them to the three fields
    the feed search filters on: auth_user.username (raw DDL — Django owns the
    built-in User model, so we can't add indexes via its Meta), and
    profession + location on users_profile.

    PostgreSQL-only: pg_trgm / GIN don't exist on SQLite (local dev/tests).
    The vendor guard makes this migration a no-op there while still running
    in production/CI (which use PostgreSQL).
    """
    if not _is_postgres(schema_editor):
        return

    try:
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except IntegrityError:
        # Postgres can throw a unique violation on IF NOT EXISTS if run concurrently (e.g. by CI workers)
        pass
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS user_username_trgm "
        "ON auth_user USING gin (username gin_trgm_ops);"
    )
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS profile_profession_trgm "
        "ON users_profile USING gin (profession gin_trgm_ops);"
    )
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS profile_location_trgm "
        "ON users_profile USING gin (location gin_trgm_ops);"
    )


def remove_feed_search_indexes(apps, schema_editor):
    if not _is_postgres(schema_editor):
        return

    schema_editor.execute("DROP INDEX IF EXISTS user_username_trgm;")
    schema_editor.execute("DROP INDEX IF EXISTS profile_profession_trgm;")
    schema_editor.execute("DROP INDEX IF EXISTS profile_location_trgm;")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("users", "0015_pushtoken"),
    ]

    operations = [
        migrations.RunPython(
            add_feed_search_indexes,
            remove_feed_search_indexes,
        ),
    ]
