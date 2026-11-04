"""Public commerce read model: persisted evidence only, no provider calls or writes."""
from datetime import datetime, timedelta, timezone
from threading import Lock
import time
from urllib.parse import urlsplit

from product_matching import CatalogMatcher
from product_matching.destinations import choose_url, classify_url, kind_rank, store_from_url
from product_matching.ml_ids import ml_ids_from_offer
from product_matching.offers import condition_labels, evaluate_offer
from product_matching.promotions import enrich_promotion
from product_matching.quality import catalog_offers, offer_url, valid_http_url, money, date_value

_cache = {}
_lock = Lock()

# Best offer: a direct product link may be up to this much dearer than a search/homepage/unverified link and still win.
NON_PRODUCT_PENALTY = 0.05
LOCAL_IMAGES = {'rtx-5060-8gb', 'rtx-5060-ti-8gb', 'rtx-5060-ti-16gb'}


def _usable_image(value):
    value = valid_http_url(value) if isinstance(value, str) and not value.startswith('/') else value
    return value if isinstance(value, str) and value and 'default-' not in value and 'placehold.co' not in value else None


def official_image(component):
    """First official Mercado Livre product picture, only from an enrichment the PC2YOU matcher accepted without conflicts."""
    enrichment = (component.get('external_enrichment') or {}).get('mercado_livre') or {}
    if enrichment.get('match_status') != 'matched' or enrichment.get('external_conflict'):
        return None
    image = next(iter(enrichment.get('images') or []), None)
    return image if isinstance(image, str) and image.startswith('https://') else None


def resolve_image(offer, component):
    """(url, source). source: promotion > mercado_livre_product_api > component_real > component > local > fallback
    (url None: UI category fallback)."""
    for source, value in (('promotion', offer.get('image') or offer.get('image_url') or offer.get('thumbnail')),
                          ('mercado_livre_product_api', official_image(component)),
                          ('component_real', component.get('real_image')),
                          ('component', (component.get('images') or [None])[0] or component.get('image'))):
        if _usable_image(value):
            return value, source
    if component.get('id') in LOCAL_IMAGES:
        return f"/images/{component['id']}.png", 'local'
    return None, 'fallback'


def projection(offer, component, *, captured=None, promotion_id=None, state=None, evaluation=None, now=None):
    price = money(offer.get('price'))
    conditions = offer.get('conditions') if isinstance(offer.get('conditions'), dict) else {}
    evaluation = evaluation or evaluate_offer(offer, now, captured=captured, conditions=conditions)
    deadlines = [date_value(offer.get('valid_until'))]
    if offer.get('coupon'):
        deadlines.append(date_value(offer.get('coupon_valid_until')))
    source = offer.get('source', 'unknown')
    until = min((d for d in deadlines if d), default=None)
    fresh_until = captured + timedelta(days=3 if source == 'telegram' else 7) if captured else None
    original = money(offer.get('original_price') or offer.get('regular_price'))
    original_url, resolved_url = offer_url(offer.get('url')), offer_url(offer.get('resolved_url'))
    best_url = choose_url(original_url, resolved_url)
    image, image_source = resolve_image(offer, component)
    ml_product_id, ml_item_id = ml_ids_from_offer(offer)
    return {'id': promotion_id or offer.get('external_id') or component['id'] + ':' + str(price),
            'component_id': component['id'], 'name': component['name'], 'brand': component.get('brand'),
            'category': component['category'], 'model': component['name'], 'source': source,
            'image': image, 'image_source': image_source, 'ml_product_id': ml_product_id, 'ml_item_id': ml_item_id,
            'price': price, 'currency': offer.get('currency') or 'BRL', 'original_price': original if original and price and original > price else None,
            'discount_percent': round((original-price)/original*100, 1) if original and price and original > price else None,
            'store': store_from_url(resolved_url) or store_from_url(original_url) or offer.get('store'), 'coupon': offer.get('coupon'), 'price_condition': 'coupon' if offer.get('coupon') else 'regular',
            'captured_at': captured.isoformat() if captured else None, 'valid_until': until.isoformat() if until else None,
            'fresh_until': fresh_until.isoformat() if fresh_until else None,
            'state': state or (offer.get('quality') or {}).get('state', 'unknown'),
            'url': best_url, 'original_url': original_url, 'resolved_url': resolved_url,
            'url_kind': classify_url(best_url) if best_url else 'unknown', 'checkout_verified': False,
            # Offer model: what was announced, under which conditions, and how far it can be trusted.
            'status': evaluation['status'], 'commercial_status': evaluation['status'], 'status_reason': evaluation['reason'],
            'freshness': evaluation['freshness'],
            'is_conditional': evaluation['is_conditional'], 'eligible': evaluation['eligible'],
            'conditions': conditions, 'condition_labels': condition_labels(conditions), 'conditions_text': conditions.get('conditions_text'),
            'requires_coupon': bool(offer.get('coupon')), 'coupon_code': offer.get('coupon') or None,
            'advertised_price': price, 'regular_price': original if original and price and original > price else None,
            'conditional_price': price if evaluation['is_conditional'] else None,
            'manual_validation': {'status': offer.get('manual_validation_status'), 'validated_at': offer.get('manual_validated_at')},
            'verification': {'source': offer.get('verification_source'), 'verified_price': money(offer.get('verified_price')),
                             'verified_at': offer.get('verified_at'), 'manual_status': offer.get('manual_validation_status'),
                             'manual_validated_at': offer.get('manual_validated_at')}}


