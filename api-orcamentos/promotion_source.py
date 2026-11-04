"""Read-only access to already processed promotions. No Telegram API or writes."""

import os
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient
from pymongo.errors import PyMongoError


class PromotionSource:
    def __init__(self, collection=None):
        self.client = None
        if collection is None:
            self.client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"),
                                      serverSelectionTimeoutMS=1500, connectTimeoutMS=1500,
                                      socketTimeoutMS=2000, tz_aware=True)
            collection = self.client[os.getenv("MONGO_DB", "orcapc_catalog")]["telegram_promotions"]
        self.collection = collection

    def recent(self, now=None):
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=72)
        selector = {"status": {"$in": ["parsed", "matched", "verified", "published"]},
                    "is_demo": {"$ne": True}, "$or": [
                        {"telegram.sent_at": {"$gte": cutoff, "$lte": now}},
                        {"telegram.sent_at": None, "created_at": {"$gte": cutoff, "$lte": now}},
                    ]}
        projection = {"offer": 1, "product": 1, "raw_text": 1, "status": 1,
                      "created_at": 1, "telegram.sent_at": 1, "is_demo": 1}
        try:
            return list(self.collection.find(selector, projection).sort("created_at", -1).limit(200)), True
        except PyMongoError:
            return [], False  # Catalog-only advice remains available; do not log URI or raw error.

    def history(self, component_ids, now):
        try:
            selector = {'component_id': {'$in': component_ids}, 'match_level': 'high', 'verified': True,
                        'match_confidence': {'$gte': .85}, 'source': 'telegram'}
            projection = {'_id': 0, 'component_id': 1, 'date': 1, 'price': 1, 'source': 1,
                          'verified': 1, 'match_level': 1, 'match_confidence': 1}
            return list(self.collection.database.product_price_history.find(selector, projection).sort('date', -1).limit(2000))
        except PyMongoError:
            return []
