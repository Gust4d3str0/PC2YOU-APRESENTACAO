import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from telethon.tl.custom.messagebutton import MessageButton
from telethon.tl.types import (
    ButtonTypeDefault, ButtonTypeSimpleWebView, InlineButtonTypeUrl,
    KeyboardButton, KeyboardButtonRow, KeyboardInlineButton, KeyboardInlineButtonRow,
    Message, MessageEntityTextUrl, MessageEntityUrl, PeerChannel,
    ReplyInlineMarkup, ReplyKeyboardMarkup,
)

from services.telegram_collector.collector import import_history, process_message
from services.telegram_collector.links import extract_message_links, select_offer_url, valid_http_url
from services.telegram_collector.parser import extract_urls, parse_message


OFFER = "https://www.kabum.com.br/produto/123?tag=canal"
HIDDEN = "https://www.pichau.com.br/placa-de-video"
SHORT = "https://amzn.to/oferta"
CHANNEL = "https://t.me/canal_ofertas"


def button(url=OFFER):
    return SimpleNamespace(url=url, click=Mock())


def parse_telegram(message):
    return parse_message(message.message, **extract_message_links(message))


@pytest.mark.parametrize("text,expected", [
    (f"SSD por R$ 100 {OFFER}", OFFER),
    (f"SSD por R$ 100 {CHANNEL} {OFFER}", OFFER),
    (f"SSD por R$ 100 {OFFER} {SHORT}", OFFER),
    (f"SSD por R$ 100 {SHORT}", SHORT),
    ("SSD por R$ 100 https://mercadolivre.com/sec/AbCd", "https://mercadolivre.com/sec/AbCd"),
    ("SSD por R$ 100 https://loja-independente.test/produto/123", "https://loja-independente.test/produto/123"),
    ("SSD por R$ 100", None),
    (f"SSD por R$ 100 {CHANNEL}", None),
    ("SSD por R$ 100 https://images.test/ssd.jpg?size=large", None),
])
def test_visible_urls_selection(text, expected):
    parsed = parse_message(text)
    assert parsed["offer"]["url"] == expected
    if expected:
        assert expected in parsed["links"]


def test_hidden_entity_beats_visible_url(message):
    message.message = f"SSD por R$ 100 {OFFER} Comprar"
    message.entities = [MessageEntityTextUrl(0, 1, HIDDEN)]
    parsed = parse_telegram(message)
    assert parsed["offer"]["url"] == HIDDEN
    assert parsed["links"] == [OFFER, HIDDEN]


