"""Insert new enrichment rows only. Default dry-run; never reprocess promotions."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'services'))
from catalog_audit.seed_io import load_seed
from catalog_enrichment import sync_new, baseline_divergences
from scripts.preview_catalog_enrichment import load_expansion, validate_catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    rows = load_expansion()
    base = load_seed(ROOT / 'api-catalogo/seed.py')
    validate_catalog(base, rows)
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    load_dotenv(ROOT / '.env')
    try:
        with MongoClient(os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000) as client:
            collection = client[os.getenv('MONGO_DB', 'orcapc_catalog')].components
            differences = baseline_divergences(base, list(collection.find({}, {'_id': 0})))
            if args.apply and differences:
                parser.error('Apply blocked: live catalog identity differs from audited baseline. Review the prior identity sync first; nothing written.')
            if args.apply and not any(i.get('unique') and list(i.get('key', {}).items()) == [('id', 1)] for i in collection.list_indexes()):
                parser.error('Apply requires an existing unique components.id index; no index was changed.')
            result = sync_new(collection, rows, apply=args.apply)
            result['baseline_divergences'] = differences
            result['apply_ready'] = not differences
    except PyMongoError:
        print('MongoDB operation failed. Connection details omitted.', file=sys.stderr)
        return 1
    path = ROOT / 'reports' / f"catalog-enrichment-sync-{result['mode']}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
