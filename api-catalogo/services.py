import sys
from pathlib import Path

_shared = Path(__file__).resolve().parents[1] / 'services'
if _shared.is_dir():
    sys.path.append(str(_shared))
from product_matching.quality import catalog_offers, best_known_price, history_observation
from catalog_specs.external_identity import search_metadata
from catalog_specs.human_input import human_keys

import re

from pymongo.collection import Collection


def _telegram_prices(database, component_id: str) -> list[dict]:
    """Current, eligible Telegram offers as price rows. Announced prices: coupon/conditions are carried, never hidden."""
    if database is None:
        return []
    import commerce
    try:
        rows = commerce.best_candidates(commerce.snapshot(database)['offers'].get(component_id, []))
    except Exception:  # commercial read model must never break the technical catalog
        return []
    return [{'store': r['store'] or 'Loja não identificada', 'price': r['price'], 'url': r['url'], 'last_update': r['captured_at'] or '',
             'source': 'telegram', 'availability': 'Disponível', 'coupon': r['coupon'], 'conditional': r['is_conditional'],
             'status': r['status'], 'condition_labels': r['condition_labels'], 'offer_id': r['id'],
             'quality': {'source': 'telegram', 'verified': True, 'state': 'active', 'product_match_level': 'high'}}
            for r in rows if r['source'] == 'telegram']


def real_price_history(database, document: dict) -> list[dict]:
    """Daily min/avg/max of real observations (verified Telegram offers) plus non-seed legacy snapshots. Never synthetic."""
    days: dict[str, list[float]] = {}
    if database is not None:
        for row in database['product_price_history'].find({'component_id': document.get('id'), 'verified': True}):
            price, day = row.get('price'), str(row.get('date') or '')[:10]
            if day and isinstance(price, (int, float)) and price > 0:
                days.setdefault(day, []).append(float(price))
    history = [{'date': day, 'min_price': min(v), 'max_price': max(v), 'average_price': round(sum(v) / len(v), 2),
                'source': 'telegram', 'observations': len(v)} for day, v in days.items()]
    history += [h for h in document.get('price_history') or [] if isinstance(h, dict) and h.get('source', 'seed') != 'seed']
    return sorted(history, key=lambda h: str(h.get('date')))


def _public_component(document: dict | None, database=None):
    """Technical component + only real commercial data. Seed prices/history are legacy and never shown as current."""
    if not document:
        return None
    document.pop("_id", None)
    qualified = catalog_offers(document)
    real = [p for p in qualified if p['quality']['verified'] and p['quality']['source'] != 'seed']
    document['prices'] = real + _telegram_prices(database, document.get('id'))
    document['unverified_prices'] = [p for p in qualified if not p['quality']['verified'] and p['quality']['source'] != 'seed']
    document['price_history'] = real_price_history(database, document)
    return document


def create_component(collection: Collection, component: dict):
    component.update(search_metadata(component))
    component['human_lookup_keys'] = human_keys(component)
    collection.insert_one(component)
    collection.database.catalog_human_index_meta.update_one({'_id': 'active'}, {'$set': {'valid': False}}, upsert=True)
    return component


# Fields the technical consumers (AI analysis) need. No commercial or history data.
TECHNICAL_PROJECTION = {'_id': 0, 'id': 1, 'name': 1, 'category': 1, 'brand': 1, 'technical_specs': 1,
                        'compatibility': 1, 'benchmark': 1, 'identity_scope': 1, 'aliases': 1, 'mpn': 1,
                        'model': 1, 'normalized_name': 1, 'normalized_identity': 1, 'identity_variant': 1}


def _technical_component(document: dict) -> dict:
    """Light view: no Telegram snapshot and no price-history lookups."""
    document.pop('_id', None)
    document['prices'] = []
    document['unverified_prices'] = []
    document['price_history'] = []
    return document


