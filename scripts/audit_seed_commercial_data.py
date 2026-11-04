"""Audit (and optionally archive) synthetic commercial data left in `components` by the old seed.

    python scripts/audit_seed_commercial_data.py                  # dry-run: report only, writes nothing to the database
    python scripts/audit_seed_commercial_data.py --apply          # archive seed prices/history into `legacy_seed_commercial`

Seed entries are the fictitious prices (`source == "seed"`, search links of Kabum/Pichau/Terabyte) and the synthetic
price-history curves. The application already ignores them everywhere; `--apply` only removes them from `prices` /
`price_history` and keeps a copy under `legacy_seed_commercial` (nothing is deleted). Entries from real sources
(Mercado Livre, Telegram, manual) are never touched. Telegram promotions and `product_price_history` are not read or changed.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient  # noqa: E402


def is_seed_price(entry):
    return not isinstance(entry, dict) or entry.get('source', 'seed') == 'seed'


def is_seed_history(entry):
    return isinstance(entry, dict) and entry.get('source') == 'seed'


def audit(components):
    """Counts of seed vs real commercial entries over a list of component documents."""
    report = {'components': 0, 'with_seed_prices': 0, 'with_seed_history': 0, 'seed_prices': 0, 'seed_history': 0,
              'real_prices_by_source': Counter(), 'real_history': 0, 'already_archived': 0, 'seed_stores': Counter(), 'by_component': []}
    for document in components:
        report['components'] += 1
        prices, history = document.get('prices') or [], document.get('price_history') or []
        seed_prices = [p for p in prices if is_seed_price(p)]
        seed_history = [h for h in history if is_seed_history(h)]
        report['seed_prices'] += len(seed_prices)
        report['seed_history'] += len(seed_history)
        report['with_seed_prices'] += bool(seed_prices)
        report['with_seed_history'] += bool(seed_history)
        report['already_archived'] += 'legacy_seed_commercial' in document
        report['real_history'] += len(history) - len(seed_history)
        for p in prices:
            if not is_seed_price(p):
                report['real_prices_by_source'][p.get('source')] += 1
        for p in seed_prices:
            report['seed_stores'][p.get('store') if isinstance(p, dict) else None] += 1
        if seed_prices or seed_history:
            report['by_component'].append({'id': document.get('id'), 'seed_prices': len(seed_prices), 'seed_history': len(seed_history)})
    return {k: dict(v) if isinstance(v, Counter) else v for k, v in report.items()}


def archive(collection, now=None):
    """Move seed entries to `legacy_seed_commercial`; returns how many components were changed. Idempotent."""
    now = (now or datetime.now(timezone.utc)).isoformat()
    changed = 0
    for document in list(collection.find({})):
        prices, history = document.get('prices') or [], document.get('price_history') or []
        seed_prices = [p for p in prices if is_seed_price(p)]
        seed_history = [h for h in history if is_seed_history(h)]
        if not seed_prices and not seed_history:
            continue
        previous = document.get('legacy_seed_commercial') or {}
        legacy = {'prices': (previous.get('prices') or []) + seed_prices, 'price_history': (previous.get('price_history') or []) + seed_history,
                  'archived_at': now, 'note': 'Synthetic seed data (fictitious prices, store search links, synthetic history). Not real.'}
        collection.update_one({'_id': document['_id'], 'prices': prices, 'price_history': history}, {'$set': {
            'prices': [p for p in prices if not is_seed_price(p)],
            'price_history': [h for h in history if not is_seed_history(h)], 'legacy_seed_commercial': legacy}})
        changed += 1
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017')
    parser.add_argument('--db', default='orcapc_catalog')
    parser.add_argument('--apply', action='store_true', help='archive seed entries (default: dry-run)')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'reports/seed-commercial-audit.json')
    args = parser.parse_args()
    database = MongoClient(args.mongo_uri)[args.db]
    report = audit(database.components.find({}))
    report['mode'] = 'apply' if args.apply else 'dry-run'
    if args.apply:
        report['components_changed'] = archive(database.components)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {k: v for k, v in report.items() if k != 'by_component'}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'Relatório: {args.output}')


if __name__ == '__main__':
    main()
