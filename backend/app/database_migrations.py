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
    cfg = Config(os.path.join(BASE_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BASE_DIR, "alembic"))
    # Escape % so ConfigParser does not treat it as interpolation.
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return cfg


def current_revision():
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def ensure_schema() -> str:
    """Bring the database to head. Returns the resulting revision."""
    cfg = _alembic_config()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    has_alembic = "alembic_version" in tables
    has_app_tables = "users" in tables

    if has_app_tables and not has_alembic:
        # Pre-migration database: assume it matches the baseline, then migrate.
        logger.info("Existing unversioned database detected - stamping %s.", BASELINE_REVISION)
        command.stamp(cfg, BASELINE_REVISION)

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
