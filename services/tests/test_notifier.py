import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import ServerSelectionTimeoutError
from telegram.error import Forbidden, NetworkError, RetryAfter

from services.telegram_bot.notifier import NotificationWorker, notification_text
from services.telegram_collector.repository import bson_values
from services.telegram_collector.parser import parse_message


@pytest.fixture
def delivery(alerts_repository, settings):
    now = [datetime.now(timezone.utc).replace(microsecond=0)]
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=777)))
    worker = NotificationWorker(alerts_repository, bot, settings, clock=lambda: now[0])
    worker.bootstrap()

    def add_alert(user_id=123, **updates):
        values = {"query": "RTX 5070", "max_price": 3800, "component_type": "gpu", **updates}
        record = alerts_repository.create(user_id, values)
        alerts_repository.alerts.update_one({"_id": record["_id"]}, {"$set": {"created_at": now[0] - timedelta(seconds=1)}})
        return alerts_repository.get_owned(user_id, record["_id"])

    def add_promotion(text="GALAX RTX 5070\nPor R$ 3.599,90\nKaBuM\nCupom GPU10\nhttps://www.kabum.com.br/produto/1", **updates):
        now[0] += timedelta(seconds=1)
        document = bson_values({"telegram": {"chat_id": -1001234567890, "message_id": alerts_repository.promotions.count_documents({}) + 1}, "raw_text": text, **parse_message(text), "created_at": now[0], "status": "parsed", **updates})
        document["_id"] = alerts_repository.promotions.insert_one(document).inserted_id
        return document

    return SimpleNamespace(repo=alerts_repository, worker=worker, bot=bot, now=now, add_alert=add_alert, add_promotion=add_promotion, settings=settings)


def test_delivery_is_persistent_and_reprocessing_is_idempotent(delivery):
    delivery.add_alert()
    promotion = delivery.add_promotion("GALAX RTX 5070\nDe R$ 4.099,90\nPor R$ 3.599,90\nKaBuM\nCupom GPU10\nhttps://www.kabum.com.br/produto/1")
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 1
    row = delivery.repo.history.find_one()
    assert row["status"] == "sent" and row["telegram_message_id"] == 777
    text = delivery.bot.send_message.call_args.kwargs["text"]
    assert "R$ 3.599,90" in text and "GPU10" in text and "R$ 200,10" in text
    assert "De R$ 4.099,90" in text and "Por R$ 3.599,90" in text and "12,20%" in text
    markup = delivery.bot.send_message.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url.startswith("https://www.kabum")
    delivery.repo.promotions.update_one({"_id": promotion["_id"]}, {"$unset": {"notifications_processed_at": ""}})
    restarted = NotificationWorker(delivery.repo, delivery.bot, delivery.settings, clock=lambda: delivery.now[0])
    asyncio.run(restarted.run_once())
    assert delivery.bot.send_message.await_count == 1
    assert delivery.repo.history.count_documents({}) == 1


@pytest.mark.parametrize("url", ["https://amzn.to/offer", None, "javascript:alert(1)"])
def test_purchase_button_uses_only_offer_url_without_message_link_fallback(delivery, url):
    delivery.add_alert()
    parsed = parse_message("RTX 5070 por R$ 3500")
    parsed["offer"]["url"] = url
    delivery.add_promotion(**parsed, telegram={"chat_id": -100123, "message_id": 42,
                                             "message_url": "https://t.me/canal/42"})
    asyncio.run(delivery.worker.run_once())
    delivery.bot.send_message.assert_awaited_once()
    markup = delivery.bot.send_message.call_args.kwargs["reply_markup"]
    purchase = [b for row in markup.inline_keyboard for b in row if b.text == "🛒 Abrir oferta"]
    if url and url.startswith("https://"):
        assert len(purchase) == 1 and purchase[0].url == url
    else:
        assert purchase == []
    assert len(markup.inline_keyboard[-1]) == 2  # Ignore and pause actions remain available.


