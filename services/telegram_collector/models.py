from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class PromotionStatus(str, Enum):
    PENDING = "pending"
    PARSED = "parsed"
    MATCHED = "matched"
    VERIFIED = "verified"
    PUBLISHED = "published"
    IGNORED = "ignored"


@dataclass(frozen=True)
class PriceAlert:
    """Contrato persistido de acompanhamento; user_id é opcional nesta etapa."""

    telegram_user_id: int
    query: str
    max_price: Decimal | None
    component_type: str | None = None
    user_id: str | None = None
    normalized_terms: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    ignored_brands: list[str] = field(default_factory=list)
    stores: list[str] = field(default_factory=list)
    ignored_stores: list[str] = field(default_factory=list)
    minimum_discount: Decimal | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
