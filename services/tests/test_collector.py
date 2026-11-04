import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telethon.tl.types import Chat, ChatPhotoEmpty, MessageEntityTextUrl, User

from services.telegram_collector.collector import import_history, is_allowed_source, list_chats, message_url, process_message, resolve_sources, run
from services.telegram_collector.config import ConfigurationError, Settings, load_settings, parse_allowed_chats
from services.telegram_collector.logging_setup import SecretFormatter


async def items(values):
    for value in values:
        yield value


def test_whitelist_config_is_fail_closed():
    assert parse_allowed_chats("") == frozenset()
    assert parse_allowed_chats("-100123, -987,-100123") == frozenset({-100123, -987})
    for raw in ("123", "-100123,anything", "0"):
        with pytest.raises(ConfigurationError):
            parse_allowed_chats(raw)
    with pytest.raises(ConfigurationError):
        Settings().require_sources()


def test_config_uses_existing_mongo_variables_and_hides_secrets(monkeypatch):
    import services.telegram_collector.config as config

    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    for key, value in {"MONGO_URI": "mongodb://test:27017", "MONGO_DB": "catalog_test", "TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "SECRET_HASH", "TELEGRAM_PHONE": "SECRET_PHONE", "TELEGRAM_BOT_TOKEN": "SECRET_TOKEN", "TELEGRAM_ALLOWED_CHATS": "-100123", "TELEGRAM_HISTORY_LIMIT": "100"}.items():
        monkeypatch.setenv(key, value)
    settings = load_settings()
    assert settings.mongo_db == "catalog_test"
    assert settings.mongo_uri == "mongodb://test:27017"
    assert "SECRET" not in repr(settings)
    monkeypatch.setenv("TELEGRAM_HISTORY_LIMIT", "0")
    with pytest.raises(ConfigurationError):
        load_settings()


def test_log_formatter_removes_secrets():
    import logging

    formatter = SecretFormatter(("SECRET",))
    record = logging.LogRecord("test", logging.ERROR, "", 1, "failure %s", ("SECRET",), None)
    assert "SECRET" not in formatter.format(record)


def test_private_chats_are_never_allowed(settings):
    user = User(id=55, first_name="Privado")
    assert not is_allowed_source(55, user, {55})
    assert not is_allowed_source(-55, user, {-55})


def test_unauthorized_private_outgoing_and_empty_messages_are_not_stored(repository, message, settings, channel):
    assert not asyncio.run(process_message(message, channel, Settings(), repository))
    assert not asyncio.run(process_message(message, User(id=55), settings, repository))
    for updates in ({"out": True}, {"message": ""}, {"message": None}, {"message": "Bom dia!"}, {"action": object()}):
        candidate = SimpleNamespace(**{**vars(message), **updates})
        assert not asyncio.run(process_message(candidate, channel, settings, repository))
    assert repository.promotions.count_documents({}) == 0


def test_optional_metadata_and_hidden_links(repository, settings, message, channel):
    channel.username = None
    message.entities = [MessageEntityTextUrl(offset=0, length=1, url="https://amzn.to/test")]
    message.message = "Oferta de SSD por R$ 100"
    channel.title = None
    assert asyncio.run(process_message(message, channel, settings, repository))
    saved = repository.promotions.find_one()
    assert saved["telegram"]["chat_name"] is None
    assert saved["telegram"]["message_url"] == "https://t.me/c/1234567890/10"
    assert saved["offer"]["store"] == "Amazon"


def test_legacy_group_link_is_unknown():
    group = Chat(id=123, title="Grupo", photo=ChatPhotoEmpty(), participants_count=1, date=datetime.now(timezone.utc), version=1)
    assert message_url(group, 10) is None


def test_history_is_whitelisted_configurable_and_repeatable(repository, settings, message, channel):
    calls = []

    def history(entity, limit):
        calls.append(limit)
        return items([message])

    client = SimpleNamespace(iter_messages=history)
    sources = {-1001234567890: channel}
    assert asyncio.run(import_history(client, sources, settings, repository, 25)) == 1
    assert asyncio.run(import_history(client, sources, settings, repository, 25)) == 0
    assert calls == [25, 25]


def test_list_chats_excludes_private_dialogs(settings, channel, capsys):
    dialogs = [SimpleNamespace(id=-1001234567890, entity=channel, name=channel.title), SimpleNamespace(id=55, entity=User(id=55), name="Privado")]
    client = SimpleNamespace(iter_dialogs=lambda: items(dialogs))
    asyncio.run(list_chats(client))
    output = capsys.readouterr().out
    assert "Promo Hardware" in output and "canal" in output
    assert "Privado" not in output
    sources = asyncio.run(resolve_sources(client, settings))
    assert set(sources) == settings.allowed_chats
    with pytest.raises(ConfigurationError):
        asyncio.run(resolve_sources(client, Settings(allowed_chats=frozenset({-999}))))


def test_list_requires_existing_session_and_disconnects(monkeypatch, settings, tmp_path):
    import services.telegram_collector.collector as collector

    client = SimpleNamespace(connect=AsyncMock(), is_user_authorized=AsyncMock(return_value=False), disconnect=AsyncMock())
    monkeypatch.setattr(collector, "TelegramClient", lambda *args: client)
    from dataclasses import replace

    with pytest.raises(ConfigurationError, match="auth"):
        asyncio.run(run(SimpleNamespace(command="list-chats"), replace(settings, session_path=tmp_path / "session")))
    client.disconnect.assert_awaited_once()


def test_listen_registers_before_backfill_and_rejects_private_events(monkeypatch, settings, tmp_path, repository, message, channel):
    from dataclasses import replace

    import services.telegram_collector.collector as collector

    order = []
    registered = []
    private = SimpleNamespace(is_private=True, chat_id=-1001234567890, id=11, message=SimpleNamespace(**{**vars(message), "id": 11}))
    outside = SimpleNamespace(is_private=False, chat_id=-1009999999, id=12, message=SimpleNamespace(**{**vars(message), "id": 12}))
    valid = SimpleNamespace(is_private=False, chat_id=-1001234567890, id=10, message=message)

    def register(handler, event):
        order.append("register")
        registered.append(handler)
        assert event.chats == [-1001234567890]

    def history(entity, limit):
        order.append("history")
        assert registered and limit == 15
        return items([message])

    async def disconnected():
        for event in (private, outside, valid):
            await registered[0](event)

    client = SimpleNamespace(
        connect=AsyncMock(), is_user_authorized=AsyncMock(return_value=True),
        get_me=AsyncMock(return_value=SimpleNamespace(bot=False)), disconnect=AsyncMock(),
        iter_dialogs=lambda: items([SimpleNamespace(id=-1001234567890, entity=channel)]),
        iter_messages=history, add_event_handler=register,
        run_until_disconnected=disconnected, is_connected=lambda: True,
    )
    mongo_client = SimpleNamespace(close=Mock())
    monkeypatch.setattr(collector, "TelegramClient", lambda *args: client)
    monkeypatch.setattr(collector, "open_repository", lambda settings: (mongo_client, repository))
    args = SimpleNamespace(command="listen", import_history=True, limit=15)
    asyncio.run(run(args, replace(settings, session_path=tmp_path / "session")))
    assert order == ["register", "history"]
    assert repository.promotions.count_documents({}) == 1
    assert repository.service_status.find_one()["connected"] is False
    client.disconnect.assert_awaited_once()
    mongo_client.close.assert_called_once()
