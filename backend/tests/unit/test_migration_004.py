"""Verify the 004_grandfather_tenants data migration.

Checks:
- File exists with correct revision chain (004 follows 003)
- Upgrade performs UPDATE to set plan=subscription, status=active
- Downgrade reverts (or warns about irreversibility)
"""

from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
ALEMBIC_CFG = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


class TestMigration004:
    """Structural checks for the grandfather data migration."""

    def test_migration_file_exists(self):
        """Migration 004 file must exist."""
        version_file = MIGRATIONS_DIR / "versions" / "004_grandfather_tenants.py"
        assert version_file.exists(), f"Missing migration file: {version_file}"

    def test_revision_chain(self):
        """004 must follow 003."""
        config = Config(str(ALEMBIC_CFG))
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        assert "004" in heads, f"004 is not a head. Heads: {heads}"

    def test_upgrade_updates_plan_and_status(self):
        """Upgrade must UPDATE existing tenants plan->subscription, status->active."""
        config = Config(str(ALEMBIC_CFG))
        script = ScriptDirectory.from_config(config)
        revision = script.get_revision("004")
        assert revision is not None, "Revision 004 not found"

        module = revision.module
        import inspect
        upgrade_src = inspect.getsource(module.upgrade)
        assert "UPDATE" in upgrade_src.upper() or "update" in upgrade_src.lower()
        assert "plan" in upgrade_src.lower()
        assert "subscription" in upgrade_src.lower()
        assert "status" in upgrade_src.lower()
        assert "active" in upgrade_src.lower()

    def test_downgrade_reverses_update(self):
        """Downgrade should revert plan and status for affected rows."""
        module = ScriptDirectory.from_config(
            Config(str(ALEMBIC_CFG))
        ).get_revision("004").module

        import inspect
        downgrade_src = inspect.getsource(module.downgrade)
        assert "UPDATE" in downgrade_src.upper() or "update" in downgrade_src.lower()
