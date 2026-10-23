from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db import Base


def test_migrations_match_models(tmp_path):
    """Fails if someone changes a model without writing a migration."""
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    config = Config("alembic.ini")
    config.attributes["url"] = url
    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []

    command.downgrade(config, "base")
