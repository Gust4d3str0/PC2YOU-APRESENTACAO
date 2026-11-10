import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


ComponentType = Literal["cpu", "gpu", "motherboard", "ram", "storage", "psu", "case"]
Usage = Literal["gaming", "programming", "general", "editing", "streaming", "3d_rendering", "ai_ml"]
Confidence = Literal["low", "medium", "high"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


def technical_text(value: str) -> str:
    # Do not pass secrets, contact details, URLs or instruction-like payloads to a provider.
    if re.search(
        r"@|https?://|\beyJ[\w-]+\.[\w-]+\.[\w-]+|AIza[\w-]+|"
        r"\b(?:sk|ghp)[_-][\w-]+|\b\d{10,}\b|\+?\d[\d ()-]{10,}\d|"
        r"(?:ignore|ignorar|desconsidere).{0,45}(?:instru|previous|anteriores)|"
        r"system\s*prompt|api[ _-]?key|password|senha|token\s*[:=]|"
        r"\b(?:email|e-mail|telefone|phone|jwt)\s*[:=]|[\x00-\x1f]",
        value, re.IGNORECASE,
    ):
        raise ValueError("Informe somente dados técnicos, sem instruções ou dados pessoais.")
    return " ".join(value.split())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Components(StrictModel):
    cpu: Name
    gpu: Name | None = None
    motherboard: Name | None = None
    ram: Name | None = None
    storage: list[Name] = Field(default_factory=list, max_length=8)
    psu: Name | None = None
    case: Name | None = None

    @field_validator("storage", mode="before")
    @classmethod
    def storage_list(cls, value):
        return [value] if isinstance(value, str) else value

    @field_validator("cpu", "gpu", "motherboard", "ram", "psu", "case")
    @classmethod
    def safe_name(cls, value):
        return technical_text(value) if value is not None else value

    @field_validator("storage")
    @classmethod
    def safe_storage(cls, value):
        return [technical_text(item) for item in value]


class AnalyzePCRequest(StrictModel):
    components: Components
    usage: list[Usage] = Field(min_length=1, max_length=7)
    resolution: Literal["1080p", "1440p", "4K"] = "1080p"
    refresh_rate: int | None = Field(default=None, ge=24, le=1000, strict=True)
    monitor: Name | None = None
    games: list[Name] = Field(default_factory=list, max_length=15)
    upgrade_budget: float | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("games")
    @classmethod
    def safe_games(cls, value):
        return list(dict.fromkeys(technical_text(item) for item in value))

    @field_validator("monitor")
    @classmethod
    def safe_monitor(cls, value):
        return technical_text(value) if value else value

    @field_validator("usage")
    @classmethod
    def unique_usage(cls, value):
        return list(dict.fromkeys(value))  # Order expresses the user's priorities.


class Balance(StrictModel):
    status: Literal["balanced", "attention", "insufficient_data"]
    explanation: Text


class PrimaryLimit(StrictModel):
    component: Literal["cpu", "gpu", "motherboard", "ram", "storage", "psu", "case", "unknown"]
    confidence: Confidence
    explanation: Text


class UpgradePriority(StrictModel):
    priority: int = Field(ge=1, le=7, strict=True)
    component_type: ComponentType
    reason: Text
    expected_benefit: Text
    budget_relevance: Literal["within_budget", "price_unavailable", "no_budget", "save_budget"]
    candidate_id: Name | None = None


class PCAnalysis(StrictModel):
    summary: Text
    overall_rating: Literal["good", "attention", "insufficient_data"]
    balance: Balance
    primary_limit: PrimaryLimit
    strengths: list[Text] = Field(default_factory=list, max_length=8)
    weaknesses: list[Text] = Field(default_factory=list, max_length=8)
    upgrade_priorities: list[UpgradePriority] = Field(default_factory=list, max_length=7)
    warnings: list[Text] = Field(default_factory=list, max_length=12)
    missing_information: list[Text] = Field(default_factory=list, max_length=15)
    final_recommendation: Text

    @model_validator(mode="after")
    def unique_priorities(self):
        priorities = self.upgrade_priorities
        if [item.priority for item in priorities] != list(range(1, len(priorities) + 1)):
            raise ValueError("Prioridades devem ser sequenciais")
        if len({item.component_type for item in priorities}) != len(priorities):
            raise ValueError("Tipo de componente repetido")
        return self


class TechnicalComponent(StrictModel):
    name: str
    category: ComponentType
    source: Literal["user", "catalog", "derived"]
    catalog_id: str | None = None
    specifications: dict = Field(default_factory=dict)
    compatibility: dict = Field(default_factory=dict)
    resolution_scope: Literal['sku', 'model', 'family', 'generic', 'unresolved'] | None = None
    field_sources: dict[str, str] = Field(default_factory=dict)


class CompatibilityResult(StrictModel):
    valid: bool | None
    status: Literal["compatible", "incompatible", "partial"]
    issues: list[str]
    warnings: list[str]
    checked_rules: list[str]
    unchecked_rules: list[str]


class UpgradeCandidate(StrictModel):
    component_id: str
    name: str
    component_type: ComponentType
    price: float | None


class AnalysisMetadata(StrictModel):
    provider: str
    model: str
    catalog_matches: int
    technical_matches: int = 0
    derived_matches: int = 0
    compatibility_checked: bool
    cached: bool
    prompt_version: str


class AnalyzePCResponse(StrictModel):
    analysis: PCAnalysis
    compatibility: CompatibilityResult
    compatibility_notes: list[str]
    components: list[TechnicalComponent]
    recommended_candidates: list[UpgradeCandidate]
    upgrade_budget: float | None
    metadata: AnalysisMetadata
