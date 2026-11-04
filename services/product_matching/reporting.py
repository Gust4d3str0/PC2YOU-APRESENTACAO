"""Aggregates only; no sender, token or raw message enters a quality report."""
from collections import Counter
from .quality import money, offer_url


def quality_report(documents):
    counts = Counter()
    conflicts = Counter()
    total = 0
    for doc in documents:
        total += 1
        product, offer = doc.get('product') or {}, doc.get('offer') or {}
        level = product.get('match_level')
        counts[level if level in {'high', 'medium', 'low'} else 'unassessed'] += 1
        counts['component_id'] += bool(product.get('component_id'))
        counts['url'] += bool(offer_url(offer.get('url')))
        counts['price'] += money(offer.get('price')) is not None
        counts['store'] += bool(offer.get('store'))
        counts['verified_price'] += offer.get('verified') is True
        conflicts.update(product.get('conflicts') or [])
    return {'total_promotions': total, 'counts': dict(counts),
            'percentages': {k: round(counts[k] * 100 / total, 2) if total else 0
                            for k in ('component_id', 'high', 'medium', 'low', 'unassessed', 'url', 'price', 'store', 'verified_price')},
            'conflicts': dict(conflicts)}