def _dedupe_key(row):
    destination = urlsplit(row['url']) if row['url'] and row['url_kind'] == 'product' else None
    return (row['component_id'], row['price'], str(row['coupon'] or '').upper(), row['store'] or '',
            (destination.hostname, destination.path) if destination else None)


def dedupe(rows):
    """One commercial offer per key (newest kept). Source documents are untouched; `also_seen` counts the merged ones."""
    kept = {}
    for row in sorted(rows, key=lambda r: (r['captured_at'] or '', r['id']), reverse=True):
        key = _dedupe_key(row)
        if key in kept:
            kept[key]['also_seen'] += 1
            kept[key]['merged_ids'].append(row['id'])
        else:
            kept[key] = {**row, 'also_seen': 0, 'merged_ids': []}
    return list(kept.values())


def best_offer(rows):
    """Cheapest effective price, where a non-product destination costs NON_PRODUCT_PENALTY extra.

    So a direct product link at R$ 2.750 beats a search link at R$ 2.700, but not one at R$ 2.300."""
    # Equal effective price: a confirmed/recent announcement beats one that is already old and unconfirmed.
    return min(rows, key=lambda r: (r['price'] * (1 + (0 if r['url_kind'] == 'product' else NON_PRODUCT_PENALTY)),
                                    r.get('status') == 'stale', r.get('status') != 'confirmed',
                                    -kind_rank(r['url_kind']), r['id'])) if rows else None


def best_candidates(rows):
    """Only offers that may compete for "best price": eligible, with a usable link and a positive price."""
    return [r for r in rows if r.get('eligible') and r.get('url') and (r.get('price') or 0) > 0 and r.get('source') != 'seed']


def best_general_offer(rows):
    """Best offer without any relevant special condition (coupon, first purchase, app, payment method, membership, minimum)."""
    return best_offer([r for r in best_candidates(rows) if not r['is_conditional']])


def best_conditional_offer(rows):
    """Best offer that depends on a condition; always presented together with its conditions."""
    return best_offer([r for r in best_candidates(rows) if r['is_conditional']])


def listing_order(row):
    """Home order: active, (matched high is a precondition), useful URL, lowest price, newest."""
    return (row['state'] != 'active', -kind_rank(row['url_kind']) if row['url'] else 1, row['price'],
            tuple(-ord(c) for c in (row['captured_at'] or '')))


def build_snapshot(database, now=None):
    now = now or datetime.now(timezone.utc)
    components = list(database.components.find({}, {'_id': 0}))
    by_id = {c['id']: c for c in components}
    matcher = CatalogMatcher(components)
    current, historical, promotions = {}, {}, []
    total = 0
    for row in database.telegram_promotions.find({}).sort('created_at', -1):
        total += 1
        if row.get('is_demo'):
            continue
        enriched = enrich_promotion(row, matcher, now)
        p, offer = enriched['product'], enriched['offer']
        if p['match_level'] != 'high' or not p['component_id'] or offer.get('price') is None:
            continue
        component = by_id[p['component_id']]
        captured = date_value(offer.get('captured_at'))
        evaluation = enriched['evaluation']
        out = projection(offer, component, captured=captured, promotion_id=str(row['_id']), state=offer.get('state'),
                         evaluation=evaluation, now=now)
        if not out['price']:
            continue
        out['eligible'] = bool(evaluation['eligible'] and offer.get('verified'))
        if evaluation['status'] == 'invalid':
            out['state'] = 'invalid'
        elif out['eligible']:
            out['state'] = 'active'
        elif out['state'] == 'active':
            out['state'] = 'unknown'
        promotions.append(out)
        target = current if out['eligible'] and out['state'] == 'active' else historical
        target.setdefault(component['id'], []).append(out)
    for component in components:
        for offer in catalog_offers(component, now):
            if offer['quality']['source'] == 'seed':
                continue
            out = projection(offer, component, captured=date_value(offer['quality']['captured_at']), now=now)
            out['eligible'] = bool(out['eligible'] and offer['quality']['verified'])
            target = current if out['eligible'] and out['state'] == 'active' else historical
            target.setdefault(component['id'], []).append(out)
    for cid, rows in current.items():
        current[cid] = sorted(dedupe(rows), key=lambda r: (r['price'], r['id']))
    for cid, rows in historical.items():
        historical[cid] = sorted(dedupe(rows), key=lambda r: (r['captured_at'] or '', r['id']), reverse=True)
    best = {cid: best_offer(best_candidates(rows)) for cid, rows in current.items()}
    best_general = {cid: best_general_offer(rows) for cid, rows in current.items()}
    best_conditional = {cid: best_conditional_offer(rows) for cid, rows in current.items()}
    raw_published = len(promotions)
    promotions = sorted(dedupe(promotions), key=listing_order)
    for row in promotions:
        row['offers_count'] = len(current.get(row['component_id'], [])) if row['state'] == 'active' else 0
    statuses = {}
    for row in promotions:
        statuses[row['status']] = statuses.get(row['status'], 0) + 1
    return {'components': components, 'promotions': promotions, 'offers': current, 'history': historical, 'best': best,
            'best_general': best_general, 'best_conditional': best_conditional,
            'counts': {'by_status': statuses, 'mongo_promotions': total, 'published_promotions': len(promotions), 'raw_published': raw_published,
                       'active': sum(p['state'] == 'active' for p in promotions),
                       'historical': sum(p['state'] != 'active' for p in promotions)}}


def snapshot(database):
    key = f'{id(database.client)}:{database.client.address}:{database.name}'
    with _lock:
        if key not in _cache or time.monotonic() - _cache[key][0] > 30:
            _cache[key] = (time.monotonic(), build_snapshot(database))
        return _cache[key][1]
