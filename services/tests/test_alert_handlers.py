import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from services.telegram_bot.bot import build_application, start_worker, stop_worker
from services.telegram_bot.handlers import AlertHandlers, DRAFT_KEY
from services.telegram_collector.config import Settings


@pytest.fixture
def conversation(alerts_repository, settings):
    message = SimpleNamespace(reply_text=AsyncMock(), text="")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=123), effective_chat=SimpleNamespace(type="private"), effective_message=message, callback_query=None)
    context = SimpleNamespace(args=[], user_data={})
    handlers = AlertHandlers(alerts_repository, settings)
    return SimpleNamespace(update=update, context=context, handlers=handlers, message=message, repo=alerts_repository)


def reply(conversation, text):
    conversation.message.text = text
    asyncio.run(conversation.handlers.safe(conversation.handlers.text)(conversation.update, conversation.context))


def callback(conversation, data):
    conversation.update.callback_query = SimpleNamespace(answer=AsyncMock(), data=data)
    asyncio.run(conversation.handlers.safe(conversation.handlers.callback)(conversation.update, conversation.context))
    conversation.update.callback_query = None


def begin(conversation, args=None):
    conversation.context.args = args or []
    asyncio.run(conversation.handlers.safe(conversation.handlers.follow)(conversation.update, conversation.context))


def test_follow_without_argument_creates_only_after_confirmation(conversation):
    begin(conversation)
    assert "Qual peça" in conversation.message.reply_text.call_args.args[0]
    reply(conversation, "RTX 5070")
    reply(conversation, "R$ 3.800,00")
    assert conversation.repo.alerts.count_documents({}) == 0
    token = conversation.context.user_data[DRAFT_KEY]["token"]
    callback(conversation, f"pc2:save:{token}")
    assert conversation.repo.alerts.count_documents({"telegram_user_id": 123}) == 1
    assert "Alerta criado" in conversation.message.reply_text.call_args.args[0]
    callback(conversation, f"pc2:save:{token}")
    assert conversation.repo.alerts.count_documents({}) == 1


def test_follow_command_reuses_query_and_validates_price(conversation):
    begin(conversation, ["RTX", "5070"])
    assert "Até quanto" in conversation.message.reply_text.call_args.args[0]
    reply(conversation, "-3")
    assert conversation.context.user_data[DRAFT_KEY]["field"] == "max_price"
    reply(conversation, "3800")
    assert conversation.context.user_data[DRAFT_KEY]["values"]["component_type"] == "gpu"


def test_filter_edit_pause_state_and_cancel(conversation):
    begin(conversation, ["RTX", "5070"])
    reply(conversation, "3800")
    token = conversation.context.user_data[DRAFT_KEY]["token"]
    callback(conversation, f"pc2:filters:{token}")
    callback(conversation, f"pc2:field:{token}:ignored_brands")
    reply(conversation, "Biostar, MSI")
    callback(conversation, f"pc2:field:{token}:stores")
    reply(conversation, "KaBuM, Pichau")
    callback(conversation, f"pc2:field:{token}:minimum_discount")
    reply(conversation, "10%")
    callback(conversation, f"pc2:toggle:{token}")
    callback(conversation, f"pc2:save:{token}")
    alert = conversation.repo.alerts.find_one()
    assert not alert["enabled"] and alert["ignored_brands"] == ["Biostar", "MSI"]
    callback(conversation, f"pc2:resume:{alert['_id']}")
    assert conversation.repo.alerts.find_one()["enabled"]
    callback(conversation, f"pc2:edit:{alert['_id']}")
    draft = conversation.context.user_data[DRAFT_KEY]
    callback(conversation, f"pc2:field:{draft['token']}:max_price")
    reply(conversation, "2400")
    callback(conversation, f"pc2:cancel:{draft['token']}")
    assert str(conversation.repo.alerts.find_one()["max_price"]) == "3800.00"


