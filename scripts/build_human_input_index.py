"""Build ONLY local lookup metadata for existing components. No import, Atlas or deletes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_specs.human_index import build_human_index

if __name__ == '__main__':
    from pymongo import MongoClient
    from pymongo.uri_parser import parse_uri
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uri', default='mongodb://127.0.0.1:27219')
    parser.add_argument('--db', default='pc2you_external_catalog_validation_release')
    args = parser.parse_args()
    if any(h not in {'127.0.0.1', 'localhost', '::1'} for h, _ in parse_uri(args.uri)['nodelist']):
        parser.error('This maintenance step permits loopback MongoDB only')
    with MongoClient(args.uri, serverSelectionTimeoutMS=5000) as client:
        print(json.dumps(build_human_index(client[args.db])))
