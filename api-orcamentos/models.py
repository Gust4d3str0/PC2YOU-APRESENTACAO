from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from database import Base


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (CheckConstraint("total_price >= 0", name="ck_budget_total_nonnegative"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Logical owner id from api-usuarios; intentionally not a database foreign key.",
    )
    name = Column(String(120), nullable=False, default="Orçamento OrçaPC")
    total_price = Column(Numeric(12, 2), nullable=False, default=0)
    performance = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    items = relationship(
        "BudgetItem",
        cascade="all, delete-orphan",
        back_populates="budget",
        lazy="joined",
    )


class BudgetItem(Base):
    __tablename__ = "budget_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1 AND quantity <= 16", name="ck_budget_item_quantity"),
        CheckConstraint("best_price >= 0", name="ck_budget_item_price_nonnegative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    component_id = Column(String(120), nullable=False, index=True)
    name = Column(String(180), nullable=False)
    category = Column(String(60), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    best_price = Column(Numeric(12, 2), nullable=False)
    store = Column(String(120), nullable=False)
    url = Column(String(500), nullable=False)

    budget = relationship("Budget", back_populates="items")
