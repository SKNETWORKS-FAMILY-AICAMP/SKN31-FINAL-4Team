from contextlib import contextmanager

from django.db import connection


class CollectionAlreadyRunning(RuntimeError):
    """Raised when another NAVER collection command is already running."""


# A stable, project-specific PostgreSQL advisory-lock key.  This keeps every
# `collect_naver` invocation mutually exclusive, regardless of its --source.
NAVER_COLLECTION_LOCK_KEY = 7_235_202_608_20


@contextmanager
def naver_collection_lock():
    """Acquire the NAVER collection lock without waiting for another runner."""
    # SQLite is used only for local experiments. Its request-history table still
    # suppresses repeat requests; run one collection command at a time.
    if connection.vendor == "sqlite":
        yield
        return

    if connection.vendor != "postgresql":
        raise RuntimeError("NAVER collection locking requires PostgreSQL.")

    acquired = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [NAVER_COLLECTION_LOCK_KEY])
        acquired = cursor.fetchone()[0]

    if not acquired:
        raise CollectionAlreadyRunning(
            "A NAVER collection is already running. This run was stopped to prevent duplicate API requests."
        )

    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [NAVER_COLLECTION_LOCK_KEY])
