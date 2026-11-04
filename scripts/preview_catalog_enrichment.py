"""Discover missing models and compare catalogs using one read-only Mongo snapshot."""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_audit import audit_components
from catalog_audit.seed_io import load_seed
from catalog_enrichment import discover, baseline_divergences
from product_matching import CatalogMatcher
from product_matching.promotions import promotion_match


def load_expansion():
    return json.loads((ROOT / 'api-catalogo/catalog_enrichment_v1.json').read_text(encoding='utf-8'))


def validate_catalog(base, additions):
    refs = {}
    for name in ('seed_identity_reference.json', 'catalog_enrichment_sources.json'):
        refs.update(json.loads((ROOT / 'api-catalogo' / name).read_text(encoding='utf-8')))
    audit = audit_components(base + additions, refs)
    if audit['summary']['critical_conflicts']:
        raise ValueError('Catalog identity audit failed')
    if any(r.get('prices') or r.get('price_history') or any(v is not None for v in r.get('benchmark', {}).values()) for r in additions):
        raise ValueError('Enrichment cannot introduce estimated prices, history or benchmarks')
    return audit


def preview(promotions, base, additions):
    old, new = CatalogMatcher(base), CatalogMatcher(base + additions)
    before, after, transitions = Counter(), Counter(), Counter()
    changes = []
    for index, row in enumerate(promotions):
        a, b = promotion_match(row, old), promotion_match(row, new)
        before[a.confidence_level] += 1
        after[b.confidence_level] += 1
        if (a.confidence_level, a.component_id) != (b.confidence_level, b.component_id):
            transition = f'{a.confidence_level}->{b.confidence_level}'
            if a.confidence_level == b.confidence_level == 'high':
                transition = 'high->high_different'
            transitions[transition] += 1
            changes.append({'sample_index': index, 'transition': transition,
                            'before': a.to_dict(), 'after': b.to_dict()})
    for name in ('low->high', 'low->medium', 'medium->high', 'high->low', 'high->high_different'):
        transitions.setdefault(name, 0)
    transitions['high->conflict'] = sum(c['before']['confidence_level'] == 'high' and bool(c['after']['conflicts']) for c in changes)
    return {'mode': 'dry-run', 'mongo_written': False, 'promotions': len(promotions),
            'catalog_before': len(base), 'catalog_after': len(base + additions),
            'thresholds': {'high': .85, 'medium': .65}, 'before': dict(before), 'after': dict(after),
            'transitions': dict(transitions), 'changed_decisions': changes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=654)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 10000:
        parser.error('--limit must be 1..10000')
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from bson.json_util import dumps
    from pymongo.errors import PyMongoError
    base = load_seed(ROOT / 'api-catalogo/seed.py')
    additions = load_expansion()
    audit = validate_catalog(base, additions)
    load_dotenv(ROOT / '.env')
    try:
        with MongoClient(os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'), tz_aware=True,
                         serverSelectionTimeoutMS=3000, socketTimeoutMS=5000) as client:
            db = client[os.getenv('MONGO_DB', 'orcapc_catalog')]
            def fingerprint():
                return {name: hashlib.sha256(dumps(list(db[name].find({}).sort('_id', 1)), sort_keys=True).encode()).hexdigest()
                        for name in ('components', 'telegram_promotions', 'product_price_history')}
            hashes = fingerprint()
            promos = list(db.telegram_promotions.find({}).sort([('created_at', -1), ('_id', -1)]).limit(args.limit))
            current = list(db.components.find({}, {'_id': 0}))
            candidates = discover(promos, base)
            result = preview(promos, base, additions)
            result['baseline_origin'] = 'audited_corrected_seed_in_memory'
            result['live_baseline_divergences'] = baseline_divergences(base, current)
            result['live_mongo_comparison'] = preview(promos, current, additions)
            result['sync_ready'] = not result['live_baseline_divergences']
            result['collection_fingerprints_before'] = hashes
            result['collection_fingerprints_after'] = fingerprint()
            result['collections_unchanged'] = hashes == result['collection_fingerprints_after']
            result['generated_at'] = datetime.now(timezone.utc).isoformat()
            for candidate in candidates['candidates']:
                candidate['estimated_high_matches'] = sum(c['transition'] == 'low->high' and candidate['normalized_model'] in c['after']['normalized_key'].split('|')[1].split(',') for c in result['changed_decisions'])
                candidate['model_clarity_weight'] = 2 if candidate['category'] in {'gpu', 'cpu'} else 1
                candidate['category_weight'] = 5 if candidate['category'] in {'gpu', 'cpu'} else 3
                candidate['priority_score'] = (candidate['occurrences'] * 10 + candidate['model_clarity_weight']
                                               + candidate['category_weight'] + candidate['estimated_high_matches'] * 2)
            candidates['candidates'].sort(key=lambda c: (-c['priority_score'], c['category'], c['normalized_model']))
            candidates['ranking_method'] = 'occurrences * 10 + explicit model clarity (1..2) + category (3..5) + measured low-to-high gain * 2; prices are not used'
    except PyMongoError:
        print('MongoDB unavailable; preview performed no writes.', file=sys.stderr)
        return 1
    for filename, report in [('catalog-enrichment-candidates.json', candidates), ('catalog-enrichment-preview.json', result),
                             ('catalog-enrichment-audit.json', audit)]:
        path = ROOT / 'reports' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('before', 'after', 'transitions', 'collections_unchanged')}))
    return 0 if result['collections_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
