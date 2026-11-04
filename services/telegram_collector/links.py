"""Extract and rank existing links only. Never fetch, resolve or click a URL."""

import re
from urllib.parse import urlsplit
try:
    from product_matching.quality import valid_http_url as quality_http_url
except ImportError:
    from services.product_matching.quality import valid_http_url as quality_http_url



URL_RE = re.compile(r"https?://[^\s<>\"\u201c\u201d]+", re.IGNORECASE)
_SHOP_DOMAINS = (
    "mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com", "meli.la",
    "kabum.com.br", "pichau.com.br", "terabyteshop.com.br", "amazon.com.br", "amazon.com", "amzn.to",
)
_SOCIAL_DOMAINS = (
    "t.me", "telegram.me", "telegram.dog", "instagram.com", "facebook.com", "fb.com",
    "twitter.com", "x.com", "youtube.com", "youtu.be", "tiktok.com", "discord.gg", "discord.com",
    "whatsapp.com", "wa.me",
)
_IMAGE_RE = re.compile(r"\.(?:jpe?g|png|gif|webp|svg|avif|bmp|ico)$", re.IGNORECASE)
_PRODUCT_RE = re.compile(r"/(?:produto|product|products|item|dp|gp/product|p|sec)(?:/|$)|/MLB[-\d]", re.IGNORECASE)
_INFO_RE = re.compile(r"/(?:institucional|atendimento|ajuda|help|contato|contact|login|signin|privacidade|privacy)(?:/|$)", re.IGNORECASE)


def valid_http_url(value: object) -> str | None:
    return quality_http_url(value.strip()) if isinstance(value, str) else None


def extract_urls(text: object, extra_urls=()) -> list[str]:
    # Punctuation may surround a visible link. Structured targets are kept verbatim:
    # trailing '?', ')' or '!' can legitimately belong to a button's affiliate URL.
    candidates = [url.rstrip(".,;:!?)]}'\"") for url in URL_RE.findall(text)] if isinstance(text, str) else []
    candidates.extend(extra_urls or ())
    result = []
    for candidate in candidates:
        url = valid_http_url(candidate)
        if url and url not in result:
            result.append(url)
    return result


def _domain_matches(host, domains):
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def select_offer_url(*, button_urls=(), text_urls=(), visible_urls=(), other_urls=()) -> str | None:
    candidates = []
    for source, urls in enumerate((button_urls, text_urls, visible_urls, other_urls)):
        for url in extract_urls("", urls):
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if _domain_matches(host, _SOCIAL_DOMAINS) or _IMAGE_RE.search(parsed.path):
                continue
            # A shop homepage/help page is weaker evidence than an actual destination.
            destination = bool(parsed.path.strip("/") or parsed.query) and not _INFO_RE.search(parsed.path)
            shop = _domain_matches(host, _SHOP_DOMAINS)
            product = bool(_PRODUCT_RE.search(parsed.path))
            candidates.append(((-int(destination), source, -int(shop), -int(product), len(candidates)), url))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _get(obj, name, default=None):
    # Optional custom properties may be unavailable on unbound historical messages.
    try:
        return getattr(obj, name, default)
    except (AttributeError, ValueError, TypeError, RuntimeError):
        return default


def _rows(value):
    return value if isinstance(value, (list, tuple)) else ()


def extract_message_links(message) -> dict:
    """Support custom MessageButton objects and raw TL reply_markup as a fallback.

    Telethon 1.45 stores raw inline targets in button.type.url; older TL layouts and
    custom MessageButton expose button.url. Reading properties is synchronous only.
    """
    from telethon import utils
    from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
    buttons = []
    for row in _rows(_get(message, "buttons")):
        buttons.extend(_rows(row) or _rows(_get(row, "buttons")))
    markup = _get(message, "reply_markup")
    for row in _rows(_get(markup, "rows")):
        buttons.extend(_rows(_get(row, "buttons")))
    button_urls = []
    for button in buttons:
        # Do not interpret callback data, labels or actions as links. Only an
        # existing .url attribute is considered; no button action is executed.
        raw = _get(button, "button", button)
        candidates = (_get(button, "url"), _get(raw, "url"), _get(_get(raw, "type"), "url"))
        button_urls.extend(extract_urls("", candidates))
    text_urls, entity_urls = [], []
    text = _get(message, "message")
    for entity in _rows(_get(message, "entities")):
        if isinstance(entity, MessageEntityTextUrl):
            text_urls.extend(extract_urls("", [_get(entity, "url")]))
        elif isinstance(entity, MessageEntityUrl) and isinstance(text, str):
            offset, length = _get(entity, "offset"), _get(entity, "length")
            if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length <= 0:
                continue
            try:
                # Telethon handles Telegram UTF-16 offsets, including emoji prefixes.
                entity_urls.extend(extract_urls("", utils.get_inner_text(text, [entity])))
            except (ValueError, UnicodeError):
                continue
    return {"button_urls": extract_urls("", button_urls), "extra_urls": text_urls, "entity_urls": entity_urls}
