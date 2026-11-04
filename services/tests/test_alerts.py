from datetime import datetime, timezone
from decimal import Decimal

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128

from services.telegram_bot.alerts import AlertRepository, parse_max_price
from services.telegram_collector import config
from services.telegram_collector.config import ConfigurationError
from services.telegram_collector.matcher import detect_component_type, normalize_terms


@pytest.mark.parametrize("raw", ["3800", "3.800", "3800,00", "R$ 3.800,00", "r$3800,0"])
def test_max_price_formats(raw):
    assert parse_max_price(raw) == Decimal("3800.00")


@pytest.mark.parametrize("raw", ["-1", "0", "NaN", "Infinity", "3.80", "38,000", "1.00,00", "", "1e5", "1000000000"])
def test_invalid_max_price(raw):
    with pytest.raises(ValueError):
        parse_max_price(raw)


@pytest.mark.parametrize("raw", ["sem limite", "qualquer", "-"])
def test_optional_price_limit(raw):
    assert parse_max_price(raw) is None


@pytest.mark.parametrize("query,kind", [("RTX 5070", "gpu"), ("RX 9070 XT", "gpu"), ("Ryzen 7 7800X3D", "cpu"), ("Core i7 14700K", "cpu"), ("B650", "motherboard"), ("DDR5 6000", "ram"), ("NVMe 2TB", "storage"), ("750W", "psu"), ("peça especial", None)])
def test_automatic_component_types(query, kind):
    assert detect_component_type(query) == kind


def test_alert_creation_indexes_and_money(alerts_repository):
    alert = alerts_repository.create(123, {"query": "RTX 5070", "component_type": "gpu", "max_price": Decimal("3800")})
    assert alert["max_price"] == Decimal128("3800.00")
    assert alert["normalized_terms"] == ["rtx", "5070"]
    assert alert["enabled"] and alert["ignored_brands"] == []
    assert alert["created_at"].tzinfo is not None
    assert "ix_alert_user_created" in alerts_repository.alerts.index_information()
    assert alerts_repository.history.index_information()["uq_notification_user_alert_promotion"]["unique"]


def test_alert_ownership_update_pause_and_remove(alerts_repository):
    alert = alerts_repository.create(123, {"query": "RTX 5070", "max_price": Decimal("3800")})
    assert alerts_repository.get_owned(456, alert["_id"]) is None
    assert not alerts_repository.set_enabled(456, alert["_id"], False)
    assert not alerts_repository.remove(456, alert["_id"])
    assert not alerts_repository.update(456, alert["_id"], {"query": "outra", "max_price": None})
    assert alerts_repository.set_enabled(123, alert["_id"], False)
    paused = alerts_repository.get_owned(123, alert["_id"])
    assert paused["query"] == alert["query"] and not paused["enabled"]
    assert alerts_repository.update(123, alert["_id"], {"query": "RX 9070 XT", "max_price": Decimal("4000"), "enabled": False})
    assert alerts_repository.get_owned(123, alert["_id"])["normalized_terms"] == ["rx", "9070", "xt"]
    assert alerts_repository.remove(123, alert["_id"])
    assert alerts_repository.get_owned(123, "not-an-object-id") is None


@pytest.mark.parametrize("values", [{"query": ""}, {"query": "x" * 121}, {"query": "RTX", "max_price": Decimal("NaN")}, {"query": "RTX", "minimum_discount": 101}, {"query": "RTX", "brands": ["x" * 41]}, {"query": "RTX", "component_type": "inventado"}])
def test_invalid_alert_fields(alerts_repository, values):
    with pytest.raises(ValueError):
        alerts_repository.create(123, values)
    assert alerts_repository.alerts.count_documents({}) == 0


def test_allowed_user_config_is_validated_without_loading_secrets(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123, 456,123")
    assert config.load_settings().allowed_users == frozenset({123, 456})
    for raw in ("abc", "-123", "0"):
        monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", raw)
        with pytest.raises(ConfigurationError):
            config.load_settings()


def test_confirmation_retry_is_idempotent_and_cannot_reuse_another_users_id(alerts_repository):
    from pymongo.errors import DuplicateKeyError

    creation_id = ObjectId()
    first = alerts_repository.create(123, {"query": "RTX 5070", "max_price": 3800}, creation_id=creation_id)
    again = alerts_repository.create(123, {"query": "RTX 5070", "max_price": 3900}, creation_id=creation_id)
    assert again["_id"] == first["_id"]
    assert str(again["max_price"]) == "3900.00"
    assert alerts_repository.alerts.count_documents({}) == 1
    with pytest.raises(DuplicateKeyError):
        alerts_repository.create(456, {"query": "outro modelo", "max_price": None}, creation_id=creation_id)
    assert alerts_repository.get_owned(123, creation_id)["query"] == "RTX 5070"
