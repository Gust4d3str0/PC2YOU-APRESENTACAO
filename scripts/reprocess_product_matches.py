"""Local quality audit/backfill. Default is dry-run; --apply explicitly persists metadata."""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.product_matching.promotions import enrich_promotion
from services.product_matching import CatalogMatcher
from services.product_matching.reporting import quality_report


def reprocess(database, *, limit=100, dry_run=True, now=None):
    from services.telegram_collector.repository import PromotionRepository
    catalog = list(database.components.find({}, {'_id': 0}))
    documents = list(database.telegram_promotions.find({}).sort([('created_at', -1), ('_id', -1)]).limit(limit))
    matcher = CatalogMatcher(catalog)
    proposed = [enrich_promotion(doc, matcher, now) for doc in documents]
    written, raced = 0, 0
    if not dry_run:
        repository = PromotionRepository(database)
        for doc in documents:
            result = repository.refresh_quality({'_id': doc['_id']})
            written += result is not None
            raced += result is None
    samples = {}
    for level in ('high', 'medium', 'low'):
        samples[level] = []
        for doc in proposed:
            p = doc['product']
            if p['match_level'] == level and len(samples[level]) < 4:
                target = next((c for c in catalog if c['id'] == p['component_id']), {})
                samples[level].append({'component_id': p['component_id'], 'catalog_name': target.get('name'),
                                       'normalized_key': p['normalized_key'], 'confidence': p['match_confidence'],
                                       'matched_by': p['matched_by'], 'conflicts': p['conflicts']})
    return {'mode': 'dry-run' if dry_run else 'apply', 'source': 'telegram', 'catalog_components': len(catalog),
            'messages_analyzed': len(documents), 'documents_updated': written, 'concurrent_changes_skipped': raced,
            'before': quality_report(documents), 'proposed': quality_report(proposed), 'samples': samples}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['telegram'], default='telegram')
    parser.add_argument('--limit', type=int, default=100)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--report-only', action='store_true', help='Aggregate persisted metadata without rematching')
    parser.add_argument('--output', type=Path, help='Save aggregate JSON without URLs/raw messages/Telegram IDs')
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 10000:
        parser.error('--limit must be between 1 and 10000')
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    load_dotenv(ROOT / '.env')
    try:
        with MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017'), tz_aware=True,
                         serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=5000) as client:
            database = client[os.getenv('MONGO_DB', 'orcapc_catalog')]
            if args.report_only:
                report = {'mode': 'persisted-report', **quality_report(database.telegram_promotions.find({}, {'product': 1, 'offer': 1}))}
            else:
                report = reprocess(database, limit=args.limit, dry_run=not args.apply, now=datetime.now(timezone.utc))
    except PyMongoError:
        print('MongoDB unavailable; no changes made. Check the configured connection.', file=sys.stderr)
        return 1
    result = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + '\n', encoding='utf-8')
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
