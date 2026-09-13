"""
Deployment packaging guards.

A production deploy failed because the Dockerfile copied only `app/`, so
alembic.ini and alembic/ never reached the image. Alembic then failed, startup
fell back to create_all() — which cannot add a column to an existing table —
and the app died later on "column users.plan does not exist".

These tests fail at CI time instead.
"""
import os
import re

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKERFILE = os.path.join(BACKEND_DIR, "Dockerfile")


def _dockerfile() -> str:
    with open(DOCKERFILE, encoding="utf-8") as fh:
        return fh.read()


class TestDockerImageContents:
    def test_dockerfile_exists(self):
        assert os.path.exists(DOCKERFILE)

    @pytest.mark.parametrize("target", ["alembic.ini", "alembic"])
    def test_migrations_are_copied_into_the_image(self, target):
        """Without these the container cannot migrate and the deploy breaks."""
        content = _dockerfile()
        pattern = rf"^\s*COPY\s+.*\b{re.escape(target)}\b"
        assert re.search(pattern, content, re.M), (
            f"Dockerfile must COPY {target} into the image - a deploy without "
            f"it fails on the first schema change."
        )

    def test_app_package_is_copied(self):
        assert re.search(r"^\s*COPY\s+app\b", _dockerfile(), re.M)

    def test_requirements_are_installed(self):
        assert "requirements.txt" in _dockerfile()


class TestMigrationAssets:
    def test_alembic_config_present(self):
        assert os.path.exists(os.path.join(BACKEND_DIR, "alembic.ini"))

    def test_versions_directory_has_migrations(self):
        versions = os.path.join(BACKEND_DIR, "alembic", "versions")
        assert os.path.isdir(versions)
        revisions = [f for f in os.listdir(versions) if f.endswith(".py")]
        assert revisions, "no migration scripts found"

    def test_env_py_present(self):
        assert os.path.exists(os.path.join(BACKEND_DIR, "alembic", "env.py"))

    def test_missing_migration_files_give_an_actionable_error(self, monkeypatch):
        """The opaque Alembic error is what made the original failure hard to read."""
        from app import database_migrations

        monkeypatch.setattr(database_migrations, "BASE_DIR", "/nonexistent-path")
        with pytest.raises(FileNotFoundError) as exc:
            database_migrations._alembic_config()

        message = str(exc.value)
        assert "alembic.ini" in message
        assert "Dockerfile" in message, "the error should say how to fix it"


class TestRenderBlueprint:
    def _render_yaml(self) -> str:
        path = os.path.join(os.path.dirname(BACKEND_DIR), "render.yaml")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_sets_production_env(self):
        """ENV=production activates the startup safety checks."""
        assert re.search(r"key:\s*ENV\s*\n\s*value:\s*production", self._render_yaml())

    def test_jwt_secret_is_generated(self):
        assert re.search(r"key:\s*JWT_SECRET\s*\n\s*generateValue:\s*true", self._render_yaml())


class TestStartupSafety:
    def test_create_all_is_not_used_as_a_blind_fallback(self):
        """
        A populated database must never be "repaired" with create_all(): it
        silently leaves old tables missing their new columns.
        """
        main_py = os.path.join(BACKEND_DIR, "app", "main.py")
        with open(main_py, encoding="utf-8") as fh:
            source = fh.read()

        assert "create_all" in source, "bootstrap path removed entirely?"
        # The fallback must be guarded by an emptiness check.
        assert "get_table_names" in source, (
            "main.py must check whether the database is empty before falling "
            "back to create_all()"
        )
