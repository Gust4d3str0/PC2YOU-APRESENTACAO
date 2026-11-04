"""Regras conservadoras: informação ambígua permanece ausente."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit

from .filters import normalize_text
from .links import URL_RE as _URL_RE, extract_urls, select_offer_url
try:
    from product_matching.offers import extract_conditions
except ImportError:
    from services.product_matching.offers import extract_conditions


_AMOUNT = r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})?"
_PRICE_RE = re.compile(
    rf"(?<![\w.,/])(?:R\$\s*(?P<currency>{_AMOUNT})|(?P<bare>\d+(?:\.\d{{3}})*,\d{{2}}))(?![\w/]|[.,]\d|\s*%)",
    re.IGNORECASE,
)
_COUPON_RE = re.compile(r"\b(?:cupom(?:\s*:\s*|\s+)|use\s+)[`'\"]?([A-Za-z0-9][A-Za-z0-9_-]{2,39})\b", re.IGNORECASE)
_STORES = {
    "KaBuM": (r"\bkabum\b", ("kabum.com.br",)),
    "Pichau": (r"\bpichau\b", ("pichau.com.br",)),
    "Terabyte": (r"\bterabyte(?:shop)?\b", ("terabyteshop.com.br",)),
    "Amazon": (r"\bamazon\b", ("amazon.com.br", "amazon.com", "amzn.to")),
    "Mercado Livre": (r"\bmercado\s*livre\b", ("mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com", "meli.la")),
}


def _domain_store(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    for store, (_, domains) in _STORES.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return store
    return None


def identify_store(text: object, urls=()) -> str | None:
    links = extract_urls(text, urls)
    # Não interpretar nomes no caminho de um domínio desconhecido como loja.
    plain = normalize_text(_URL_RE.sub(" ", text)) if isinstance(text, str) else ""
    found = {store for store, (pattern, _) in _STORES.items() if re.search(pattern, plain)}
    found.update(filter(None, (_domain_store(url) for url in links)))
    return next(iter(found)) if len(found) == 1 else None


def extract_prices(text: object) -> tuple[Decimal | None, Decimal | None]:
    if not isinstance(text, str):
        return None, None
    # URLs e códigos de cupom não são fontes de valores monetários.
    clean = normalize_text(_URL_RE.sub(" ", text))
    current, original, unlabelled = set(), set(), set()
    for match in _PRICE_RE.finditer(clean):
        before = clean[max(0, match.start() - 45):match.start()]
        after = clean[match.end():match.end() + 30]
        if re.search(r"\d+\s*x\s*(?:de\s*)?$|\b(?:parcela(?:s)?|frete|economize|desconto de)\s*:?\s*$", before):
            continue
        if re.match(r"\s*(?:/\s*mes|por mes|mensais|de frete)\b", after):
            continue
        amount = Decimal((match.group("currency") or match.group("bare")).replace(".", "").replace(",", "."))
        if amount <= 0:
            continue
        if re.search(r"\b(?:de|antes|preco original)\s*:?\s*$", before):
            original.add(amount)
        elif re.search(r"\b(?:por|agora|por apenas|a vista|no pix)\s*:?\s*$", before) or re.match(r"\s*(?:no pix|a vista)\b", after):
            current.add(amount)
        else:
            unlabelled.add(amount)
    price = next(iter(current)) if len(current) == 1 else None
    if not current and len(unlabelled) == 1:
        price = next(iter(unlabelled))
    old_price = next(iter(original)) if len(original) == 1 else None
    if price is not None and old_price is not None and old_price <= price:
        old_price = None
    return price, old_price


def extract_coupon(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    coupons = set()
    for match in _COUPON_RE.finditer(text):
        code = match.group(1)
        if code.casefold() in {"cupom", "desconto", "para", "agora", "esse", "este", "aqui", "com", "ganhe"}:
            continue
        if any(char.isdigit() for char in code) or code.isupper():
            coupons.add(code)
    return next(iter(coupons)) if len(coupons) == 1 else None


def identify_component_type(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    plain = normalize_text(_URL_RE.sub(" ", text))
    patterns = {
        "gpu": r"\b(?:gpu|placa de video|rtx\s*\d{4}|rx\s*\d{4})\b",
        "cpu": r"\b(?:cpu|processador|ryzen|intel core)\b",
        "storage": r"\b(?:ssd|nvme)\b",
        "ram": r"\b(?:ram|memoria(?:s)?(?: ram)?)\b",
        "psu": r"\b(?:fonte|psu)\b",
        "motherboard": r"\b(?:placa[ -]mae|motherboard)\b",
        "case": r"\bgabinete\b",
        "cooler": r"\b(?:cooler|watercooler)\b",
    }
    found = [kind for kind, pattern in patterns.items() if re.search(pattern, plain)]
    return found[0] if len(found) == 1 else None


def parse_message(text: object, extra_urls=(), *, button_urls=(), entity_urls=(), sent_at=None) -> dict:
    extra_urls, button_urls, entity_urls = list(extra_urls or ()), list(button_urls or ()), list(entity_urls or ())
    visible_urls = extract_urls(text)
    urls = extract_urls(text, extra_urls + button_urls + entity_urls)
    price, original_price = extract_prices(text)
    store = identify_store(text, urls)
    url = select_offer_url(button_urls=button_urls, text_urls=extra_urls, visible_urls=visible_urls, other_urls=entity_urls)
    result = {
        "product": {"name": None, "normalized_key": None, "component_id": None, "component_type": identify_component_type(text)},
        "offer": {"store": store, "price": price, "original_price": original_price, "coupon": extract_coupon(text), "url": url,
                  "url_source": ('button' if url in button_urls else 'entity' if url in extra_urls + entity_urls else 'text') if url else None},
        "links": urls,
    }
    # Only explicit full dates are accepted; no guessed year or coupon duration.
    deadline = re.search(r'(?:v[aá]lid[oa](?:de)?\s*(?:ate|até|:)|expira\s*(?:em|:))\s*(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}))?', str(text), re.I)
    if deadline:
        try:
            value = datetime.strptime(deadline[1] + ' ' + (deadline[2] or '23:59'), '%d/%m/%Y %H:%M').replace(tzinfo=timezone(timedelta(hours=-3)))
            result['offer']['valid_until'] = value.isoformat()
        except ValueError:
            pass
    # Announced conditions (first purchase, app, PIX, minimum order, ...) and explicit validity; unknown stays None.
    conditions = extract_conditions(text, result['offer']['coupon'], sent_at)
    if any(value for key, value in conditions.items() if key != 'conditions_version'):
        result['offer']['conditions'] = conditions
    if conditions['valid_until'] and not result['offer'].get('valid_until'):
        result['offer']['valid_until'] = conditions['valid_until']
    return result
