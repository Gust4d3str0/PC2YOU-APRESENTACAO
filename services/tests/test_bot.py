import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services.telegram_bot.bot import build_application, start, status
from services.telegram_collector.config import ConfigurationError, Settings


def test_start_introduces_pc2you_without_storing_user_data():
    message = SimpleNamespace(reply_text=AsyncMock())
    asyncio.run(start(SimpleNamespace(effective_message=message), None))
    assert "PC2YOU" in message.reply_text.call_args.args[0]
    assert "hardware" in message.reply_text.call_args.args[0]


def test_status_reports_counts_and_collector_health(settings):
    message = SimpleNamespace(reply_text=AsyncMock())
    repo = SimpleNamespace(summary=Mock(return_value={"promotions": 42, "collector_online": False, "collector_sources": 1}))
    context = SimpleNamespace(bot_data={"repository": repo, "settings": settings})
    asyncio.run(status(SimpleNamespace(effective_message=message), context))
    text = message.reply_text.call_args.args[0]
    assert "42" in text and "Fontes configuradas: 1" in text
    assert "offline" in text


def test_status_handles_database_outage_without_exposing_errors(settings):
    message = SimpleNamespace(reply_text=AsyncMock())
    repo = SimpleNamespace(summary=Mock(side_effect=RuntimeError("SECRET_CONNECTION")))
    context = SimpleNamespace(bot_data={"repository": repo, "settings": settings})
    asyncio.run(status(SimpleNamespace(effective_message=message), context))
    text = message.reply_text.call_args.args[0]
    assert "MongoDB indisponível" in text
    assert "SECRET" not in text


def test_only_start_and_status_commands_are_registered():
    app = build_application(Settings(bot_token="123456:FAKE_TEST_TOKEN"), None)
    assert {command for handler in app.handlers[0] for command in handler.commands} == {"start", "status"}
    with pytest.raises(ConfigurationError):
        build_application(Settings(), None)
