"""One Telegram adapter for collection, reprocessing and the AI read model."""
from copy import deepcopy
from .matcher import match_product
from .offers import CONDITIONS_VERSION, evaluate_offer, extract_conditions
from .quality import price_quality, equivalence_key, history_observation


def promotion_match(document, catalog):
    product = document.get('product') or {}
    raw = document.get('raw_text')
    title = product.get('name') or (raw if isinstance(raw, str) else '')
    return match_product({'title': title, 'brand': product.get('brand'),
                          'category': product.get('component_type'), 'source': 'telegram'}, catalog)


def enrich_promotion(document, catalog, now=None):
    result = deepcopy(document)
    match = promotion_match(document, catalog)
    product = result.setdefault('product', {})
    previous = product.get('component_id')
    if previous and previous != match.component_id:
        product['previous_component_id'] = previous
    product.update(component_id=match.component_id, normalized_key=match.normalized_key,
                   match_confidence=match.confidence, match_level=match.confidence_level,
                   matched_by=match.matched_by, conflicts=match.conflicts, matcher_version=match.matcher_version)
    offer = result.setdefault('offer', {})
    captured = (result.get('telegram') or {}).get('sent_at') or result.get('created_at')
    # Conditions are read from the stored parse when present, else derived from the stored text (older documents).
    if not isinstance(offer.get('conditions'), dict) or offer['conditions'].get('conditions_version') != CONDITIONS_VERSION:
        offer['conditions'] = extract_conditions(result.get('raw_text'), offer.get('coupon'), captured)
    if not offer.get('valid_until') and offer['conditions'].get('valid_until'):
        offer['valid_until'] = offer['conditions']['valid_until']
    quality = price_quality(offer, match, now=now, source='telegram', captured_at=captured)
    if result.get('is_demo') or result.get('status') not in {'parsed', 'matched', 'verified', 'published'}:
        quality['verified'] = False
    offer.update(quality)
    # Derived at read time, never persisted: status ages with the clock.
    result['evaluation'] = evaluate_offer(offer, now, captured=quality['captured_at'], conditions=offer['conditions'])
    result['equivalence_key'] = equivalence_key(match.component_id, offer)
    result['price_observation'] = history_observation(match.component_id, offer, quality)
    return result
