"""Matching determinístico, sem catálogo, chamadas HTTP ou classificação por IA."""

import re
from decimal import Decimal, InvalidOperation

from bson.decimal128 import Decimal128

from .filters import normalize_text
from .parser import identify_component_type
from services.product_matching.matcher import GPU as GPU_MODEL
from services.product_matching.normalization import BRANDS, normalize_store as catalog_store


IRRELEVANT = {"geforce", "placa", "de", "video", "processador"}
COMPONENT_TYPES = {"gpu", "cpu", "motherboard", "ram", "storage", "psu", "case", "cooler"}


def decimal_value(value) -> Decimal | None:
    try:
        amount = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
        return amount if amount.is_finite() and amount > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_terms(text: object) -> list[str]:
    if not isinstance(text, str):
        return []
    plain = normalize_text(re.sub(r"https?://\S+", " ", text))
    plain = GPU_MODEL.sub(lambda m: " ".join(filter(None, (m[1], m[2], (m[3] or "").replace(" ", "")))) + " ", plain)
    # ti super é uma variante composta; conservar seus dois termos.
    plain = re.sub(r"\btisuper\b", "ti super", plain)
    plain = re.sub(r"\b(\d+)\s+(gb|tb|mhz|w)\b", r"\1\2", plain)
    return [term for term in re.findall(r"[a-z0-9]+", plain) if term not in IRRELEVANT]


def gpu_models(text: str) -> set[tuple]:
    return {(m[1].lower(), m[2], re.sub(r"\s", "", (m[3] or "").lower())) for m in GPU_MODEL.finditer(normalize_text(text))}


def detect_component_type(text: str) -> str | None:
    plain = " ".join(normalize_terms(text))
    found = set()
    existing = identify_component_type(plain)
    if existing:
        found.add(existing)
    for kind, pattern in {
        "gpu": r"\b(?:rtx|gtx|rx)\s+\d{4}\b",
        "cpu": r"\b(?:core\s+i[3579]|\d{4}x3d|ryzen)\b",
        "motherboard": r"\b(?:[abx][45678]\d{2}[a-z]?|[bhz][4678]\d{2}[a-z]?)\b",
        "ram": r"\bddr[345]\b",
        "storage": r"\b(?:nvme|ssd|hdd)\b",
        "psu": r"\b\d{3,4}\s*w\b",
    }.items():
        if re.search(pattern, plain):
            found.add(kind)
    return next(iter(found)) if len(found) == 1 else None


def promotion_text(promotion: dict) -> str:
    product = promotion.get("product") or {}
    if product.get("name"):
        return product["name"]
    lines = [line for line in (promotion.get("raw_text") or "").splitlines() if not re.match(r"\s*(?:cupom\b|use\b|https?://)", line, re.I)]
    # Valores monetários e cupons não devem virar modelos por coincidência.
    text = re.sub(r"r\$\s*[\d.,]+", " ", "\n".join(lines), flags=re.I)
    return re.sub(r"\b\d+(?:\.\d{3})*,\d{2}\b", " ", text)


def has_phrase(text: str, phrase: str) -> bool:
    needle = normalize_terms(phrase)
    words = normalize_terms(text)
    return bool(needle) and any(words[i:i + len(needle)] == needle for i in range(len(words) - len(needle) + 1))


def normalize_store(value: str) -> str:
    return (catalog_store(value) or '').replace('_', '')


def discount_percent(promotion: dict) -> Decimal | None:
    offer = promotion.get("offer") or {}
    original = decimal_value(offer.get("original_price"))
    price = decimal_value(offer.get("price"))
    if original is None or price is None or original < price:
        return None
    return (original - price) / original * 100


def matches_alert(promotion: dict, alert: dict) -> bool:
    if not alert.get("enabled", False) or promotion.get("status") == "ignored":
        return False
    text = promotion_text(promotion)
    expected = normalize_terms(alert.get("query", ""))
    if not expected or not set(expected).issubset(set(normalize_terms(text))):
        return False
    models = gpu_models(alert.get("query", ""))
    if models and gpu_models(text) != models:
        return False
    if not models:
        variants = "".join(term for term in expected if term in {"ti", "super", "xt", "xtx"})
        if any(number in expected and suffix != variants for _, number, suffix in gpu_models(text)):
            return False
    offer = promotion.get("offer") or {}
    price = decimal_value(offer.get("price"))
    if price is None:
        return False
    if alert.get("max_price") is not None:
        maximum = decimal_value(alert["max_price"])
        if maximum is None or price > maximum:
            return False
    actual_type = (promotion.get("product") or {}).get("component_type") or detect_component_type(text.splitlines()[0] if text else "")
    if alert.get("component_type") and actual_type and alert["component_type"] != actual_type:
        return False
    if any(has_phrase(text, brand) for brand in alert.get("ignored_brands", [])):
        return False
    if alert.get("brands") and not any(has_phrase(text, brand) for brand in alert["brands"]):
        return False
    store = normalize_store(offer.get("store") or "")
    if store in {normalize_store(item) for item in alert.get("ignored_stores", [])}:
        return False
    if alert.get("stores") and store not in {normalize_store(item) for item in alert["stores"]}:
        return False
    minimum = alert.get("minimum_discount")
    if minimum is not None:
        threshold = minimum.to_decimal() if isinstance(minimum, Decimal128) else Decimal(str(minimum))
        discount = discount_percent(promotion)
        # Conforme a regra desta etapa, percentual só é aplicado quando os
        # dois preços estão disponíveis; não inferir desconto desconhecido.
        if discount is not None and discount < threshold:
            return False
    return True


def product_identity(promotion: dict) -> str | None:
    """Chave conservadora para reaproveitar equivalent_offer_key entre fontes."""
    text = promotion_text(promotion)
    models = gpu_models(text)
    brands = sorted(brand for brand in BRANDS if has_phrase(text, brand))
    capacities = sorted(set(re.findall(r"\b\d+\s*(?:gb|tb)\b", normalize_text(text))))
    if len(models) == 1:
        return "|".join([" ".join(next(iter(models))), *brands, *(re.sub(r"\s", "", item) for item in capacities)])
    cpu_models = re.findall(r"\b(?:\d{4}x3d|\d{4}[xg]|\d{5}[kf]{0,2})\b", normalize_text(text))
    if len(set(cpu_models)) == 1 and detect_component_type(text.splitlines()[0]) == "cpu":
        return "|".join([cpu_models[0], *brands])
    product = promotion.get('product') or {}
    if product.get('matcher_version') and product.get('match_level') != 'high':
        return None
    return product.get('normalized_key')
