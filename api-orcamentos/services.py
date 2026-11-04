from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import models
from catalog_client import catalog_client
from compatibility import STEP_CATEGORIES, check_components
from performance import estimate_performance


MONEY_QUANTUM = Decimal("0.01")
REQUIRED_CATEGORY_LABELS = {
    "cpu": "CPU",
    "cooler": "cooler",
    "motherboard": "placa-mãe",
    "ram": "RAM",
    "storage": "armazenamento",
    "gpu": "GPU",
    "psu": "fonte",
    "case": "gabinete",
}


def fetch_component(component_id: str) -> dict:
    return catalog_client.get_component(component_id)


def fetch_components(component_ids: list[str]) -> list[dict]:
    components = catalog_client.get_components(component_ids)
    by_id = {str(component.get("id")): component for component in components}
    if len(by_id) != len(components) or set(by_id) - set(component_ids):
        raise HTTPException(status_code=503, detail="Resposta inválida do catálogo")
    missing = set(component_ids) - set(by_id)
    if missing:
        raise HTTPException(status_code=404, detail="Peça não encontrada no catálogo")
    return [by_id[component_id] for component_id in component_ids]


def list_catalog_components(category: str | None = None) -> list[dict]:
    return catalog_client.list_components(category)


def catalog_health() -> None:
    catalog_client.health()


def ensure_user_exists(db: Session, user_id: int) -> None:
    try:
        exists = db.execute(
            text("SELECT 1 FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        ).first()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Serviço de usuários indisponível") from exc
    if not exists:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")


def _money(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Preço inválido recebido do catálogo") from exc
    if not amount.is_finite() or amount <= 0:
        raise HTTPException(status_code=503, detail="Preço inválido recebido do catálogo")
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def get_best_price(component: dict) -> dict:
    prices = component.get("prices", [])
    if not prices:
        raise HTTPException(status_code=503, detail="Peça sem preço disponível no catálogo")
    if any(not isinstance(item, dict) or "price" not in item for item in prices):
        raise HTTPException(status_code=503, detail="Resposta inválida do catálogo")
    # Unconditional offers first; a coupon/conditional price only when it is all there is.
    general = [item for item in prices if not item.get("conditional") and not item.get("coupon")]
    return min(general or prices, key=lambda item: _money(item["price"]))


def quote_component(component: dict, quantity: int = 1) -> dict:
    price = get_best_price(component)
    unit_price = _money(price["price"])
    line_price = (unit_price * quantity).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return {
        "component_id": component["id"],
        "name": component["name"],
        "category": component["category"],
        "quantity": quantity,
        "best_price": line_price,
        "store": price["store"],
        "url": str(price["url"]),
    }


def budget_to_response(budget: models.Budget) -> dict:
    return {
        "budget_id": budget.id,
        "user_id": budget.user_id,
        "name": budget.name,
        "items": [
            {
                "component_id": item.component_id,
                "name": item.name,
                "category": item.category,
                "quantity": getattr(item, "quantity", None) or 1,
                "best_price": item.best_price,
                "store": item.store,
                "url": item.url,
            }
            for item in budget.items
        ],
        "total_price": budget.total_price,
        "performance": budget.performance,
    }


def validate_component_ids(component_ids: list[str]) -> None:
    if not component_ids:
        raise HTTPException(status_code=400, detail="O orçamento precisa ter pelo menos uma peça.")

    if any(not component_id for component_id in component_ids):
        raise HTTPException(status_code=400, detail="A lista de peças não pode conter valores vazios.")

    if len(component_ids) != len(set(component_ids)):
        raise HTTPException(status_code=400, detail="A lista de peças não pode conter IDs repetidos.")

    if len(component_ids) != len(STEP_CATEGORIES):
        raise HTTPException(status_code=400, detail="O orçamento deve conter exatamente oito peças.")


def validate_quantities(component_ids: list[str], quantities: dict[str, int]) -> None:
    unknown = sorted(set(quantities) - set(component_ids))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Quantidades informadas para peças não selecionadas: {', '.join(unknown)}.",
        )


def validate_budget_components(component_ids: list[str], components: list[dict]) -> None:
    validate_component_ids(component_ids)

    try:
        effective = [
            "ram" if component["category"] == "kit-ram" else component["category"]
            for component in components
        ]
    except KeyError as exc:
        raise HTTPException(status_code=503, detail="Resposta inválida do catálogo") from exc

    missing = [category for category in STEP_CATEGORIES if category not in set(effective)]
    if missing:
        labels = [REQUIRED_CATEGORY_LABELS[category] for category in missing]
        raise HTTPException(
            status_code=400,
            detail=(
                "O orçamento precisa conter CPU, cooler, placa-mãe, RAM, armazenamento, "
                f"GPU, fonte e gabinete. Faltando: {', '.join(labels)}."
            ),
        )

    if len(effective) != len(set(effective)) or set(effective) != set(STEP_CATEGORIES):
        raise HTTPException(
            status_code=400,
            detail="O orçamento deve conter apenas uma peça de cada categoria.",
        )


def create_or_update_budget(
    db: Session,
    user_id: int,
    name: str,
    component_ids: list[str],
    budget: models.Budget | None = None,
    quantities: dict | None = None,
) -> models.Budget:
    quantities = quantities or {}
    ensure_user_exists(db, user_id)
    validate_component_ids(component_ids)
    validate_quantities(component_ids, quantities)
    components = fetch_components(component_ids)
    validate_budget_components(component_ids, components)
    compatibility = check_components(components, quantities)
    if not compatibility["compatible"]:
        raise HTTPException(status_code=400, detail=compatibility)

    quotes = [
        quote_component(component, quantities.get(component["id"], 1))
        for component in components
    ]
    total_price = sum((item["best_price"] for item in quotes), Decimal("0.00")).quantize(MONEY_QUANTUM)
    performance = estimate_performance(components)

    if budget is None:
        budget = models.Budget(user_id=user_id, name=name)
        db.add(budget)
        db.flush()
    else:
        budget.name = name
        budget.items.clear()

    budget.total_price = total_price
    budget.performance = performance

    for quote in quotes:
        budget.items.append(
            models.BudgetItem(
                component_id=quote["component_id"],
                name=quote["name"],
                category=quote["category"],
                quantity=quote["quantity"],
                best_price=quote["best_price"],
                store=quote["store"],
                url=quote["url"],
            )
        )

    try:
        db.commit()
        db.refresh(budget)
    except Exception:
        db.rollback()
        raise
    return budget


def get_budget(db: Session, budget_id: int, user_id: int | None = None):
    query = db.query(models.Budget).filter(models.Budget.id == budget_id)
    if user_id is not None:
        query = query.filter(models.Budget.user_id == user_id)
    return query.first()


def get_user_budgets(db: Session, user_id: int):
    return db.query(models.Budget).filter(models.Budget.user_id == user_id).all()


def delete_budget(db: Session, budget_id: int):
    budget = get_budget(db, budget_id)
    if not budget:
        return None
    db.delete(budget)
    db.commit()
    return budget