def test_message_entity_url_uses_utf16_offset_after_emoji(message):
    prefix = "🔥 SSD por R$ 100: "
    message.message = prefix + OFFER
    message.entities = [MessageEntityUrl(len(prefix.encode("utf-16-le")) // 2, len(OFFER))]
    found = extract_message_links(message)
    assert found["entity_urls"] == [OFFER]
    assert parse_telegram(message)["links"] == [OFFER]


@pytest.mark.parametrize("offset,length", [(-1, 10), (0, 0), (9999, 30), (0, 1)])
def test_malformed_entity_offsets_are_ignored(message, offset, length):
    message.message = "🔥 SSD por R$ 100"
    message.entities = [MessageEntityUrl(offset, length)]
    assert extract_message_links(message)["entity_urls"] == []


def test_inline_button_priority_and_all_links_preserved(message):
    message.message = f"SSD por R$ 100 {OFFER}"
    message.entities = [MessageEntityTextUrl(0, 1, HIDDEN)]
    link_button = button(SHORT)
    message.buttons = [[link_button]]
    parsed = parse_telegram(message)
    assert parsed["offer"]["url"] == SHORT
    assert parsed["links"] == [OFFER, HIDDEN, SHORT]
    link_button.click.assert_not_called()


def test_multiple_buttons_prefer_purchase_and_deduplicate(message):
    message.message = "SSD por R$ 100"
    message.buttons = [[button(CHANNEL), button("https://images.test/banner.png")], [button(OFFER), button(OFFER)]]
    parsed = parse_telegram(message)
    assert parsed["offer"]["url"] == OFFER
    assert parsed["links"] == [CHANNEL, "https://images.test/banner.png", OFFER]


def test_social_button_does_not_override_hidden_store(message):
    message.buttons = [[button(CHANNEL)]]
    message.entities = [MessageEntityTextUrl(0, 1, SHORT)]
    parsed = parse_telegram(message)
    assert parsed["offer"]["url"] == SHORT


def test_unknown_affiliate_button_is_not_restricted_to_store_allowlist(message):
    message.buttons = [[button("https://descontos.test/r/abc")]]
    assert parse_telegram(message)["offer"]["url"] == "https://descontos.test/r/abc"


def test_homepage_button_loses_to_explicit_product_url(message):
    message.message = f"SSD por R$ 100 {OFFER}"
    message.buttons = [[button("https://amazon.com.br/")]]
    assert parse_telegram(message)["offer"]["url"] == OFFER


def test_same_source_prefers_known_product_over_unrelated_generic_link():
    assert select_offer_url(button_urls=["https://blog.test/post", OFFER]) == OFFER


@pytest.mark.parametrize("buttons", [None, [], [[None]], [[SimpleNamespace(text="Comprar")]],
                                   [[SimpleNamespace(data=b"https://fake.test", text=OFFER)]], "not rows", [42]])
def test_absent_or_non_url_buttons_do_not_create_urls(message, buttons):
    message.message = "SSD por R$ 100"
    message.buttons = buttons
    assert parse_telegram(message)["offer"]["url"] is None
    assert parse_telegram(message)["links"] == []


def test_wrapped_telethon_button_url(message):
    raw = KeyboardInlineButton("Comprar", InlineButtonTypeUrl(OFFER))
    wrapped = MessageButton(Mock(), raw, None, None, message.id)
    message.message = "SSD por R$ 100"
    message.buttons = [[wrapped]]
    assert parse_telegram(message)["offer"]["url"] == OFFER


def test_raw_markup_on_unbound_historical_telethon_message():
    raw = Message(id=123, peer_id=PeerChannel(123), message="SSD por R$ 100",
                  reply_markup=ReplyInlineMarkup([KeyboardInlineButtonRow([
                      KeyboardInlineButton("Canal", InlineButtonTypeUrl(CHANNEL)),
                      KeyboardInlineButton("Comprar", InlineButtonTypeUrl(SHORT)),
                  ])]))
    assert raw.buttons is None
    parsed = parse_telegram(raw)
    assert parsed["offer"]["url"] == SHORT
    assert parsed["links"] == [CHANNEL, SHORT]


def test_raw_keyboard_url_and_button_without_url():
    raw = Message(id=123, peer_id=PeerChannel(123), message="SSD por R$ 100",
                  reply_markup=ReplyKeyboardMarkup([KeyboardButtonRow([
                      KeyboardButton("Ajuda", ButtonTypeDefault()),
                      KeyboardButton("Comprar", ButtonTypeSimpleWebView(OFFER)),
                  ])]))
    assert parse_telegram(raw)["offer"]["url"] == OFFER


def test_old_style_raw_button_direct_url(message):
    message.message = "SSD por R$ 100"
    message.reply_markup = SimpleNamespace(rows=[SimpleNamespace(buttons=[button(OFFER)])])
    assert parse_telegram(message)["offer"]["url"] == OFFER


def test_unavailable_custom_buttons_property_falls_back_to_raw_markup():
    class HistoricalMessage:
        message = "SSD por R$ 100"
        reply_markup = SimpleNamespace(rows=[SimpleNamespace(buttons=[button(OFFER)])])

        @property
        def buttons(self):
            raise ValueError("No bound chat")

    assert parse_telegram(HistoricalMessage())["offer"]["url"] == OFFER


@pytest.mark.parametrize("url", [None, "", "javascript:alert(1)", "tg://user?id=1", "ftp://shop.test/file",
                               "https://[invalid", "https://user:pass@shop.test/offer", "https://shop.test:99999/offer",
                               "https://shop.test/a\nb", "https://shop.test/a b", "https://shop.test\\@evil.test"])
def test_invalid_links_are_not_persistable_targets(url):
    assert valid_http_url(url) is None
    assert select_offer_url(button_urls=[url]) is None


def test_structured_short_link_preserves_target_exactly():
    url = "https://redirect.test/go?target=a)&tag=x!"
    assert parse_message("SSD", button_urls=[url])["offer"]["url"] == url
    assert extract_urls("", [url]) == [url]


def test_new_button_link_is_saved(repository, settings, message, channel):
    message.message = "SSD por R$ 100"
    message.buttons = [[button(OFFER)]]
    assert asyncio.run(process_message(message, channel, settings, repository))
    saved = repository.promotions.find_one()
    assert saved["offer"]["url"] == OFFER and saved["links"] == [OFFER]


@pytest.mark.parametrize("previous", [None, "", "javascript:fake"])
def test_reimport_completes_missing_or_invalid_offer_url(repository, settings, message, channel, previous):
    message.message = "SSD por R$ 100"
    assert asyncio.run(process_message(message, channel, settings, repository))
    saved = repository.promotions.find_one()
    repository.promotions.update_one({}, {"$set": {
        "offer.url": previous, "status": "published", "notifications_processed_at": saved["created_at"],
    }})
    before = repository.promotions.find_one()
    message.buttons = [[button(OFFER)]]
    assert not asyncio.run(process_message(message, channel, settings, repository))
    after = repository.promotions.find_one()
    assert after["offer"]["url"] == OFFER and after["links"] == [OFFER]
    before["offer"]["url"] = OFFER
    before["links"] = [OFFER]
    before["offer"].update(url_valid=True, url_source="button")
    assert before == after  # No matching, price, status, dates or notification state changed.


@pytest.mark.parametrize("new_url", [None, SHORT])
def test_reimport_preserves_valid_existing_offer_and_unions_links(repository, settings, message, channel, new_url):
    message.message = f"SSD por R$ 100 {OFFER}"
    assert asyncio.run(process_message(message, channel, settings, repository))
    message.message = "SSD por R$ 150"  # Unrelated parsed fields must stay unchanged.
    message.buttons = [[button(new_url)]]
    assert not asyncio.run(process_message(message, channel, settings, repository))
    saved = repository.promotions.find_one()
    assert saved["offer"]["url"] == OFFER
    assert set(saved["links"]) == ({OFFER, SHORT} if new_url else {OFFER})
    assert saved["offer"]["price"].to_decimal() == 100


def test_history_reprocesses_existing_message_buttons(repository, settings, message, channel):
    message.message = "SSD por R$ 100"

    async def messages():
        yield message

    client = SimpleNamespace(iter_messages=lambda *a, **kw: messages())
    sources = {-1001234567890: channel}
    assert asyncio.run(import_history(client, sources, settings, repository, 5)) == 1
    message.buttons = [[button(SHORT)]]
    assert asyncio.run(import_history(client, sources, settings, repository, 5)) == 0
    assert repository.promotions.count_documents({}) == 1
    assert repository.promotions.find_one()["offer"]["url"] == SHORT


def test_concurrent_reimports_preserve_first_valid_url_and_all_links(repository):
    identity = {"chat_id": -100123, "message_id": 99}
    repository.save({"telegram": identity, "offer": {"url": None}, "links": []})
    targets = [f"https://shop.test/product/{i}" for i in range(12)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda url: repository.save({"telegram": identity, "offer": {"url": url}, "links": [url]}), targets))
    assert not any(results)
    saved = repository.promotions.find_one()
    assert saved["offer"]["url"] in targets
    assert set(saved["links"]) == set(targets)


def test_reimport_compare_and_set_does_not_overwrite_concurrent_valid_url(repository, monkeypatch):
    identity = {"chat_id": -100123, "message_id": 99}
    repository.save({"telegram": identity, "offer": {"url": None}, "links": []})
    update = repository.promotions.update_one

    def concurrent_update(selector, changes, **kwargs):
        if "$addToSet" in changes:
            update({"telegram.message_id": 99}, {"$set": {"offer.url": SHORT}, "$addToSet": {"links": SHORT}})
        return update(selector, changes, **kwargs)

    monkeypatch.setattr(repository.promotions, "update_one", concurrent_update)
    repository.save({"telegram": identity, "offer": {"url": OFFER}, "links": [OFFER]})
    saved = repository.promotions.find_one()
    assert saved["offer"]["url"] == SHORT
    assert set(saved["links"]) == {SHORT, OFFER}
