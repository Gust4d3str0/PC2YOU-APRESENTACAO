"""Read-only coverage audit of every component in JSONL or MongoDB."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_specs.coverage import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jsonl', type=Path, default=ROOT / 'demo-data/components.jsonl')
    parser.add_argument('--mongo', action='store_true', help='Use MONGO_URI environment variable')
    parser.add_argument('--db', default=os.getenv('MONGO_DB', 'orcapc_catalog'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mongo:
        from pymongo import MongoClient
        if not os.getenv('MONGO_URI'):
            parser.error('--mongo requires MONGO_URI')
        try:
            with MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=10000) as client:
                rows = list(client[args.db].components.find({}))
        except Exception as exc:
            raise SystemExit(f'MongoDB audit failed ({type(exc).__name__}); credentials omitted') from None
    else:
        rows = [json.loads(line) for line in args.jsonl.read_text(encoding='utf-8').splitlines() if line.strip()]
    report = audit(rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Total: {report["total"]}')
    for category, row in report['categories'].items():
        print(f'{category}: {row["complete"]}/{row["total"]}')


if __name__ == '__main__':
    main()