def test_equivalent_offer_dedup_and_expiration(delivery):
    delivery.add_alert()
    delivery.add_promotion()
    asyncio.run(delivery.worker.run_once())
    delivery.add_promotion("🔥 GALAX GeForce RTX-5070\nOFERTA! Por R$ 3.599,90\nKaBuM\nCupom GPU10")
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 1
    assert delivery.repo.history.count_documents({"status": "skipped_equivalent"}) == 1
    delivery.now[0] += timedelta(hours=6, seconds=1)
    delivery.add_promotion()
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 2


def test_multiple_alerts_and_users_are_isolated(delivery):
    delivery.add_alert(123)
    delivery.add_alert(123, max_price=4000)
    delivery.add_alert(456)
    delivery.add_promotion()
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 3
    assert {call.kwargs["chat_id"] for call in delivery.bot.send_message.call_args_list} == {123, 456}


def test_worker_obeys_user_whitelist_and_paused_alerts(delivery):
    delivery.add_alert(123, enabled=False)
    delivery.add_alert(456)
    delivery.worker.settings = replace(delivery.settings, allowed_users=frozenset({123}))
    delivery.add_promotion()
    asyncio.run(delivery.worker.run_once())
    delivery.bot.send_message.assert_not_awaited()


def test_initial_start_skips_old_promotions_and_restart_finds_offline_arrivals(delivery):
    delivery.add_alert()
    old = delivery.add_promotion()
    delivery.repo.promotions.update_one({"_id": old["_id"]}, {"$set": {"created_at": delivery.now[0] - timedelta(days=1)}})
    asyncio.run(delivery.worker.run_once())
    delivery.bot.send_message.assert_not_awaited()
    delivery.add_promotion()
    restarted = NotificationWorker(delivery.repo, delivery.bot, delivery.settings, clock=lambda: delivery.now[0])
    asyncio.run(restarted.run_once())
    delivery.bot.send_message.assert_awaited_once()


def test_new_alert_does_not_push_already_existing_promotions(delivery):
    promotion = delivery.add_promotion()
    alert = delivery.add_alert()
    delivery.repo.alerts.update_one({"_id": alert["_id"]}, {"$set": {"created_at": promotion["created_at"] + timedelta(seconds=1)}})
    asyncio.run(delivery.worker.run_once())
    delivery.bot.send_message.assert_not_awaited()


def test_rate_limit_is_retried_after_backoff(delivery):
    delivery.add_alert()
    delivery.add_promotion()
    delivery.bot.send_message.side_effect = [RetryAfter(60), SimpleNamespace(message_id=778)]
    asyncio.run(delivery.worker.run_once())
    assert delivery.repo.history.find_one()["status"] == "failed"
    delivery.now[0] += timedelta(seconds=20)
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 1
    delivery.now[0] += timedelta(seconds=41)
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 2
    assert delivery.repo.history.find_one()["status"] == "sent"


@pytest.mark.parametrize("error,status", [(Forbidden("SECRET_TOKEN"), "rejected"), (NetworkError("SECRET_TOKEN"), "uncertain")])
def test_failed_delivery_never_logs_credentials_or_retries_ambiguous_send(delivery, error, status, caplog):
    delivery.add_alert()
    delivery.add_promotion()
    delivery.bot.send_message.side_effect = error
    asyncio.run(delivery.worker.run_once())
    assert delivery.repo.history.find_one()["status"] == status
    assert "SECRET_TOKEN" not in caplog.text
    delivery.now[0] += timedelta(minutes=3)
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 1


def test_crash_after_send_before_mongo_ack_does_not_resend(delivery, monkeypatch):
    delivery.add_alert()
    delivery.add_promotion()
    real_finish = delivery.worker.finish
    monkeypatch.setattr(delivery.worker, "finish", lambda *a, **kw: (_ for _ in ()).throw(ServerSelectionTimeoutError("SECRET_URI")))
    with pytest.raises(ServerSelectionTimeoutError):
        asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 1
    monkeypatch.setattr(delivery.worker, "finish", real_finish)
    delivery.now[0] += timedelta(minutes=3)
    asyncio.run(delivery.worker.run_once())
    assert delivery.repo.history.find_one()["status"] == "uncertain"
    assert delivery.bot.send_message.await_count == 1


