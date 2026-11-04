from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import compatibility
import schemas
import services
from auth import AuthenticatedUser, get_current_user, require_payload_owner
from database import get_db
from settings import get_settings
from request_context import request_context_middleware
from ai_routes import router as ai_router


settings = get_settings()
app = FastAPI(
    title="PC2YOU API de Orçamentos",
    version="2.0.0",
    openapi_tags=[
        {"name": "health", "description": "Sinais de vida e prontidão do serviço."},
        {"name": "budgets", "description": "Orçamentos pertencentes ao usuário autenticado."},
        {"name": "build", "description": "Montagem e compatibilidade de componentes."},
        {"name": "performance", "description": "Estimativa de desempenho do orçamento."},
    ],
)
app.middleware("http")(request_context_middleware)

app.include_router(ai_router)

import demo_mode  # noqa: E402

demo_mode.install(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live", tags=["health"])
def health_live():
    return {"status": "ok", "service": "api-orcamentos"}


def _readiness(db: Session) -> dict:
    if not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="Serviço ainda não está pronto")
    try:
        db.execute(text("SELECT 1"))
        services.catalog_health()
    except (SQLAlchemyError, HTTPException) as exc:
        raise HTTPException(status_code=503, detail="Serviço ainda não está pronto") from exc
    return {"status": "ok", "service": "api-orcamentos", "dependencies": ["database", "catalog"]}


@app.get("/health/ready", tags=["health"])
def health_ready(db: Session = Depends(get_db)):
    return _readiness(db)


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    return _readiness(db)


@app.post("/budgets", response_model=schemas.BudgetResponse, status_code=201, tags=["budgets"])
def create_budget(
    payload: schemas.BudgetCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    require_payload_owner(payload.user_id, current_user)
    budget = services.create_or_update_budget(
        db,
        user_id=payload.user_id,
        name=payload.name,
        component_ids=payload.components,
        quantities=payload.quantities,
    )
    return services.budget_to_response(budget)


@app.get("/budgets/{budget_id}", response_model=schemas.BudgetResponse, tags=["budgets"])
def read_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    services.ensure_user_exists(db, current_user.user_id)
    budget = services.get_budget(db, budget_id, current_user.user_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    return services.budget_to_response(budget)


@app.get("/budgets/user/{user_id}", response_model=list[schemas.BudgetResponse], tags=["budgets"])
def read_user_budgets(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    require_payload_owner(user_id, current_user)
    services.ensure_user_exists(db, current_user.user_id)
    return [services.budget_to_response(item) for item in services.get_user_budgets(db, user_id)]


@app.put("/budgets/{budget_id}", response_model=schemas.BudgetResponse, tags=["budgets"])
def update_budget(
    budget_id: int,
    payload: schemas.BudgetUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    services.ensure_user_exists(db, current_user.user_id)
    budget = services.get_budget(db, budget_id, current_user.user_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")

    component_ids = (
        payload.components
        if payload.components is not None
        else [item.component_id for item in budget.items]
    )
    name = payload.name if payload.name is not None else budget.name
    quantities = (
        payload.quantities
        if payload.quantities is not None
        else {
            item.component_id: item.quantity
            for item in budget.items
            if item.component_id in component_ids
        }
    )
    updated = services.create_or_update_budget(
        db,
        user_id=budget.user_id,
        name=name,
        component_ids=component_ids,
        budget=budget,
        quantities=quantities,
    )
    return services.budget_to_response(updated)


@app.delete("/budgets/{budget_id}", response_model=schemas.BudgetResponse, tags=["budgets"])
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    services.ensure_user_exists(db, current_user.user_id)
    budget = services.get_budget(db, budget_id, current_user.user_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    response = services.budget_to_response(budget)
    db.delete(budget)
    db.commit()
    return response


@app.post("/compatibility/check", tags=["build"])
def check(payload: schemas.CompatibilityCheck):
    component_ids = [
        value
        for value in payload.model_dump().values()
        if value
    ]
    components = services.fetch_components(component_ids)
    return compatibility.check_components(components)


@app.post("/build/next-options", tags=["build"])
def next_options(payload: schemas.NextOptionsRequest):
    selected_ids = list(payload.selected_components.values())
    selected_components = services.fetch_components(selected_ids) if selected_ids else []
    next_category = compatibility.next_category(payload.selected_components)

    if not next_category:
        return {
            "done": True,
            "next_category": None,
            "options": [],
            "compatibility": compatibility.check_components(selected_components),
        }

    if next_category == "ram":
        candidates = (
            services.list_catalog_components("ram")
            + services.list_catalog_components("kit-ram")
        )
    else:
        candidates = services.list_catalog_components(next_category)
    options = []
    for candidate in candidates:
        result = compatibility.check_components([*selected_components, candidate])
        if result["compatible"]:
            options.append({
                **candidate,
                "best_price": services.get_best_price(candidate),
            })

    return {
        "done": False,
        "next_category": next_category,
        "options": options,
        "compatibility": compatibility.check_components(selected_components),
    }


@app.post("/build/finalize", response_model=schemas.BudgetResponse, status_code=201, tags=["build"])
def finalize(
    payload: schemas.BuildFinalize,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    require_payload_owner(payload.user_id, current_user)
    budget = services.create_or_update_budget(
        db,
        user_id=payload.user_id,
        name=payload.name,
        component_ids=payload.components,
        quantities=payload.quantities,
    )
    return services.budget_to_response(budget)


@app.get("/performance/{budget_id}", tags=["performance"])
def performance(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    services.ensure_user_exists(db, current_user.user_id)
    budget = services.get_budget(db, budget_id, current_user.user_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    return {"budget_id": budget_id, "performance": budget.performance}
