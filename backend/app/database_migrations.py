"""
Schema bootstrap.

The app used to call Base.metadata.create_all() at startup. That creates missing
*tables* but never alters existing ones, so the first column added to a live
database silently does not appear and every query touching it 500s.

ensure_schema() replaces that with real migrations, and handles the awkward
case of a database that predates Alembic:

  * fresh database        -> upgrade head (runs every migration)
  * existing, unversioned -> stamp the baseline, then upgrade head
  * already versioned     -> upgrade head
"""
import logging
import os

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from .database import engine, DATABASE_URL

logger = logging.getLogger("finmate.migrations")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_REVISION = "0001_baseline"


def _alembic_config() -> Config:
    ini_path = os.path.join(BASE_DIR, "alembic.ini")
    script_path = os.path.join(BASE_DIR, "alembic")

    # A container image that ships only `app/` has no migrations, and Alembic's
    # own error for that is opaque. Say exactly what is missing and where.
    missing = [p for p in (ini_path, script_path) if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(
            "Alembic migration files are missing from this deployment: "
            + ", ".join(missing)
            + ". The image must include alembic.ini and the alembic/ directory "
              "alongside app/ - see the COPY lines in backend/Dockerfile."
        )

    cfg = Config(ini_path)
    cfg.set_main_option("script_location", script_path)
    # Escape % so ConfigParser does not treat it as interpolation.
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return cfg


def current_revision():
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _pending_schema_changes() -> list:
    """
    Structural differences between the live database and the models.

    Only additions matter here: they tell us the database predates a migration.
    Cosmetic diffs (type spellings, index naming) vary by dialect and would
    otherwise make a healthy database look out of date.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from .database import Base
    from . import models  # noqa: F401 - registers tables on Base.metadata

    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    additions = []
    for diff in diffs:
        # Entries are tuples or lists of tuples; the first element is the kind.
        head = diff[0] if isinstance(diff, tuple) else (diff[0][0] if diff else None)
        kind = head[0] if isinstance(head, tuple) else head
        if kind in ("add_table", "add_column"):
            additions.append(diff)
    return additions


def ensure_schema() -> str:
    """Bring the database to head. Returns the resulting revision."""
    cfg = _alembic_config()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    has_alembic = "alembic_version" in tables
    has_app_tables = "users" in tables

    if has_app_tables and not has_alembic:
        # A database that predates Alembic. Which revision it corresponds to
        # depends on how it was created: an old deployment sits at the
        # baseline, whereas one bootstrapped by create_all() already has every
        # current column. Stamping the wrong one either skips a migration or
        # re-runs one that has already effectively been applied.
        try:
            pending = _pending_schema_changes()
        except Exception as e:
            logger.warning("Could not compare schema (%s) - assuming baseline.", e)
            pending = [True]

        if pending:
            logger.info(
                "Unversioned database is behind the models (%d pending additions) "
                "- stamping %s and migrating.", len(pending), BASELINE_REVISION,
            )
            command.stamp(cfg, BASELINE_REVISION)
        else:
            logger.info("Unversioned database already matches the models - stamping head.")
            command.stamp(cfg, "head")

    command.upgrade(cfg, "head")
    rev = current_revision()
    logger.info("Database schema at revision %s", rev)
    return rev


def post_migration_backfill() -> None:
    """
    Data fixes that must run after the schema is in place.

    Currently: populate dedupe_hash for transactions imported before de-dup
    existed, so re-uploading an old statement is correctly recognised.
    """
    from .database import SessionLocal
    from .services import dedupe

    db = SessionLocal()
    try:
        total = 0
        # Bounded loop - a very large table should not stall startup forever.
        for _ in range(40):
            n = dedupe.backfill_hashes(db, batch_size=500)
            total += n
            if n == 0:
                break
        if total:
            logger.info("Backfilled dedupe hashes for %d transactions.", total)
    except Exception as e:
        logger.warning("Dedupe backfill skipped: %s", e)
    finally:
        db.close()
