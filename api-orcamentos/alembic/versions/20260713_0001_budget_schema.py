"""Create or safely evolve the budgets schema.

The budgets service owns these tables. ``budgets.user_id`` intentionally remains
a logical reference to the users service; no cross-service foreign key is added.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260713_0001"
down_revision = None
branch_labels = None
depends_on = None

MAX_QUANTITY = 16


def _inspector():
    return sa.inspect(op.get_bind())


def _check_names(table: str) -> set[str]:
    return {item.get("name") for item in _inspector().get_check_constraints(table) if item.get("name")}


def _index_names(table: str) -> set[str]:
    return {item.get("name") for item in _inspector().get_indexes(table) if item.get("name")}


def _column_names(table: str) -> set[str]:
    return {item["name"] for item in _inspector().get_columns(table)}


def _create_empty_schema() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
            comment="Logical owner id from api-usuarios; intentionally not a database foreign key.",
        ),
        sa.Column("name", sa.String(length=120), nullable=False, server_default="Orçamento OrçaPC"),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("performance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("total_price >= 0", name="ck_budget_total_nonnegative"),
    )
    op.create_index("ix_budgets_id", "budgets", ["id"])
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"])

    op.create_table(
        "budget_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "budget_id",
            sa.Integer(),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("best_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("store", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.CheckConstraint(
            f"quantity >= 1 AND quantity <= {MAX_QUANTITY}",
            name="ck_budget_item_quantity",
        ),
        sa.CheckConstraint("best_price >= 0", name="ck_budget_item_price_nonnegative"),
    )
    op.create_index("ix_budget_items_id", "budget_items", ["id"])
    op.create_index("ix_budget_items_component_id", "budget_items", ["component_id"])
    op.create_index("ix_budget_items_category", "budget_items", ["category"])


def _evolve_budgets() -> None:
    dialect = op.get_bind().dialect.name
    op.execute(sa.text("UPDATE budgets SET total_price = 0 WHERE total_price IS NULL OR total_price < 0"))
    if dialect == "postgresql":
        op.execute(sa.text("UPDATE budgets SET total_price = ROUND(total_price::numeric, 2)"))
    else:
        op.execute(sa.text("UPDATE budgets SET total_price = ROUND(total_price, 2)"))
    checks = _check_names("budgets")
    alter_kwargs = {"postgresql_using": "ROUND(total_price::numeric, 2)"} if dialect == "postgresql" else {}
    with op.batch_alter_table("budgets", recreate="auto") as batch:
        batch.alter_column(
            "total_price",
            existing_type=sa.Float(),
            type_=sa.Numeric(12, 2),
            existing_nullable=True,
            nullable=False,
            server_default="0",
            **alter_kwargs,
        )
        if "ck_budget_total_nonnegative" not in checks:
            batch.create_check_constraint("ck_budget_total_nonnegative", "total_price >= 0")

    if dialect == "postgresql":
        op.execute(
            "COMMENT ON COLUMN budgets.user_id IS "
            "'Logical owner id from api-usuarios; intentionally not a database foreign key.'"
        )

    indexes = _index_names("budgets")
    if "ix_budgets_id" not in indexes:
        op.create_index("ix_budgets_id", "budgets", ["id"])
    if "ix_budgets_user_id" not in indexes:
        op.create_index("ix_budgets_user_id", "budgets", ["user_id"])


def _evolve_budget_items() -> None:
    if "quantity" not in _column_names("budget_items"):
        op.add_column("budget_items", sa.Column("quantity", sa.Integer(), nullable=True, server_default="1"))

    dialect = op.get_bind().dialect.name
    op.execute(sa.text("UPDATE budget_items SET quantity = 1 WHERE quantity IS NULL OR quantity < 1"))
    op.execute(sa.text(f"UPDATE budget_items SET quantity = {MAX_QUANTITY} WHERE quantity > {MAX_QUANTITY}"))
    op.execute(sa.text("UPDATE budget_items SET best_price = 0 WHERE best_price IS NULL OR best_price < 0"))
    if dialect == "postgresql":
        op.execute(sa.text("UPDATE budget_items SET best_price = ROUND(best_price::numeric, 2)"))
    else:
        op.execute(sa.text("UPDATE budget_items SET best_price = ROUND(best_price, 2)"))
    checks = _check_names("budget_items")
    alter_kwargs = {"postgresql_using": "ROUND(best_price::numeric, 2)"} if dialect == "postgresql" else {}
    with op.batch_alter_table("budget_items", recreate="auto") as batch:
        batch.alter_column(
            "quantity",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
            server_default="1",
        )
        batch.alter_column(
            "best_price",
            existing_type=sa.Float(),
            type_=sa.Numeric(12, 2),
            existing_nullable=True,
            nullable=False,
            **alter_kwargs,
        )
        if "ck_budget_item_quantity" not in checks:
            batch.create_check_constraint(
                "ck_budget_item_quantity",
                f"quantity >= 1 AND quantity <= {MAX_QUANTITY}",
            )
        if "ck_budget_item_price_nonnegative" not in checks:
            batch.create_check_constraint("ck_budget_item_price_nonnegative", "best_price >= 0")

    indexes = _index_names("budget_items")
    for name, column in (
        ("ix_budget_items_id", "id"),
        ("ix_budget_items_component_id", "component_id"),
        ("ix_budget_items_category", "category"),
    ):
        if name not in indexes:
            op.create_index(name, "budget_items", [column])


def upgrade() -> None:
    tables = set(_inspector().get_table_names())
    if "budgets" not in tables and "budget_items" not in tables:
        _create_empty_schema()
        return
    if "budgets" not in tables or "budget_items" not in tables:
        raise RuntimeError("Schema parcial de orçamentos detectado; migração interrompida sem apagar dados.")

    _evolve_budgets()
    _evolve_budget_items()


def downgrade() -> None:
    # Intentionally non-destructive: reverting Numeric/constraints could lose data.
    pass