def list_components(
    collection: Collection,
    category: str | None = None,
    q: str | None = None,
    brand: str | None = None,
    skip: int = 0,
    limit: int | None = None,
    technical_only: bool = False,
):
    query: dict = {}
    if category:
        query["category"] = category
    if brand:
        query["brand"] = {"$regex": re.escape(brand), "$options": "i"}
    if q:
        escaped_query = re.escape(q)
        query["$or"] = [
            {"name": {"$regex": escaped_query, "$options": "i"}},
            {"brand": {"$regex": escaped_query, "$options": "i"}},
            {"description": {"$regex": escaped_query, "$options": "i"}},
        ]

    cursor = collection.find(query, TECHNICAL_PROJECTION if technical_only else None).sort("category", 1).skip(skip)
    if limit is not None:
        cursor = cursor.limit(limit)
    if technical_only:
        return [_technical_component(doc) for doc in cursor]
    return [_public_component(doc, collection.database) for doc in cursor]


def get_components_batch(collection: Collection, component_ids: list[str]):
    documents = collection.find({"id": {"$in": component_ids}})
    by_id = {document["id"]: _public_component(document, collection.database) for document in documents}
    return [by_id[component_id] for component_id in component_ids if component_id in by_id]


def get_component(collection: Collection, component_id: str):
    return _public_component(collection.find_one({"id": component_id}), collection.database)


def update_component(collection: Collection, component_id: str, data: dict):
    current = collection.find_one({'id': component_id})
    identity_changed = bool(set(data) & {'name','category','brand','technical_specs','compatibility','aliases','mpn','identity_scope','identity_variant'})
    if current is not None and identity_changed:
        prospective = {**current, **data}
        data = {**data, **search_metadata(prospective), 'human_lookup_keys': human_keys(prospective)}
    collection.update_one({"id": component_id}, {"$set": data})
    if current is not None and identity_changed:
        collection.database.catalog_human_index_meta.update_one({'_id': 'active'}, {'$set': {'valid': False}}, upsert=True)
    return get_component(collection, component_id)


def delete_component(collection: Collection, component_id: str):
    component = get_component(collection, component_id)
    if not component:
        return None
    collection.delete_one({"id": component_id})
    collection.database.catalog_human_index_meta.update_one({'_id': 'active'}, {'$set': {'valid': False}}, upsert=True)
    return component


def _real_prices(component: dict) -> list[dict]:
    """Non-seed, verified price rows. Stored scores are never trusted: marketplace rows are re-qualified here;
    Telegram rows are only the ones `_public_component` built from the commercial read model."""
    rows = [p for p in component.get('prices') or [] if isinstance(p, dict)]
    telegram = [p for p in rows if p.get('source') == 'telegram' and p.get('offer_id')]
    others = {**component, 'prices': [p for p in rows if not any(p is t for t in telegram)]}
    real = [p for p in catalog_offers(others) if p['quality']['verified'] and p['quality']['source'] != 'seed']
    return real + telegram


def best_price(component: dict):
    """Best real price: unconditional offers first; a conditional one only when nothing else exists."""
    rows = _real_prices(component)
    general = [p for p in rows if not p.get('conditional') and not p.get('coupon')]
    pool = general or rows
    return min(pool, key=lambda p: p['price']) if pool else None


def _valid_prices(prices: list[dict]) -> list[dict]:
    valid = []
    for item in prices or []:
        price = item.get("price")
        if isinstance(price, (int, float)) and price >= 0:
            valid.append({**item, "price": float(price)})
    return valid


def _offer_payload(offer: dict | None) -> dict | None:
    if not offer:
        return None
    payload = dict(offer)
    if "url" in payload:
        payload["url"] = str(payload["url"])
    return payload


def _price_stats(prices: list[dict]) -> dict:
    if not prices:
        return {
            "min_price": None,
            "max_price": None,
            "average_price": None,
            "offers_count": 0,
            "best_offer": None,
            "highest_offer": None,
        }

    sorted_prices = sorted(prices, key=lambda p: p["price"])
    values = [p["price"] for p in sorted_prices]
    return {
        "min_price": sorted_prices[0]["price"],
        "max_price": sorted_prices[-1]["price"],
        "average_price": round(sum(values) / len(values), 2),
        "offers_count": len(sorted_prices),
        "best_offer": _offer_payload(sorted_prices[0]),
        "highest_offer": _offer_payload(sorted_prices[-1]),
    }


