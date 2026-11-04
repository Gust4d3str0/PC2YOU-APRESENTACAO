from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


UserId = Annotated[int, Field(gt=0)]
ComponentId = Annotated[str, Field(min_length=1, max_length=120)]
Quantity = Annotated[int, Field(ge=1, le=16)]
BudgetName = Annotated[str, Field(min_length=1, max_length=120)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BudgetCreate(StrictModel):
    user_id: UserId
    name: BudgetName = "Orçamento OrçaPC"
    components: list[ComponentId] = Field(default_factory=list)
    quantities: dict[ComponentId, Quantity] = Field(default_factory=dict)


class BudgetUpdate(StrictModel):
    name: BudgetName | None = None
    components: list[ComponentId] | None = None
    quantities: dict[ComponentId, Quantity] | None = None


class BudgetItemResponse(BaseModel):
    component_id: str
    name: str
    category: str
    quantity: int = 1
    best_price: Decimal
    store: str
    url: str


class BudgetResponse(BaseModel):
    budget_id: int
    user_id: int
    name: str
    items: list[BudgetItemResponse]
    total_price: Decimal
    performance: dict


class CompatibilityCheck(StrictModel):
    cpu_id: str | None = None
    cooler_id: str | None = None
    motherboard_id: str | None = None
    ram_id: str | None = None
    storage_id: str | None = None
    gpu_id: str | None = None
    psu_id: str | None = None
    case_id: str | None = None


class NextOptionsRequest(StrictModel):
    selected_components: dict[str, ComponentId] = Field(default_factory=dict)


class BuildFinalize(StrictModel):
    user_id: UserId
    components: list[ComponentId]
    name: BudgetName = "Orçamento OrçaPC"
    quantities: dict[ComponentId, Quantity] = Field(default_factory=dict)
