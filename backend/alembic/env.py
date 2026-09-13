"""Alembic environment - reads the app's own engine/metadata so migrations and
models can never drift apart."""
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv

load_dotenv()

from app.database import DATABASE_URL, Base  # noqa: E402
from app import models  # noqa: F401,E402  - registers all tables on Base.metadata

config = context.config

# Default to the app's database, but never clobber a URL the caller set
# explicitly - that override is how migrations get pointed at another database.
if not (config.get_main_option("sqlalchemy.url") or "").strip():
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER most things in place; batch mode rewrites the table.
        render_as_batch=DATABASE_URL.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine, pool

    from app.database import engine as app_engine

    # Reuse the app's pooled engine when migrating the app's own database, but
    # honour an explicitly configured URL so migrations can be run against
    # another database (a test fixture, or `alembic upgrade` pointed at a
    # staging copy) instead of silently hitting the app's.
    configured = config.get_main_option("sqlalchemy.url")
    if configured and configured != DATABASE_URL:
        connectable = create_engine(configured, poolclass=pool.NullPool)
    else:
        connectable = app_engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=DATABASE_URL.startswith("sqlite"),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
