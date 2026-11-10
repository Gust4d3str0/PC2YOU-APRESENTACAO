from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class Price(BaseModel):
    store: str
    title: str | None = None
    price: float = Field(ge=0)
    url: HttpUrl | str
    thumbnail: HttpUrl | str | None = None
    images: list[HttpUrl | str] | None = None
    last_update: str
    source: str = "seed"
    availability: str = "Disponível"
    external_id: str | None = None
    condition: str | None = None
    seller: str | None = None
    catalog_product_id: str | None = None
    quality: dict[str, Any] | None = None
    product_match: dict[str, Any] | None = None
    equivalence_key: str | None = None
    url_source: str | None = None
    attributes: dict[str, Any] | None = None
    brand: str | None = None
    coupon: str | None = None
    valid_until: str | None = None
    coupon_valid_until: str | None = None
    conditional: bool | None = None
    status: str | None = None
    condition_labels: list[str] | None = None
    offer_id: str | None = None


class Benchmark(BaseModel):
    gaming_score: int | None = Field(default=None, ge=0, le=100)
    workstation_score: int | None = Field(default=None, ge=0, le=100)
    ai_score: int | None = Field(default=None, ge=0, le=100)


class ComponentBase(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str
    category: str
    brand: str
    image: HttpUrl | str
    real_image: HttpUrl | str | None = None
    image_source: str | None = None
    image_external_id: str | None = None
    images: list[HttpUrl | str] | None = None
    description: str
    technical_specs: dict[str, Any]
    compatibility: dict[str, Any]
    prices: list[Price]
    benchmark: Benchmark
    price_history: list[dict] = Field(default_factory=list)
    external_enrichment: dict[str, Any] | None = None
    identity_scope: str | None = None
    spec_provenance: dict[str, Any] | None = None
    aliases: list[str] = Field(default_factory=list)
    external_ids: dict[str, Any] = Field(default_factory=dict)
    normalized_name: str | None = None
    normalized_identity: str | None = None
    model: str | None = None
    mpn: list[str] = Field(default_factory=list)
    identity_variant: str | None = None


class ComponentCreate(ComponentBase):
    pass


class Component(ComponentBase):
    unverified_prices: list[Price] = Field(default_factory=list)


class ComponentUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    image: HttpUrl | str | None = None
    real_image: HttpUrl | str | None = None
    image_source: str | None = None
    image_external_id: str | None = None
    images: list[HttpUrl | str] | None = None
    description: str | None = None
    technical_specs: dict[str, Any] | None = None
    compatibility: dict[str, Any] | None = None
    prices: list[Price] | None = None
    benchmark: Benchmark | None = None
    price_history: list[dict] | None = None


class ComponentBatchRequest(BaseModel):
    component_ids: list[str] = Field(min_length=1)


class OfferValidation(BaseModel):
    """A person's check of one announced offer. `unknown` clears an earlier mark."""
    status: Literal['valid', 'invalid', 'unknown', 'working', 'not_working']   # last two: legacy aliases
    observed_price: float | None = Field(default=None, gt=0, le=1_000_000)
