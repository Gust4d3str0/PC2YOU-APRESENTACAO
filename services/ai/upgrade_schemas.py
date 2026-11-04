from typing import Literal

from pydantic import Field, model_validator

from .schemas import (AnalyzePCRequest, AnalysisMetadata, CompatibilityResult, ComponentType,
                      Confidence, Name, StrictModel, TechnicalComponent, Text)


class RecommendUpgradesRequest(AnalyzePCRequest):
    include_promotions: bool = Field(default=True, strict=True)


class UpgradeChoice(StrictModel):
    priority: int = Field(ge=1, le=5, strict=True)
    component_type: ComponentType
    candidate_id: Name
    reason: Text
    confidence: Confidence
    budget_relevance: Literal["within_budget", "price_unavailable", "no_budget", "save_budget"]


class BuyOpportunity(StrictModel):
    candidate_id: Name
    promotion_id: Name


class UpgradeAnalysis(StrictModel):
    summary: Text
    recommended_upgrades: list[UpgradeChoice] = Field(default_factory=list, max_length=5)
    buy_now_opportunities: list[BuyOpportunity] = Field(default_factory=list, max_length=5)
    warnings: list[Text] = Field(default_factory=list, max_length=12)
    final_recommendation: Text

    @model_validator(mode="after")
    def unique_choices(self):
        items = self.recommended_upgrades
        if [i.priority for i in items] != list(range(1, len(items) + 1)):
            raise ValueError("Prioridades devem ser sequenciais")
        if len({i.component_type for i in items}) != len(items):
            raise ValueError("Apenas uma substituição por categoria")
        if len({i.candidate_id for i in self.buy_now_opportunities}) != len(self.buy_now_opportunities):
            raise ValueError("Apenas uma oportunidade por candidato")
        return self


class PromotionOffer(StrictModel):
    promotion_id: str
    component_id: str
    title: str
    store: str | None
    price: float
    original_price: float | None
    coupon: str | None
    url: str | None
    observed_at: str
    source: Literal["telegram"] = "telegram"
    is_conditional: bool = False
    conditions: list[str] = Field(default_factory=list)
    status: str | None = None


class KnownPrice(StrictModel):
    value: float | None
    source: Literal["telegram", "catalog_real", "catalog_reference", "unavailable"]
    verified: bool
    store: str | None = None
    conditional: bool = False
    conditions: list[str] = Field(default_factory=list)


class PriceHistory(StrictModel):
    historical_average: float
    historical_min: float
    samples: int
    source: Literal["catalog_real"] = "catalog_real"


class EnrichedUpgrade(StrictModel):
    candidate_id: str
    component: TechnicalComponent
    price: KnownPrice
    catalog_price: float | None
    promotion: PromotionOffer | None
    promotions: list[PromotionOffer]
    history: PriceHistory | None
    compatibility: CompatibilityResult
    opportunity_evidence: Literal["below_verified_catalog", "below_historical_average", "insufficient_data"]


class UpgradeMetadata(AnalysisMetadata):
    candidate_count: int
    matched_promotions: int
    promotions_available: bool


class RecommendUpgradesResponse(StrictModel):
    analysis: UpgradeAnalysis
    recommendations: list[EnrichedUpgrade]
    compatibility: CompatibilityResult
    warnings: list[str]
    upgrade_budget: float | None
    metadata: UpgradeMetadata