def test_competing_workers_cannot_claim_same_notification(delivery):
    alert = delivery.add_alert()
    promotion = delivery.add_promotion()
    first = delivery.worker.claim(alert, promotion)
    second = delivery.worker.claim(alert, promotion)
    assert first["status"] == "sending" and second is None
    assert delivery.repo.history.count_documents({}) == 1


def test_mongo_outage_does_not_send_or_discard_pending_promotions(delivery, monkeypatch):
    delivery.add_alert()
    promotion = delivery.add_promotion()
    with monkeypatch.context() as patch:
        patch.setattr(delivery.worker, "bootstrap", lambda: (_ for _ in ()).throw(ServerSelectionTimeoutError("private uri")))
        with pytest.raises(ServerSelectionTimeoutError):
            asyncio.run(delivery.worker.run_once())
    assert "notifications_processed_at" not in delivery.repo.promotions.find_one({"_id": promotion["_id"]})
    delivery.bot.send_message.assert_not_awaited()
    asyncio.run(delivery.worker.run_once())
    delivery.bot.send_message.assert_awaited_once()


def test_recent_offers_are_tenant_scoped_and_limited(delivery):
    delivery.add_alert(123)
    delivery.add_alert(456, query="RX 9070")
    for _ in range(12):
        delivery.add_promotion()
    assert len(delivery.repo.recent_for_user(123)) == 10
    assert delivery.repo.recent_for_user(456) == []


def test_equivalent_model_without_brand_and_custom_window(delivery):
    delivery.worker.settings = replace(delivery.settings, alert_dedup_hours=1)
    delivery.add_alert()
    for _ in range(3):
        delivery.add_promotion("RTX 5070\nR$ 3.599\nKaBuM\nCupom GPU10")
        asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 1
    delivery.now[0] += timedelta(hours=1, seconds=1)
    delivery.add_promotion("RTX 5070\nR$ 3.599\nKaBuM\nCupom GPU10")
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 2


def test_rate_limit_stops_entire_batch_and_survives_restart(delivery):
    delivery.add_alert(123)
    delivery.add_alert(456)
    delivery.add_promotion()
    delivery.bot.send_message.side_effect = RetryAfter(timedelta(seconds=60))
    asyncio.run(delivery.worker.run_once())
    assert delivery.bot.send_message.await_count == 1
    restarted = NotificationWorker(delivery.repo, delivery.bot, delivery.settings, clock=lambda: delivery.now[0])
    asyncio.run(restarted.run_once())
    assert delivery.bot.send_message.await_count == 1


def test_dismissed_offer_is_hidden_only_from_its_owner(delivery):
    alert = delivery.add_alert(123)
    delivery.add_alert(456)
    promotion = delivery.add_promotion()
    delivery.repo.history.insert_one({"telegram_user_id": 123, "alert_id": alert["_id"], "promotion_id": promotion["_id"], "status": "sent", "dismissed": True})
    assert delivery.repo.recent_for_user(123) == []
    assert len(delivery.repo.recent_for_user(456)) == 1


def test_collector_to_worker_pipeline_without_real_telegram(repository, alerts_repository, settings, message, channel):
    from services.telegram_collector.collector import process_message

    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    worker = NotificationWorker(alerts_repository, bot, settings)
    worker.bootstrap()
    alerts_repository.create(123, {"query": "RTX 5070", "component_type": "gpu", "max_price": 3800})
    async def pipeline():
        assert await process_message(message, channel, settings, repository)
        await worker.run_once()
        assert not await process_message(message, channel, settings, repository)
        await worker.run_once()
    asyncio.run(pipeline())
    bot.send_message.assert_awaited_once()
    assert repository.promotions.find_one()["status"] == "parsed"


def test_worker_loop_recovers_mongo_outage_without_logging_uri(delivery, monkeypatch, caplog):
    monkeypatch.setattr(delivery.worker, "run_once", AsyncMock(side_effect=ServerSelectionTimeoutError("SECRET_URI")))
    async def stop_after_cycle(*args):
        raise asyncio.CancelledError
    monkeypatch.setattr("services.telegram_bot.notifier.asyncio.sleep", stop_after_cycle)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(delivery.worker.run_forever())
    assert "SECRET_URI" not in caplog.text
