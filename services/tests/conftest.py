import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import mongomock
import pytest
from telethon.tl.types import Channel, ChatPhotoEmpty

from services.telegram_collector.config import Settings
from services.telegram_collector.repository import PromotionRepository
from services.telegram_bot.alerts import AlertRepository


@pytest.fixture(autouse=True)
def no_network_link_resolution(monkeypatch):
    monkeypatch.setattr("services.telegram_collector.collector.LINK_RESOLUTION_ENABLED", False)


@pytest.fixture
def messages():
    return json.loads((Path(__file__).parent / "fixtures/messages.json").read_text(encoding="utf-8"))


@pytest.fixture
def channel():
    return Channel(id=1234567890, title="Promo Hardware", photo=ChatPhotoEmpty(), date=datetime.now(timezone.utc), broadcast=True, username="pc2you_test")


@pytest.fixture
def settings():
    return Settings(api_id=123, api_hash="fake-api-hash", allowed_chats=frozenset({-1001234567890}))


@pytest.fixture
def repository():
    repo = PromotionRepository(mongomock.MongoClient(tz_aware=True)["test_pc2you"])
    repo.ensure_indexes()
    return repo


@pytest.fixture
def alerts_repository(repository):
    repo = AlertRepository(repository.database)
    repo.ensure_indexes()
    return repo


@pytest.fixture
def message(messages):
    return SimpleNamespace(id=10, message=messages["gpu"], date=datetime.now(timezone.utc), out=False, action=None, entities=[])
