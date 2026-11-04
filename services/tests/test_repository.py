import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128
from pymongo.errors import DuplicateKeyError

from services.telegram_collector.collector import process_message
from services.telegram_collector.deduplication import equivalent_offer_key, message_identity


def test_idempotent_save_preserves_existing_status(repository, settings, message, channel):
    assert asyncio.run(process_message(message, channel, settings, repository))
    repository.promotions.update_one({}, {"$set": {"status": "published"}})
    assert not asyncio.run(process_message(message, channel, settings, repository))
    assert repository.promotions.count_documents({}) == 1
    saved = repository.promotions.find_one()
    assert saved["status"] == "published"
    assert saved["offer"]["price"] == Decimal128("3599.90")
    assert saved["raw_text"] == message.message
    # BSON Date armazena milissegundos, enquanto datetime aceita microssegundos.
    assert saved["telegram"]["sent_at"] == message.date.replace(microsecond=(message.date.microsecond // 1000) * 1000)


def test_unique_index_and_different_chat_identity(repository):
    document = {"telegram": {"chat_id": -100123, "message_id": 9}}
    assert repository.save(document)
    assert not repository.save(document)
    assert repository.save({"telegram": {"chat_id": -100456, "message_id": 9}})
    with pytest.raises(DuplicateKeyError):
        repository.promotions.insert_one(document)


def test_concurrent_repeated_imports(repository):
    document = {"telegram": {"chat_id": -100123, "message_id": 9}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repository.save(document), range(20)))
    assert sum(results) == 1
    assert repository.promotions.count_documents({}) == 1


def test_duplicate_key_race_is_handled(repository, monkeypatch):
    repository.save({"telegram": {"chat_id": -100123, "message_id": 9}})

    def conflict(*args, **kwargs):
        raise DuplicateKeyError("simulated race")

    monkeypatch.setattr(repository.promotions, "update_one", conflict)
    assert not repository.save({"telegram": {"chat_id": -100123, "message_id": 9}})
    with pytest.raises(DuplicateKeyError):
        repository.save({"telegram": {"chat_id": -100123, "message_id": 10}})


@pytest.mark.parametrize("chat_id,message_id", [(1, 9), (0, 9), (-100123, 0)])
def test_invalid_identity_rejected(chat_id, message_id):
    with pytest.raises(ValueError):
        message_identity(chat_id, message_id)


def test_equivalent_offer_key_is_only_available_for_complete_identity():
    key = equivalent_offer_key("RTX 5070", Decimal("3599.90"), "KaBuM", "GPU10")
    assert key == equivalent_offer_key("rtx 5070", 3599.9, "kabum", "gpu10")
    assert key != equivalent_offer_key("rtx 5070", 3600, "kabum", "gpu10")
    assert equivalent_offer_key(None, 3599, "kabum") is None
    assert equivalent_offer_key("gpu", None, "kabum") is None
    assert equivalent_offer_key("gpu", "NaN", "kabum") is None


def test_collector_status_requires_recent_connected_signal(repository, monkeypatch):
    monkeypatch.setattr(repository.database, "command", lambda *a: {"ok": 1})
    assert not repository.summary()["collector_online"]
    repository.heartbeat(2)
    assert repository.summary() == {"promotions": 0, "collector_online": True, "collector_sources": 2}
    repository.service_status.update_one({}, {"$set": {"updated_at": datetime.now(timezone.utc) - timedelta(minutes=3)}})
    assert not repository.summary()["collector_online"]
    repository.heartbeat(2, connected=False)
    assert not repository.summary()["collector_online"]
