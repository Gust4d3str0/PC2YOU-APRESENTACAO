import re
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from services.telegram_collector.matcher import COMPONENT_TYPES, normalize_terms
from services.telegram_collector.models import PriceAlert
from services.telegram_collector.repository import bson_values


def parse_max_price(text: str) -> Decimal | None:
    value = text.strip()
    if value.casefold() in {"sem limite", "qualquer", "-"}:
        return None
    value = re.sub(r"^r\$\s*", "", value, flags=re.I)
    if not re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?", value):
        raise ValueError("Informe um preço válido, como 3800 ou R$ 3.800,00.")
    try:
        amount = Decimal(value.replace(".", "").replace(",", "."))
        if not amount.is_finite() or not Decimal("0") < amount <= Decimal("999999999.99"):
            raise ValueError
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("O preço deve ser positivo e menor que um bilhão de reais.") from None


def format_money(value) -> str:
    if value is None:
        return "sem limite"
    if hasattr(value, "to_decimal"):
        value = value.to_decimal()
    return "R$ " + f"{Decimal(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def validate_alert(values: dict) -> dict:
    query = values.get("query", "").strip()
    terms = normalize_terms(query)
    if not terms or len(query) > 120 or "\n" in query:
        raise ValueError("Informe um modelo em uma linha, com até 120 caracteres.")
    maximum = values.get("max_price")
    if maximum is not None:
        if hasattr(maximum, "to_decimal"):
            maximum = maximum.to_decimal()
        # Entrada interna usa Decimal; texto da conversa usa parse_max_price.
        maximum = Decimal(str(maximum))
        if not maximum.is_finite() or not 0 < maximum <= Decimal("999999999.99"):
            raise ValueError("Preço máximo inválido.")
        maximum = maximum.quantize(Decimal("0.01"))
    component_type = values.get("component_type")
    if component_type is not None and component_type not in COMPONENT_TYPES:
        raise ValueError("Tipo de componente inválido.")
    cleaned = {"query": query, "normalized_terms": terms, "component_type": component_type, "max_price": maximum, "enabled": bool(values.get("enabled", True))}
    for field in ("brands", "ignored_brands", "stores", "ignored_stores"):
        items = values.get(field, [])
        if not isinstance(items, list) or len(items) > 20 or any(not isinstance(item, str) or not item.strip() or len(item) > 40 for item in items):
            raise ValueError("Use até 20 filtros, com até 40 caracteres cada.")
        cleaned[field] = list(dict.fromkeys(item.strip() for item in items))
    discount = values.get("minimum_discount")
    if discount is not None:
        discount = discount.to_decimal() if hasattr(discount, "to_decimal") else Decimal(str(discount))
        if not discount.is_finite() or not 0 <= discount <= 100:
            raise ValueError("Desconto mínimo deve estar entre 0 e 100.")
    cleaned["minimum_discount"] = discount
    return cleaned


class AlertRepository:
    def __init__(self, database):
        self.database = database
        self.alerts = database["price_alerts"]
        self.promotions = database["telegram_promotions"]
        self.history = database["notification_history"]
        self.dedup = database["notification_dedup"]
        self.state = database["telegram_notification_state"]

    def ensure_indexes(self):
        self.alerts.create_index([("telegram_user_id", ASCENDING), ("created_at", ASCENDING)], name="ix_alert_user_created")
        self.alerts.create_index([("enabled", ASCENDING), ("created_at", ASCENDING)], name="ix_alert_enabled_created")
        self.history.create_index([("telegram_user_id", 1), ("alert_id", 1), ("promotion_id", 1)], unique=True, name="uq_notification_user_alert_promotion")
        self.promotions.create_index([("created_at", 1), ("notifications_processed_at", 1)], name="ix_promotion_notifications")
        self.dedup.create_index("expires_at", expireAfterSeconds=0, name="ttl_equivalent_offer")

    def create(self, user_id: int, values: dict, *, creation_id=None) -> dict:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("ID Telegram inválido.")
        now = datetime.now(timezone.utc)
        payload = validate_alert(values)
        document = asdict(PriceAlert(telegram_user_id=user_id, created_at=now, updated_at=now, **payload))
        document = bson_values(document)
        if creation_id is not None:
            # Token estável do cadastro evita criar dois alertas caso o banco
            # tenha aceitado a escrita antes de um timeout da confirmação.
            identity = ObjectId(str(creation_id))
            header = {"created_at": document.pop("created_at"), "telegram_user_id": user_id, "user_id": document.pop("user_id")}
            document.pop("telegram_user_id")
            return self.alerts.find_one_and_update(
                {"_id": identity, "telegram_user_id": user_id},
                {"$setOnInsert": header, "$set": document},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
        document["_id"] = self.alerts.insert_one(document).inserted_id
        return document

    def list_owned(self, user_id: int, offset=0, limit=10):
        return list(self.alerts.find({"telegram_user_id": user_id}).sort([("created_at", 1), ("_id", 1)]).skip(offset).limit(limit))

    def get_owned(self, user_id: int, alert_id):
        try:
            identity = ObjectId(str(alert_id))
        except Exception:
            return None
        return self.alerts.find_one({"_id": identity, "telegram_user_id": user_id})

    def update(self, user_id: int, alert_id, values: dict) -> bool:
        current = self.get_owned(user_id, alert_id)
        if current is None:
            return False
        payload = bson_values(validate_alert(values))
        payload["updated_at"] = datetime.now(timezone.utc)
        return bool(self.alerts.update_one({"_id": current["_id"], "telegram_user_id": user_id}, {"$set": payload}).matched_count)

    def set_enabled(self, user_id: int, alert_id, enabled: bool) -> bool:
        current = self.get_owned(user_id, alert_id)
        if current is None:
            return False
        return bool(self.alerts.update_one({"_id": current["_id"], "telegram_user_id": user_id}, {"$set": {"enabled": enabled, "updated_at": datetime.now(timezone.utc)}}).matched_count)

    def remove(self, user_id: int, alert_id) -> bool:
        current = self.get_owned(user_id, alert_id)
        return bool(current and self.alerts.delete_one({"_id": current["_id"], "telegram_user_id": user_id}).deleted_count)

    def recent_for_user(self, user_id: int, limit=10):
        from services.telegram_collector.matcher import matches_alert

        alerts = list(self.alerts.find({"telegram_user_id": user_id, "enabled": True}))
        if not alerts:
            return []
        dismissed = [row["promotion_id"] for row in self.history.find({"telegram_user_id": user_id, "dismissed": True}, {"promotion_id": 1})]
        result = []
        # Janela limitada explicitamente para impedir varredura ilimitada por comando.
        for promotion in self.promotions.find({"_id": {"$nin": dismissed}}).sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(1000):
            if any(matches_alert(promotion, alert) for alert in alerts):
                result.append(promotion)
                if len(result) == limit:
                    break
        return result
