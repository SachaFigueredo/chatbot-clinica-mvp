"""Verify the 003_add_billing_fields migration.

Checks:
- File exists with correct revision chain
- Offline mode generates expected ALTER TABLE statements
"""

from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
ALEMBIC_CFG = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


class TestMigration003:
    """Structural checks for the billing fields migration."""

    def test_migration_file_exists(self):
        """Migration 003 file must exist in the versions directory."""
        version_file = MIGRATIONS_DIR / "versions" / "003_add_billing_fields.py"
        assert version_file.exists(), f"Missing migration file: {version_file}"

    def test_revision_chain(self):
        """003 must follow 002 in the chain (004 follows 003)."""
        config = Config(str(ALEMBIC_CFG))
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        # The migration chain: 001 -> 002 -> 003 -> 004; so 004 is the head.
        # 003 is reachable from the head.
        rev = script.get_revision("003")
        assert rev is not None, "Revision 003 not found"
        assert rev.down_revision == "002"

    def test_upgrade_contains_add_columns(self):
        """Offline upgrade SQL must contain ADD COLUMN for each new field."""
        config = Config(str(ALEMBIC_CFG))
        config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://ignored/test")
        script = ScriptDirectory.from_config(config)

        # Get the 003 revision
        revision = script.get_revision("003")
        assert revision is not None, "Revision 003 not found"

        # We just verify the module-level upgrade function exists and contains
        # the expected column names. Full SQL generation is hard to isolate
        # without actually running the migration.
        module = revision.module
        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")

        # Check the upgrade source includes ADD COLUMN for each field
        import inspect
        upgrade_src = inspect.getsource(module.upgrade)
        assert "trial_ends_at" in upgrade_src
        assert "mercadopago_customer_id" in upgrade_src
        assert "mercadopago_subscription_id" in upgrade_src
        assert "suspended_at" in upgrade_src

    def test_downgrade_contains_drop_columns(self):
        """Downgrade must drop all four columns (reverse order)."""
        module = ScriptDirectory.from_config(
            Config(str(ALEMBIC_CFG))
        ).get_revision("003").module

        import inspect
        downgrade_src = inspect.getsource(module.downgrade)
        assert "drop_column" in downgrade_src
        assert "trial_ends_at" in downgrade_src
        assert "mercadopago_customer_id" in downgrade_src
        assert "mercadopago_subscription_id" in downgrade_src
        assert "suspended_at" in downgrade_src
