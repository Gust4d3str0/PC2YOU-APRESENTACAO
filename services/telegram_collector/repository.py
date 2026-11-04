from datetime import datetime, timezone
from decimal import Decimal

from bson.decimal128 import Decimal128
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

from .deduplication import message_identity
from .links import extract_urls, valid_http_url
from services.product_matching.destinations import link_fields, resolve_redirects
from services.product_matching.promotions import enrich_promotion


def bson_values(value):
    if isinstance(value, Decimal):
        return Decimal128(value)
    if isinstance(value, dict):
        return {key: bson_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [bson_values(item) for item in value]
    return value


class PromotionRepository:
    def __init__(self, database):
        self.database = database
        self.promotions = database["telegram_promotions"]
        self.service_status = database["telegram_service_status"]

    def ensure_indexes(self):
        self.promotions.create_index(
            [("telegram.chat_id", ASCENDING), ("telegram.message_id", ASCENDING)],
            unique=True, name="uq_telegram_chat_message",
        )

    def save(self, document: dict) -> bool:
        document = enrich_promotion(document, list(self.database['components'].find({}, {'_id': 0})))
        document.pop('evaluation', None)  # status is derived at read time and must not be frozen in the database
        identity = message_identity(document["telegram"]["chat_id"], document["telegram"]["message_id"])
        try:
            result = self.promotions.update_one(identity, {"$setOnInsert": bson_values(document)}, upsert=True)
        except DuplicateKeyError:
            # Dois processos podem observar a ausência ao mesmo tempo.
            if self.promotions.find_one(identity, {"_id": 1}) is None:
                raise
            self._complete_links(identity, document)
            return False
        if result.upserted_id is not None:
            self._save_observation(document)
            return True
        self._complete_links(identity, document)
        return False

    def _complete_links(self, identity: dict, document: dict):
        """Backfill URL only; keep parsing, timestamps and notification state intact."""
        incoming = valid_http_url((document.get("offer") or {}).get("url"))
        links = extract_urls("", (document.get("links") or []) + [incoming])
        existing = self.promotions.find_one(identity, {"offer.url": 1})
        if existing is None:
            return
        previous = (existing.get("offer") or {}).get("url")
        previous_valid = valid_http_url(previous)
        if previous_valid and previous_valid not in links:
            links.append(previous_valid)
        if links:
            self.promotions.update_one(identity, {"$addToSet": {"links": {"$each": links}}})
        if incoming and not previous_valid:
            # Compare-and-set prevents two reimports from overwriting a URL filled
            # concurrently, while $addToSet above preserves all discovered links.
            self.promotions.update_one(
                {**identity, "offer.url": previous}, {"$set": {"offer.url": incoming}},
            )
            if (document.get('offer') or {}).get('url_source'):
                self.promotions.update_one({**identity, 'offer.url': incoming},
                                          {'$set': {'offer.url_source': document['offer']['url_source']}})
        # Reevaluate the persisted price/text rather than overwriting them with a new parse.
        self.refresh_quality(identity)

    def resolve_link(self, identity: dict, resolver=resolve_redirects, force: bool = False):
        """Follow HTTP redirects of `offer.url` and store the result beside it; `offer.url` is never replaced."""
        document = self.promotions.find_one(identity, {'offer.url': 1, 'offer.link_checked_at': 1})
        url = valid_http_url(((document or {}).get('offer') or {}).get('url'))
        if not url or (not force and (document['offer'].get('link_checked_at'))):
            return None
        fields = link_fields(url, resolver(url), datetime.now(timezone.utc).isoformat())
        updated = self.promotions.update_one({**identity, 'offer.url': url},
                                             {'$set': {f'offer.{k}': v for k, v in fields.items()}})
        return fields if updated.matched_count else None

    def _save_observation(self, document):
        observation = document.get('price_observation')
        key = {'telegram.chat_id': document['telegram']['chat_id'], 'telegram.message_id': document['telegram']['message_id']}
        history = self.database['product_price_history']
        if observation:
            # One observation per message; an identical offer already seen the same day is not duplicated.
            if history.find_one(key) is None and observation.get('equivalence_key') and self._seen_same_day(history, observation):
                return
            history.update_one(key, {'$set': bson_values(observation)}, upsert=True)
        else:
            # Keep the prior observation for audit, but revoke its automatic use.
            self.database['product_price_history'].update_one(key, {'$set': {'verified': False, 'invalidated_by': 'current_product_match'}})

    @staticmethod
    def _seen_same_day(history, observation):
        day = str(observation.get('date') or '')[:10]
        return bool(day) and history.find_one({'equivalence_key': observation['equivalence_key'], 'verified': True,
                                               'date': {'$regex': '^' + day}}) is not None

    def refresh_quality(self, identity):
        previous = self.promotions.find_one(identity)
        if previous is None:
            return
        document = enrich_promotion(previous, list(self.database['components'].find({}, {'_id': 0})))
        updates = {f'product.{k}': v for k, v in document['product'].items() if k not in {'name', 'component_type', 'brand'}}
        updates.update({f'offer.{k}': v for k, v in document['offer'].items()
                        if k in {'source', 'verified', 'state', 'coupon_status', 'product_match_confidence', 'product_match_level', 'captured_at',
                                 'url_valid', 'url_source', 'store_key', 'matcher_version'}})
        updates.update({k: document[k] for k in ('equivalence_key', 'price_observation')})
        updates = {k: v for k, v in updates.items() if self._field(previous, k) != v}
        if updates:
            updated = self.promotions.update_one({'_id': previous['_id'], 'raw_text': previous.get('raw_text'),
                                                 'offer.price': (previous.get('offer') or {}).get('price'),
                                                 'offer.url': (previous.get('offer') or {}).get('url')},
                                                {'$set': bson_values(updates)})
            if not updated.matched_count:
                return None
        self._save_observation(document)
        return document

    @staticmethod
    def _field(document, path):
        value = document
        for part in path.split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        return value

    def heartbeat(self, source_count: int, *, connected: bool = True):
        self.service_status.update_one(
            {"_id": "collector"},
            {"$set": {"connected": connected, "source_count": source_count, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    def summary(self) -> dict:
        self.database.command("ping")
        count = self.promotions.count_documents({})
        state = self.service_status.find_one({"_id": "collector"}) or {}
        updated = state.get("updated_at")
        if updated is not None and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - updated).total_seconds() if updated else None
        return {
            "promotions": count,
            "collector_online": bool(state.get("connected") and age is not None and 0 <= age < 120),
            "collector_sources": state.get("source_count", 0),
        }


def open_repository(settings):
    # Mesmo servidor/banco do catálogo, sem importar inicialização/JWT das APIs.
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=5000, tz_aware=True)
    try:
        client.admin.command("ping")
        repository = PromotionRepository(client[settings.mongo_db])
        return client, repository
    except Exception:
        client.close()
        raise
