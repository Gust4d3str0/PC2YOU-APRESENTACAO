"""Worker desacoplado do Telethon, com estado e reservas persistidos no MongoDB."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, RetryAfter

from services.telegram_collector.deduplication import equivalent_offer_key
from services.telegram_collector.matcher import decimal_value, discount_percent, matches_alert, product_identity
from services.telegram_collector.parser import extract_urls
from .alerts import format_money
from services.product_matching.quality import offer_state


logger = logging.getLogger("pc2you.telegram")
TERMINAL = {"sent", "skipped_equivalent", "rejected", "uncertain", "cancelled"}


def notification_text(promotion: dict, alert: dict) -> str:
    offer = promotion.get("offer") or {}
    title = promotion.get("product", {}).get("name") or next((line.strip() for line in promotion.get("raw_text", "").splitlines() if line.strip()), alert["query"])
    lines = ["🚨 PC2YOU — OFERTA ENCONTRADA", "", title[:180], ""]
    if decimal_value(offer.get("original_price")) is not None:
        lines.extend(["De " + format_money(offer["original_price"]), "🔥 Por " + format_money(offer.get("price"))])
    else:
        lines.append("🔥 " + format_money(offer.get("price")))
    discount = discount_percent(promotion)
    if discount is not None:
        lines.append(f"📉 {discount:.2f}% de desconto".replace(".", ","))
    lines.extend(["Seu limite: " + format_money(alert.get("max_price")), "🏪 " + (offer.get("store") or "Loja não identificada")])
    if offer.get("coupon"):
        lines.extend(["🎟 Cupom anunciado:", str(offer["coupon"])[:80]])
    maximum = decimal_value(alert.get("max_price"))
    price = decimal_value(offer.get("price"))
    if maximum is not None and price is not None:
        lines.append("💰 " + format_money(maximum - price) + " abaixo do seu limite")
    return "\n".join(lines)


def notification_buttons(promotion: dict, alert_id, history_id):
    offer = promotion.get("offer") or {}
    links = extract_urls("", [offer.get("url")])
    rows = [[InlineKeyboardButton("🛒 Abrir oferta", url=links[0])]] if links else []
    rows.append([InlineKeyboardButton("❌ Ignorar", callback_data=f"pc2:ignore:{history_id}"), InlineKeyboardButton("🔕 Pausar alerta", callback_data=f"pc2:pause:{alert_id}")])
    return InlineKeyboardMarkup(rows)


class NotificationWorker:
    def __init__(self, repository, bot, settings, *, clock=None):
        self.repo = repository
        self.bot = bot
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.initial_started_at = self.clock()
        self.rate_limited = False

    def bootstrap(self):
        self.repo.ensure_indexes()
        # O marco é escrito uma vez. Reinícios conservam a janela de pendências.
        return self.repo.state.find_one_and_update(
            {"_id": "worker"}, {"$setOnInsert": {"started_at": self.initial_started_at}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )["started_at"]

    def claim(self, alert, promotion):
        now = self.clock()
        identity = {"telegram_user_id": alert["telegram_user_id"], "alert_id": alert["_id"], "promotion_id": promotion["_id"]}
        token = uuid4().hex
        row = {**identity, "status": "sending", "claim_id": token, "lease_until": now + timedelta(minutes=2), "created_at": now, "sent_at": None}
        try:
            row["_id"] = self.repo.history.insert_one(row).inserted_id
            return row
        except DuplicateKeyError:
            existing = self.repo.history.find_one(identity)
            if existing["status"] in TERMINAL:
                return True
            if existing["status"] == "sending":
                if existing["lease_until"] <= now:
                    # Não há chave de idempotência na Bot API: envio pode ter
                    # ocorrido antes da queda. Evitar reenvio silencioso.
                    self.repo.history.update_one({"_id": existing["_id"], "claim_id": existing["claim_id"], "status": "sending"}, {"$set": {"status": "uncertain", "finished_at": now}})
                    return True
                return None
            return self.repo.history.find_one_and_update(
                {**identity, "status": "failed", "retry_at": {"$lte": now}},
                {"$set": {"status": "sending", "claim_id": token, "lease_until": row["lease_until"]}},
                return_document=ReturnDocument.AFTER,
            )

    def finish(self, row, status, **extra):
        self.repo.history.update_one(
            {"_id": row["_id"], "claim_id": row["claim_id"]},
            {"$set": {"status": status, "finished_at": self.clock(), **extra}},
        )

    def reserve_equivalent(self, row, key):
        if key is None:
            return True
        now = self.clock()
        identity = f"{row['telegram_user_id']}:{row['alert_id']}:{key}"
        try:
            self.repo.dedup.find_one_and_update(
                {"_id": identity, "$or": [{"expires_at": {"$lte": now}}, {"claim_id": row["claim_id"]}]},
                {"$set": {"claim_id": row["claim_id"], "status": "sending", "lease_until": now + timedelta(minutes=2), "expires_at": now + timedelta(hours=self.settings.alert_dedup_hours)}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            return True
        except DuplicateKeyError:
            previous = self.repo.dedup.find_one({"_id": identity})
            if previous is None:
                return "pending"
            return "pending" if previous and previous["status"] == "sending" and previous.get("lease_until", now) > now else False

    def update_equivalent(self, row, key, status):
        if key is None:
            return
        identity = f"{row['telegram_user_id']}:{row['alert_id']}:{key}"
        selector = {"_id": identity, "claim_id": row["claim_id"]}
        if status == "failed":
            self.repo.dedup.delete_one(selector)
        else:
            self.repo.dedup.update_one(selector, {"$set": {"status": status, "expires_at": self.clock() + timedelta(hours=self.settings.alert_dedup_hours)}})

    async def deliver(self, promotion, alert):
        captured = (promotion.get('telegram') or {}).get('sent_at') or promotion.get('created_at')
        if offer_state(promotion.get('offer') or {}, now=self.clock(), captured_at=captured, source='telegram') == 'expired':
            return True
        row = await asyncio.to_thread(self.claim, alert, promotion)
        if row is True:
            return True
        if row is None:
            return False
        current = await asyncio.to_thread(self.repo.get_owned, alert["telegram_user_id"], alert["_id"])
        if current is None or not matches_alert(promotion, current):
            await asyncio.to_thread(self.finish, row, "cancelled")
            return True
        offer = promotion.get("offer") or {}
        key = equivalent_offer_key(product_identity(promotion), decimal_value(offer.get("price")), offer.get("store"), offer.get("coupon"))
        reserved = await asyncio.to_thread(self.reserve_equivalent, row, key)
        if reserved == "pending":
            await asyncio.to_thread(self.finish, row, "failed", retry_at=self.clock() + timedelta(seconds=self.settings.notification_poll_seconds))
            return False
        if reserved is False:
            await asyncio.to_thread(self.finish, row, "skipped_equivalent")
            logger.info("[Notifier] Oferta equivalente já enviada; ignorando")
            return True
        try:
            sent = await self.bot.send_message(
                chat_id=alert["telegram_user_id"], text=notification_text(promotion, current),
                reply_markup=notification_buttons(promotion, alert["_id"], row["_id"]),
            )
        except RetryAfter as exc:
            retry_after = exc.retry_after
            delay = retry_after.total_seconds() if hasattr(retry_after, "total_seconds") else float(retry_after)
            retry_at = self.clock() + timedelta(seconds=max(delay, self.settings.notification_poll_seconds))
            await asyncio.to_thread(self.update_equivalent, row, key, "failed")
            await asyncio.to_thread(self.finish, row, "failed", retry_at=retry_at)
            await asyncio.to_thread(self.repo.state.update_one, {"_id": "worker"}, {"$set": {"next_send_at": retry_at}})
            self.rate_limited = True
            logger.warning("[Notifier] Telegram limitou o envio; nova tentativa agendada")
            return False
        except (Forbidden, BadRequest) as exc:
            await asyncio.to_thread(self.update_equivalent, row, key, "failed")
            await asyncio.to_thread(self.finish, row, "rejected", error_type=type(exc).__name__)
            logger.warning("[Notifier] Envio rejeitado (%s)", type(exc).__name__)
            return True
        except Exception as exc:
            # Timeout/conexão podem ocorrer depois da aceitação pelo Telegram.
            await asyncio.to_thread(self.update_equivalent, row, key, "uncertain")
            await asyncio.to_thread(self.finish, row, "uncertain", error_type=type(exc).__name__)
            logger.error("[Notifier] Entrega incerta; não reenviar automaticamente (%s)", type(exc).__name__)
            return True
        await asyncio.to_thread(self.update_equivalent, row, key, "sent")
        await asyncio.to_thread(self.finish, row, "sent", sent_at=self.clock(), telegram_message_id=sent.message_id)
        logger.info("[Notifier] Notificação enviada")
        return True

    async def run_once(self):
        start = await asyncio.to_thread(self.bootstrap)
        now = self.clock()
        state = await asyncio.to_thread(self.repo.state.find_one, {"_id": "worker"})
        if state.get("next_send_at") and state["next_send_at"] > now:
            return 0
        self.rate_limited = False
        selector = {"created_at": {"$gte": start}, "notifications_processed_at": {"$exists": False}, "$or": [{"notification_retry_at": {"$exists": False}}, {"notification_retry_at": {"$lte": now}}]}
        promotions = await asyncio.to_thread(lambda: list(self.repo.promotions.find(selector).sort([("created_at", 1), ("_id", 1)]).limit(100)))
        for promotion in promotions:
            alert_selector = {"enabled": True, "created_at": {"$lte": promotion["created_at"]}}
            if self.settings.allowed_users:
                alert_selector["telegram_user_id"] = {"$in": list(self.settings.allowed_users)}
            alerts = await asyncio.to_thread(lambda: list(self.repo.alerts.find(alert_selector)))
            complete = True
            for alert in alerts:
                if matches_alert(promotion, alert):
                    logger.info("[Matcher] Promoção corresponde ao alerta %s", alert["_id"])
                    complete = await self.deliver(promotion, alert) and complete
                    if self.rate_limited:
                        break
            field = "notifications_processed_at" if complete else "notification_retry_at"
            value = self.clock() if complete else self.clock() + timedelta(seconds=self.settings.notification_poll_seconds)
            await asyncio.to_thread(self.repo.promotions.update_one, {"_id": promotion["_id"]}, {"$set": {field: value}})
            if self.rate_limited:
                break
        return len(promotions)

    async def run_forever(self):
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                logger.error("[Notifier] Ciclo interrompido; pendências preservadas (%s)", type(exc).__name__)
            await asyncio.sleep(self.settings.notification_poll_seconds)