def test_removal_requires_confirmation_and_pause_does_not_delete(conversation):
    alert = conversation.repo.create(123, {"query": "RTX 5070", "max_price": 3800})
    conversation.context.args = ["1"]
    asyncio.run(conversation.handlers.remove(conversation.update, conversation.context))
    assert conversation.repo.alerts.count_documents({}) == 1
    assert "realmente remover" in conversation.message.reply_text.call_args.args[0]
    asyncio.run(conversation.handlers.pause(conversation.update, conversation.context))
    assert not conversation.repo.alerts.find_one()["enabled"]
    callback(conversation, f"pc2:delete:{alert['_id']}")
    assert conversation.repo.alerts.count_documents({}) == 0


def test_expired_or_old_draft_buttons_never_activate_another_draft(conversation):
    begin(conversation, ["RTX", "5070"])
    reply(conversation, "3800")
    old = conversation.context.user_data[DRAFT_KEY]["token"]
    begin(conversation, ["RX", "9070"])
    reply(conversation, "4000")
    callback(conversation, f"pc2:save:{old}")
    assert conversation.repo.alerts.count_documents({}) == 0
    draft = conversation.context.user_data[DRAFT_KEY]
    draft["expires_at"] = time.time() - 1
    callback(conversation, f"pc2:save:{draft['token']}")
    assert conversation.repo.alerts.count_documents({}) == 0


def test_unauthorized_users_and_group_chats_cannot_store_drafts(conversation):
    conversation.handlers.settings = replace(conversation.handlers.settings, allowed_users=frozenset({999}))
    begin(conversation, ["RTX", "5070"])
    assert DRAFT_KEY not in conversation.context.user_data
    assert "privado" in conversation.message.reply_text.call_args.args[0]
    conversation.handlers.settings = Settings()
    conversation.update.effective_chat.type = "group"
    begin(conversation, ["RTX", "5070"])
    assert DRAFT_KEY not in conversation.context.user_data


def test_callbacks_enforce_alert_and_notification_ownership(conversation):
    alert = conversation.repo.create(999, {"query": "RTX 5070", "max_price": 3800})
    for action in ("edit", "pause", "delete", "remove"):
        callback(conversation, f"pc2:{action}:{alert['_id']}")
    assert conversation.repo.alerts.find_one()["enabled"]
    assert conversation.repo.alerts.count_documents({}) == 1
    row = {"telegram_user_id": 999, "alert_id": alert["_id"], "promotion_id": alert["_id"], "status": "sent"}
    row_id = conversation.repo.history.insert_one(row).inserted_id
    callback(conversation, f"pc2:ignore:{row_id}")
    assert not conversation.repo.history.find_one().get("dismissed", False)


def test_mongo_failure_preserves_draft_without_exposing_private_errors(conversation, monkeypatch):
    begin(conversation, ["RTX", "5070"])
    reply(conversation, "3800")
    token = conversation.context.user_data[DRAFT_KEY]["token"]
    monkeypatch.setattr(conversation.repo, "create", Mock(side_effect=ServerSelectionTimeoutError("SECRET_URI")))
    callback(conversation, f"pc2:save:{token}")
    assert DRAFT_KEY in conversation.context.user_data
    assert "indisponível" in conversation.message.reply_text.call_args.args[0]
    assert "SECRET_URI" not in conversation.message.reply_text.call_args.args[0]


def test_lists_help_id_and_offers_commands(conversation):
    asyncio.run(conversation.handlers.list_alerts(conversation.update, conversation.context))
    assert "ainda não" in conversation.message.reply_text.call_args.args[0]
    conversation.repo.create(123, {"query": "RTX 5070", "max_price": None})
    asyncio.run(conversation.handlers.list_alerts(conversation.update, conversation.context))
    assert "SEUS ALERTAS" in conversation.message.reply_text.call_args.args[0]
    asyncio.run(conversation.handlers.help(conversation.update, conversation.context))
    assert "/ofertas" in conversation.message.reply_text.call_args.args[0]
    asyncio.run(conversation.handlers.my_id(conversation.update, conversation.context))
    assert "123" in conversation.message.reply_text.call_args.args[0]
    asyncio.run(conversation.handlers.offers(conversation.update, conversation.context))
    assert "Nenhuma oferta" in conversation.message.reply_text.call_args.args[0]


