"""Compare identical persisted promotions against Mongo catalog and corrected seed in memory."""
import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'services'))
from catalog_audit.seed_io import load_seed


class ReadOnlyRows:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    def find(self, *args, **kwargs):
        return ReadOnlyRows(self.rows)

    def sort(self, *args):
        # Promotion snapshot is already ordered by the Mongo query before comparison.
        return self

    def limit(self, limit):
        return ReadOnlyRows(self.rows[:limit])

    def __iter__(self):
        return iter(deepcopy(self.rows))


def compare_snapshots(promotions, mongo_catalog, seed_catalog, now=None):
    from scripts.reprocess_product_matches import reprocess
    from services.product_matching import CatalogMatcher
    from services.product_matching.promotions import enrich_promotion
    now = now or datetime.now(timezone.utc)
    def database(catalog):
        return SimpleNamespace(components=ReadOnlyRows(catalog), telegram_promotions=ReadOnlyRows(promotions))
    before = reprocess(database(mongo_catalog), limit=len(promotions), dry_run=True, now=now)
    after = reprocess(database(seed_catalog), limit=len(promotions), dry_run=True, now=now)
    old_matcher, new_matcher = CatalogMatcher(mongo_catalog), CatalogMatcher(seed_catalog)
    old_names = {c['id']: c['name'] for c in mongo_catalog}
    new_names = {c['id']: c['name'] for c in seed_catalog}
    differences = []
    for index, row in enumerate(promotions):
        old = enrich_promotion(row, old_matcher, now)['product']
        new = enrich_promotion(row, new_matcher, now)['product']
        if (old['component_id'], old['match_level'], old['match_confidence']) != (new['component_id'], new['match_level'], new['match_confidence']):
            differences.append({'sample_index': index, 'normalized_key': new['normalized_key'],
                                'before': {**{k: old[k] for k in ('component_id', 'match_level', 'match_confidence', 'conflicts')},
                                           'catalog_name': old_names.get(old['component_id'])},
                                'after': {**{k: new[k] for k in ('component_id', 'match_level', 'match_confidence', 'conflicts')},
                                          'catalog_name': new_names.get(new['component_id'])}})
    return {'mode': 'dry-run-corrected-seed-preview', 'mongo_written': False,
            'baseline_expected_counts': {'high': 43, 'medium': 3, 'low': 608},
            'mongo_catalog': before, 'corrected_seed': after, 'changed_decisions': differences}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=654)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/data-quality-after-seed-fix-preview.json')
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 10000:
        parser.error('--limit must be 1..10000')
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from bson.json_util import dumps
    from pymongo.errors import PyMongoError
    load_dotenv(ROOT / '.env')
    try:
        with MongoClient(os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'), tz_aware=True,
                         serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=5000) as client:
            db = client[os.getenv('MONGO_DB', 'orcapc_catalog')]
            def fingerprint():
                return {name: hashlib.sha256(dumps(list(db[name].find({}).sort('_id', 1)), sort_keys=True).encode()).hexdigest()
                        for name in ('components', 'telegram_promotions', 'product_price_history')}
            before_hash = fingerprint()
            catalog = list(db.components.find({}, {'_id': 0}))
            promotions = list(db.telegram_promotions.find({}).sort([('created_at', -1), ('_id', -1)]).limit(args.limit))
            report = compare_snapshots(promotions, catalog, load_seed(ROOT / 'api-catalogo/seed.py'))
            after_hash = fingerprint()
            report['collection_fingerprints_before'] = before_hash
            report['collection_fingerprints_after'] = after_hash
            report['collections_unchanged'] = before_hash == after_hash
    except PyMongoError:
        print('MongoDB unavailable. No write operations exist in this preview.', file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'before': report['mongo_catalog']['proposed']['counts'],
                      'after': report['corrected_seed']['proposed']['counts'],
                      'changed_decisions': len(report['changed_decisions']), 'collections_unchanged': report['collections_unchanged']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