def price_summary(component: dict) -> dict:
    prices = _real_prices(component)
    if not prices:
        return {
            "component_id": component.get("id"),
            "min_price": None,
            "max_price": None,
            "average_price": None,
            "price_range": None,
            "variation_percent": None,
            "offers_count": 0,
            "real_prices_count": 0,
            "seed_prices_count": 0,
            "real_min_price": None,
            "real_max_price": None,
            "real_average_price": None,
            "real_offers_count": 0,
            "real_best_offer": None,
            "real_highest_offer": None,
            "seed_min_price": None,
            "seed_max_price": None,
            "seed_average_price": None,
            "best_offer": None,
            "highest_offer": None,
            "last_update": None,
            "sources": [],
            "all_offers": [],
        }

    sorted_prices = sorted(prices, key=lambda p: p["price"])
    all_prices = [p["price"] for p in prices]
    real_prices = [p for p in prices if p["quality"]["verified"]]
    seed_prices = [p for p in prices if p.get("source", "seed") == "seed"]
    real_stats = _price_stats(real_prices)
    seed_stats = _price_stats(seed_prices)
    min_price = sorted_prices[0]["price"]
    max_price = sorted_prices[-1]["price"]
    average_price = round(sum(all_prices) / len(all_prices), 2)
    price_range = round(max_price - min_price, 2)
    variation_percent = round((price_range / min_price) * 100, 2) if min_price else 0
    sources = sorted({p.get("source", "seed") for p in prices if p.get("source", "seed")})
    last_update = max((p.get("last_update", "") for p in prices if p.get("last_update")), default=None)

    return {
        "component_id": component.get("id"),
        "min_price": min_price,
        "max_price": max_price,
        "average_price": average_price,
        "price_range": price_range,
        "variation_percent": variation_percent,
        "offers_count": len(prices),
        "real_prices_count": real_stats["offers_count"],
        "seed_prices_count": seed_stats["offers_count"],
        "real_min_price": real_stats["min_price"],
        "real_max_price": real_stats["max_price"],
        "real_average_price": real_stats["average_price"],
        "real_offers_count": real_stats["offers_count"],
        "real_best_offer": real_stats["best_offer"],
        "real_highest_offer": real_stats["highest_offer"],
        "seed_min_price": seed_stats["min_price"],
        "seed_max_price": seed_stats["max_price"],
        "seed_average_price": seed_stats["average_price"],
        "best_offer": _offer_payload(sorted_prices[0]),
        "highest_offer": _offer_payload(sorted_prices[-1]),
        "last_update": last_update,
        "sources": sources,
        "all_offers": [_offer_payload(price) for price in sorted_prices],
    }


def build_price_snapshot(
    component: dict,
    date_value: str | None = None,
    external_status: str | None = None,
) -> dict | None:
    summary = price_summary(component)
    if not summary["offers_count"]:
        return None

    snapshot = {
        "date": date_value or summary.get("last_update"),
        "min_price": summary["min_price"],
        "max_price": summary["max_price"],
        "average_price": summary["average_price"],
        "offers_count": summary["offers_count"],
        "best_store": summary["best_offer"].get("store") if summary["best_offer"] else None,
        "highest_store": summary["highest_offer"].get("store") if summary["highest_offer"] else None,
        "sources": summary["sources"],
        "real_prices_count": summary["real_prices_count"],
        'observations': [o for p in catalog_offers(component)
                         if (o := history_observation(component.get('id'), p, p['quality']))],
    }
    if external_status:
        snapshot["external_status"] = external_status
    return snapshot


def _snapshot_bucket(snapshot: dict) -> str:
    date_value = str(snapshot.get("date", ""))
    if "T" in date_value:
        return date_value[:16]
    return date_value


def upsert_price_snapshot(history: list[dict], snapshot: dict | None) -> list[dict]:
    if not snapshot:
        return history or []

    next_history = list(history or [])
    bucket = _snapshot_bucket(snapshot)
    for index in range(len(next_history) - 1, -1, -1):
        if _snapshot_bucket(next_history[index]) == bucket:
            next_history[index] = snapshot
            return next_history

    next_history.append(snapshot)
    return next_history
