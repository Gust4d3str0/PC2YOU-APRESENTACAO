"""Sync audited seed identity corrections only. Default is dry-run. Does not touch matches."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_audit.seed_io import load_seed
from catalog_audit.sync import sync_components, validate_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    rows = load_seed(ROOT / 'api-catalogo/seed.py')
    refs = json.loads((ROOT / 'api-catalogo/seed_identity_reference.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'api-catalogo/seed_identity_corrections.json').read_text(encoding='utf-8'))
    validate_manifest(manifest, rows, refs)
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    load_dotenv(ROOT / '.env')
    try:
        with MongoClient(os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'), tz_aware=True,
                         serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=5000) as client:
            collection = client[os.getenv('MONGO_DB', 'orcapc_catalog')].components
            result = sync_components(collection, manifest, apply=args.apply)
    except PyMongoError:
        print('MongoDB operation failed. Connection details omitted.', file=sys.stderr)
        return 1
    path = args.output or ROOT / f"reports/catalog-identity-sync-{result['mode']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'changes'}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
