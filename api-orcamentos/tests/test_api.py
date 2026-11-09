from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
import services
from database import get_db
from settings import Settings, get_settings


TEST_SETTINGS = Settings(
    database_url="sqlite://",
    catalog_api_url="http://catalog.test",
    catalog_connect_timeout=0.1,
    catalog_read_timeout=0.1,
    catalog_retries=0,
    jwt_secret="test-only-secret",
    jwt_algorithm="HS256",
    jwt_audience=None,
    cors_origins=("http://testserver",),
)


def component(component_id: str, category: str) -> dict:
    technical_specs = {}
    compatibility = {}
    if category == "cpu":
        technical_specs = {"tdp_watts": 65}
        compatibility = {"socket": "AM5"}
    elif category == "cooler":
        compatibility = {"socket_support": ["AM5"], "max_tdp_watts": 150}
    elif category == "motherboard":
        technical_specs = {"memory_slots": 4, "max_memory_gb": 128}
        compatibility = {"socket": "AM5", "memory_type": "DDR5", "form_factor": "ATX"}
    elif category in {"ram", "kit-ram"}:
        technical_specs = {"capacity": "16GB", "memory_type": "DDR5", "modules": 1}
        if category == "kit-ram":
            technical_specs["modules"] = "2x8GB"
        compatibility = {"memory_type": "DDR5"}
    elif category == "gpu":
        technical_specs = {"length_mm": 250}
        compatibility = {"min_psu_watts": 500}
    elif category == "psu":
        technical_specs = {"wattage": 650}
    elif category == "case":
        compatibility = {"supported_form_factors": ["ATX"], "max_gpu_length_mm": 350}

    return {
        "id": component_id,
        "name": component_id,
        "category": category,
        "technical_specs": technical_specs,
        "compatibility": compatibility,
        "benchmark": {"gaming_score": 70, "workstation_score": 70, "ai_score": 70},
        "prices": [{"store": "Loja", "price": "10.005", "url": "https://shop.test/item"}],
    }


@pytest.fixture
def components():
    categories = ["cpu", "cooler", "motherboard", "ram", "storage", "gpu", "psu", "case"]
    return [component(category, category) for category in categories]


@pytest.fixture
def client(monkeypatch, components):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    models.Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO users (id) VALUES (1)"))

    def override_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    by_id = {item["id"]: item for item in components}
    monkeypatch.setattr(services, "fetch_components", lambda ids: [by_id[item_id] for item_id in ids])
    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    test_client = TestClient(main.app)
    yield test_client
    main.app.dependency_overrides.clear()
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def token(user_id: int) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        TEST_SETTINGS.jwt_secret,
        algorithm=TEST_SETTINGS.jwt_algorithm,
    )


def headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(user_id)}"}


def payload(user_id: int = 1, quantities=None) -> dict:
    return {
        "user_id": user_id,
        "name": "Build teste",
        "components": ["cpu", "cooler", "motherboard", "ram", "storage", "gpu", "psu", "case"],
        "quantities": quantities or {},
    }


def test_budget_requires_bearer_and_payload_owner(client):
    assert client.post("/budgets", json=payload()).status_code == 401
    assert client.post("/budgets", json=payload(user_id=2), headers=headers(1)).status_code == 403


def test_authenticated_nonexistent_user_is_rejected(client):
    response = client.post("/budgets", json=payload(user_id=2), headers=headers(2))
    assert response.status_code == 404


def test_owner_can_create_but_other_user_cannot_read(client):
    created = client.post("/budgets", json=payload(), headers=headers(1))
    assert created.status_code == 201
    budget_id = created.json()["budget_id"]
    assert client.get(f"/budgets/{budget_id}", headers=headers(1)).status_code == 200
    assert client.get(f"/budgets/{budget_id}", headers=headers(2)).status_code == 404
    assert client.get(f"/performance/{budget_id}", headers=headers(2)).status_code == 404


def test_put_preserves_and_repasses_quantities(client):
    created = client.post("/budgets", json=payload(quantities={"ram": 2}), headers=headers(1))
    budget_id = created.json()["budget_id"]

    renamed = client.put(f"/budgets/{budget_id}", json={"name": "Renomeada"}, headers=headers(1))
    assert renamed.status_code == 200
    ram = next(item for item in renamed.json()["items"] if item["component_id"] == "ram")
    assert ram["quantity"] == 2

    changed = client.put(
        f"/budgets/{budget_id}",
        json={"quantities": {"ram": 3}},
        headers=headers(1),
    )
    ram = next(item for item in changed.json()["items"] if item["component_id"] == "ram")
    assert ram["quantity"] == 3


@pytest.mark.parametrize("quantity", [0, -1, 17])
def test_quantity_bounds_are_validated(client, quantity):
    response = client.post(
        "/budgets",
        json=payload(quantities={"ram": quantity}),
        headers=headers(1),
    )
    assert response.status_code == 422


def test_unknown_quantity_key_is_rejected(client):
    response = client.post(
        "/budgets",
        json=payload(quantities={"not-selected": 2}),
        headers=headers(1),
    )
    assert response.status_code == 400


def test_duplicate_ids_and_extra_categories_are_rejected(components):
    with pytest.raises(Exception) as duplicate:
        services.validate_component_ids(["cpu"] * 8)
    assert duplicate.value.status_code == 400

    altered = [*components[:-1], component("audio", "audio")]
    with pytest.raises(Exception) as category_error:
        services.validate_budget_components([item["id"] for item in altered], altered)
    assert category_error.value.status_code == 400


def test_decimal_rounding_is_deterministic():
    quote = services.quote_component(component("cpu", "cpu"), quantity=3)
    assert str(quote["best_price"]) == "30.03"


def test_budget_prefers_the_unconditional_price_and_uses_a_conditional_one_only_when_alone():
    from services import get_best_price
    general = {"store": "A", "price": 1900, "url": "https://a.test/p"}
    coupon = {"store": "B", "price": 1700, "url": "https://b.test/p", "coupon": "CUPOM", "conditional": True}
    assert get_best_price({"prices": [coupon, general]})["store"] == "A"
    assert get_best_price({"prices": [coupon]})["store"] == "B"
    with pytest.raises(Exception):
        get_best_price({"prices": []})
