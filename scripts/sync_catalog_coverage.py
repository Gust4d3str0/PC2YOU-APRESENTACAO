"""Insert reviewed real SKUs only. Existing records are never updated or replaced."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_enrichment import sync_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mongo', action='store_true', help='Use MONGO_URI from process environment')
    parser.add_argument('--db', default=os.getenv('MONGO_DB', 'orcapc_catalog'))
    parser.add_argument('--jsonl', type=Path, default=ROOT / 'demo-data/components.jsonl')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    rows = json.loads((ROOT / 'api-catalogo/catalog_coverage_v2.json').read_text(encoding='utf-8'))
    if args.mongo:
        from pymongo import MongoClient
        if not os.getenv('MONGO_URI'):
            parser.error('--mongo requires MONGO_URI')
        try:
            with MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=10000) as client:
                collection = client[args.db].components
                if args.apply and not any(i.get('unique') and i.get('key') == [('id', 1)] for i in collection.index_information().values()):
                    # Refuse rather than dropping/changing an existing non-unique id index.
                    raise RuntimeError('A unique id index is required before insert-only sync')
                result = sync_new(collection, rows, apply=args.apply)
        except Exception as exc:
            raise SystemExit(f'Insert-only Mongo sync failed ({type(exc).__name__}); credentials omitted. Requires unique id index.') from None
    else:
        contents = args.jsonl.read_text(encoding='utf-8')
        current = [json.loads(line) for line in contents.splitlines() if line.strip()]
        ids = [r['id'] for r in current]
        if len(set(ids)) != len(ids):
            raise SystemExit('Duplicate IDs; review before applying')
        added = [r for r in rows if r['id'] not in set(ids)]
        result = {'mode': 'apply' if args.apply else 'dry-run', 'would_insert': [r['id'] for r in added]}
        if args.apply and added:
            temporary = args.jsonl.with_suffix('.jsonl.tmp')
            temporary.write_text(contents.rstrip('\n') + '\n' + ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in added), encoding='utf-8')
            temporary.replace(args.jsonl)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
