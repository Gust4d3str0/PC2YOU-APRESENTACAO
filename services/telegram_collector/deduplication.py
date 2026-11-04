import hashlib
import json
from decimal import Decimal, InvalidOperation

from .filters import normalize_text


def message_identity(chat_id: int, message_id: int) -> dict:
    if chat_id >= 0 or message_id <= 0:
        raise ValueError("Identidade de mensagem de grupo/canal inválida.")
    return {"telegram.chat_id": chat_id, "telegram.message_id": message_id}


def equivalent_offer_key(product_key, price, store, coupon=None) -> str | None:
    """Calcula a identidade; a janela e a supressão são controladas pelo notifier."""
    if not product_key or price is None or not store:
        return None
    try:
        amount = Decimal(str(price)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    payload = [normalize_text(str(product_key)).strip(), str(amount), normalize_text(str(store)).strip(), str(coupon or "").casefold().strip()]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()
