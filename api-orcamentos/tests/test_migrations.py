from pathlib import Path
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


SERVICE_DIR = Path(__file__).resolve().parents[1]


def upgrade(database_url: str) -> None:
    config = Config(str(SERVICE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def test_initial_migration_creates_empty_database(tmp_path):
    database = tmp_path / "empty.db"
    url = f"sqlite:///{database.as_posix()}"
    upgrade(url)

    engine = sa.create_engine(url)
    inspector = sa.inspect(engine)
    assert {"budgets", "budget_items", "alembic_version_budgets"}.issubset(
        inspector.get_table_names()
    )
    budget_types = {item["name"]: item["type"] for item in inspector.get_columns("budgets")}
    item_columns = {item["name"]: item for item in inspector.get_columns("budget_items")}
    assert isinstance(budget_types["total_price"], sa.Numeric)
    assert isinstance(item_columns["best_price"]["type"], sa.Numeric)
    assert item_columns["quantity"]["nullable"] is False

    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version_budgets")) == "20260713_0001"
    engine.dispose()


def test_initial_migration_evolves_legacy_schema_without_losing_rows(tmp_path):
    database = tmp_path / "legacy.db"
    url = f"sqlite:///{database.as_posix()}"
    engine = sa.create_engine(url)
    metadata = sa.MetaData()
    budgets = sa.Table(
        "budgets",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("total_price", sa.Float(), nullable=True),
        sa.Column("performance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    items = sa.Table(
        "budget_items",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("budget_id", sa.Integer(), sa.ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_id", sa.String(120), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("best_price", sa.Float(), nullable=True),
        sa.Column("store", sa.String(120), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            budgets.insert(),
            {
                "id": 1,
                "user_id": 7,
                "name": "Legado",
                "total_price": 123.456,
                "performance": {},
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )
        connection.execute(
            items.insert(),
            {
                "id": 1,
                "budget_id": 1,
                "component_id": "cpu",
                "name": "CPU",
                "category": "cpu",
                "quantity": None,
                "best_price": 123.456,
                "store": "Loja",
                "url": "https://shop.test/cpu",
            },
        )
    engine.dispose()

    upgrade(url)

    engine = sa.create_engine(url)
    inspector = sa.inspect(engine)
    budget_columns = {item["name"]: item for item in inspector.get_columns("budgets")}
    item_columns = {item["name"]: item for item in inspector.get_columns("budget_items")}
    checks = {item["name"] for item in inspector.get_check_constraints("budget_items")}
    assert isinstance(budget_columns["total_price"]["type"], sa.Numeric)
    assert isinstance(item_columns["best_price"]["type"], sa.Numeric)
    assert item_columns["quantity"]["nullable"] is False
    assert {"ck_budget_item_quantity", "ck_budget_item_price_nonnegative"}.issubset(checks)
    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT user_id, total_price FROM budgets WHERE id = 1")
        ).one()
        item = connection.execute(
            sa.text("SELECT quantity, best_price FROM budget_items WHERE id = 1")
        ).one()
    assert row.user_id == 7
    assert float(row.total_price) == 123.46
    assert item.quantity == 1
    assert float(item.best_price) == 123.46
    engine.dispose()
