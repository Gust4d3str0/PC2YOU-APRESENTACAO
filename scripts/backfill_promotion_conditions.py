"""Backfill normalized conditions (`offer.conditions`, version 2) for stored Telegram promotions.

    python scripts/backfill_promotion_conditions.py             # dry-run (default): statistics only, nothing is written
    python scripts/backfill_promotion_conditions.py --dry-run
    python scripts/backfill_promotion_conditions.py --apply     # persist the conditions

Additive and idempotent: only `offer.conditions` is written (plus `offer.valid_until` when the document had none and the text
announces one). `raw_text`, price, coupon, URL, timestamps, the history and every other field are preserved; no document is
deleted. Conditions are read from the stored message text with deterministic rules (no AI, no network). The application also
derives them at read time, so the backfill is optional: it only makes the stored data self-describing.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient  # noqa: E402

from services.product_matching.offers import CONDITIONS_VERSION, payment_methods_of  # noqa: E402
from services.product_matching.promotions import enrich_promotion  # noqa: E402


def analyse(promotions, components, now=None):
    """(stats, updates). `updates` is a list of (document _id, {dotted field: value}) still to be written."""
    now = now or datetime.now(timezone.utc)
    stats = Counter()
    updates = []
    for document in promotions:
        enriched = enrich_promotion(document, components, now)
        conditions, evaluation = enriched['offer']['conditions'], enriched['evaluation']
        stats['promotions'] += 1
        stats['with_coupon'] += bool(conditions['requires_coupon'])
        stats['first_purchase'] += bool(conditions['first_purchase_only'])
        stats['new_customer'] += bool(conditions['new_customer_only'])
        stats['app_only'] += bool(conditions['app_only'])
        methods = payment_methods_of(conditions)
        stats['pix'] += 'PIX' in methods
        stats['nupay'] += 'NuPay' in methods
        stats['other_payment_method'] += bool(set(methods) - {'PIX', 'NuPay'})
        stats['membership'] += bool(conditions['membership_required'])
        stats['minimum_order'] += bool(conditions['minimum_order'])
        stats['max_uses_per_customer'] += bool(conditions['max_uses_per_customer'])
        stats['explicit_validity'] += bool(conditions['valid_until'])
        stats['conditional'] += evaluation['is_conditional']
        stats['without_known_condition'] += not evaluation['is_conditional']
        stats[f"status_{evaluation['status']}"] += 1
        stats['current_candidates'] += bool(evaluation['eligible'] and enriched['offer'].get('verified'))
        stored = (document.get('offer') or {}).get('conditions')
        fields = {}
        if stored != conditions:
            fields['offer.conditions'] = conditions
        if conditions['valid_until'] and not (document.get('offer') or {}).get('valid_until'):
            fields['offer.valid_until'] = conditions['valid_until']
        if fields:
            updates.append((document['_id'], fields, document.get('raw_text')))
    stats['to_update'] = len(updates)
    stats['already_up_to_date'] = stats['promotions'] - len(updates)
    return dict(stats), updates


def apply_updates(collection, updates):
    written = 0
    for _id, fields, raw_text in updates:
        # Compare-and-set on the text: a document edited meanwhile is left for the next run.
        written += collection.update_one({'_id': _id, 'raw_text': raw_text}, {'$set': fields}).modified_count
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017')
    parser.add_argument('--db', default='orcapc_catalog')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='report only (default)')
    mode.add_argument('--apply', action='store_true', help='write offer.conditions')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'reports/promotion-conditions-backfill.json')
    args = parser.parse_args()
    database = MongoClient(args.mongo_uri)[args.db]
    components = list(database.components.find({}, {'_id': 0}))
    stats, updates = analyse(database.telegram_promotions.find({'is_demo': {'$ne': True}}), components)
    report = {'mode': 'apply' if args.apply else 'dry-run', 'conditions_version': CONDITIONS_VERSION, 'stats': stats}
    if args.apply:
        report['written'] = apply_updates(database.telegram_promotions, updates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