def test_all_commands_registered_and_worker_lifecycle_is_local(repository, monkeypatch):
    app = build_application(Settings(bot_token="123456:FAKE_TEST_TOKEN"), repository)
    commands = {command for handler in app.handlers[1] if hasattr(handler, "commands") for command in handler.commands}
    assert {"acompanhar", "alertas", "remover", "pausar", "ofertas", "ajuda", "meuid", "cancelar"} == commands
    async def waiting(self):
        await asyncio.Event().wait()
    monkeypatch.setattr("services.telegram_bot.bot.NotificationWorker.run_forever", waiting)
    async def lifecycle():
        await start_worker(app)
        assert "notification_task" in app.bot_data
        await stop_worker(app)
        await stop_worker(app)
    asyncio.run(lifecycle())


def test_confirmed_edit_updates_existing_alert_and_clears_filter(conversation):
    alert = conversation.repo.create(123, {"query": "RTX 5070", "max_price": 3800, "brands": ["GALAX"]})
    callback(conversation, f"pc2:edit:{alert['_id']}")
    token = conversation.context.user_data[DRAFT_KEY]["token"]
    callback(conversation, f"pc2:field:{token}:brands")
    reply(conversation, "-")
    callback(conversation, f"pc2:field:{token}:ignored_brands")
    reply(conversation, "ignorar: Biostar")
    callback(conversation, f"pc2:field:{token}:component_type")
    reply(conversation, "gpu")
    callback(conversation, f"pc2:field:{token}:max_price")
    reply(conversation, "3900")
    callback(conversation, f"pc2:save:{token}")
    updated = conversation.repo.alerts.find_one()
    assert updated["brands"] == [] and updated["ignored_brands"] == ["Biostar"]
    assert str(updated["max_price"]) == "3900.00"
    assert conversation.repo.alerts.count_documents({}) == 1


def test_offers_with_purchase_link_and_pagination(conversation):
    from datetime import datetime, timezone
    from services.telegram_collector.repository import bson_values

    for index in range(11):
        conversation.repo.create(123, {"query": "RTX 5070", "max_price": None})
    asyncio.run(conversation.handlers.list_alerts(conversation.update, conversation.context))
    markup = conversation.message.reply_text.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[-1][0].callback_data == "pc2:list:10"
    callback(conversation, "pc2:list:10")
    assert "11." in conversation.message.reply_text.call_args.args[0]
    conversation.repo.promotions.insert_one(bson_values({"raw_text": "RTX 5070", "offer": {"price": 3500, "url": "https://kabum.com.br/item"}, "product": {}, "created_at": datetime.now(timezone.utc)}))
    asyncio.run(conversation.handlers.offers(conversation.update, conversation.context))
    assert "OFERTA RECENTE" in conversation.message.reply_text.call_args.args[0]
    assert conversation.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0].url == "https://kabum.com.br/item"


def test_recent_offer_without_purchase_url_does_not_link_to_telegram_post(conversation):
    from datetime import datetime, timezone

    conversation.repo.create(123, {"query": "RTX 5070", "max_price": None})
    conversation.repo.promotions.insert_one({"raw_text": "RTX 5070", "offer": {"url": None, "price": 3500}, "product": {},
                                           "telegram": {"message_url": "https://t.me/canal/99"},
                                           "created_at": datetime.now(timezone.utc)})
    asyncio.run(conversation.handlers.offers(conversation.update, conversation.context))
    assert conversation.message.reply_text.call_args.kwargs["reply_markup"] is None
