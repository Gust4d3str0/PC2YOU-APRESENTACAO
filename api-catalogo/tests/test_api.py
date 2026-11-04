from datetime import datetime, timedelta, timezone
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import jwt
import mongomock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import main
import ml_service
import services
from config import Settings, get_settings
from database import ensure_indexes, get_components_collection


TEST_SETTINGS = Settings(
    mongo_uri="mongodb://unused",
    mongo_db="test",
    jwt_secret="test-secret-with-enough-entropy",
    jwt_algorithm="HS256",
    admin_api_key="admin-test-key",
    cors_origins=("http://localhost:5173",),
    max_page_size=2,
    max_batch_size=2,
    max_search_length=10,
    proxy_max_bytes=8,
    proxy_connect_timeout=1,
    proxy_read_timeout=1,
    ml_connect_timeout=1,
    ml_read_timeout=1,
    refresh_cooldown_seconds=60,
)


def component(component_id: str, name: str, category: str = "cpu") -> dict:
    return {
        "id": component_id,
        "name": name,
        "category": category,
        "brand": "Marca",
        "image": "https://example.com/image.jpg",
        "description": f"Descrição {name}",
        "technical_specs": {},
        "compatibility": {},
        "prices": [
            {
                "store": "Seed",
                "price": 10.0,
                "url": "https://example.com/product",
                "last_update": "2026-01-01",
            }
        ],
        "benchmark": {"gaming_score": 1, "workstation_score": 1, "ai_score": 1},
        "price_history": [],
    }


@pytest.fixture
def collection():
    value = mongomock.MongoClient().db.components
    ensure_indexes(value)
    value.insert_many([component("one", "Literal.dot"), component("two", "Sem pontuação")])
    return value


@pytest.fixture
def client(collection):
    main.refresh_cache.clear()
    main.app.dependency_overrides[get_components_collection] = lambda: collection
    main.app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def bearer_token(expired: bool = False) -> str:
    delta = timedelta(minutes=-1 if expired else 5)
    return jwt.encode(
        {"sub": "user-1", "exp": datetime.now(timezone.utc) + delta},
        TEST_SETTINGS.jwt_secret,
        algorithm=TEST_SETTINGS.jwt_algorithm,
    )


def test_health_compatibility_and_live(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/live").status_code == 200


def test_request_id_is_propagated_and_log_is_safe(client, caplog):
    token = "sensitive-bearer-token"
    with caplog.at_level(logging.INFO, logger="api-catalogo"):
        response = client.get(
            "/health",
            headers={"X-Correlation-ID": "correlation-123", "Authorization": f"Bearer {token}"},
        )
    assert response.headers["X-Request-ID"] == "correlation-123"
    payload = json.loads(caplog.records[-1].message)
    assert payload == {
        "service": "api-catalogo",
        "method": "GET",
        "path": "/health",
        "status": 200,
        "duration_ms": payload["duration_ms"],
        "request_id": "correlation-123",
    }
    assert token not in caplog.text
    assert "Authorization" not in caplog.text


def test_search_escapes_regex_and_paginates(client):
    response = client.get("/components", params={"q": ".", "limit": 1})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["one"]
    assert client.get("/components", params={"limit": 3}).status_code == 422
    assert client.get("/components", params={"q": "x" * 11}).status_code == 422


def test_batch_deduplicates_preserves_order_and_limits(client):
    response = client.post("/components/batch", json={"component_ids": ["two", "one", "two"]})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["two", "one"]
    response = client.post("/components/batch", json={"component_ids": ["one", "two", "three"]})
    assert response.status_code == 422


def test_admin_required_and_duplicate_returns_409(client):
    payload = component("three", "Terceiro")
    assert client.post("/components", json=payload).status_code == 403
    headers = {"X-Admin-Key": TEST_SETTINGS.admin_api_key}
    assert client.post("/components", json=payload, headers=headers).status_code == 201
    assert client.post("/components", json=payload, headers=headers).status_code == 409


def test_refresh_requires_valid_jwt(client):
    route = "/components/one/refresh-real-prices"
    assert client.post(route).status_code == 401
    assert client.post(route, headers={"Authorization": f"Bearer {bearer_token(True)}"}).status_code == 401
    with patch.object(ml_service, "refresh_component_real_prices", return_value={"updated_external": False}):
        response = client.post(route, headers={"Authorization": f"Bearer {bearer_token()}"})
    assert response.status_code == 200


def test_refresh_cooldown_returns_cached_compatible_result(client):
    route = "/components/one/refresh-real-prices"
    headers = {"Authorization": f"Bearer {bearer_token()}"}
    expected = {"updated_external": False, "summary": {"best_offer": None}}
    with patch.object(ml_service, "refresh_component_real_prices", return_value=expected) as refresh:
        first = client.post(route, headers=headers)
        second = client.post(route, headers=headers)
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["updated_external"] is False
    assert refresh.call_count == 1


def test_refresh_cache_coalesces_concurrent_calls():
    cache = main.RefreshCooldownCache()
    counter = 0
    counter_lock = threading.Lock()

    def refresh():
        nonlocal counter
        with counter_lock:
            counter += 1
        time.sleep(0.05)
        return {"updated_external": True}

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: cache.get_or_refresh("one", 60, refresh), range(4)))
    assert counter == 1
    assert sum(result["cached"] is False for result in results) == 1


def test_unique_index_and_duplicate_error(collection):
    with pytest.raises(DuplicateKeyError):
        collection.insert_one(component("one", "Duplicado"))
    names = {index["name"] for index in collection.list_indexes()}
    assert {"uq_components_id", "ix_components_category", "ix_components_brand", "ix_components_name"} <= names


def test_proxy_rejects_fake_suffix_and_private_address():
    with pytest.raises(main.HTTPException):
        main._validate_proxy_url("https://evilmlstatic.com/a.jpg")
    with patch.object(main.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
        with pytest.raises(main.HTTPException) as exc:
            main._validate_proxy_url("https://http2.mlstatic.com/a.jpg")
    assert exc.value.status_code == 400


class FakeResponse:
    is_redirect = False
    is_permanent_redirect = False
    headers = {"content-type": "image/jpeg", "content-length": "9"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"123456789"


def test_proxy_enforces_content_length():
    with patch.object(main, "_validate_proxy_url"), patch.object(main.proxy_session, "get", return_value=FakeResponse()):
        with pytest.raises(main.HTTPException) as exc:
            main._download_image("https://http2.mlstatic.com/a.jpg", TEST_SETTINGS)
    assert exc.value.status_code == 413


def test_ml_failure_keeps_seed_prices(collection):
    original = services.get_component(collection, "one")
    with patch.object(ml_service, "fetch_mercado_livre_offers_with_stats", side_effect=ml_service.MercadoLivreError("timeout")):
        result = ml_service.refresh_component_real_prices(original, collection)
    persisted = services.get_component(collection, "one")
    assert result["updated_external"] is False
    assert persisted["prices"] == original["prices"]
