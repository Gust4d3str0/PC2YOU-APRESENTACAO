"""Local-only idempotence and concurrent replay check using already-reviewed real records."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json

from validate_external_catalog import ROOT, write_json
from catalog_specs.external_persistence import stage_and_apply, promote_candidate


def digest(collection):
    sha = hashlib.sha256()
    for row in collection.find({}, {'_id': 0}).sort('id', 1):
        sha.update(json.dumps(row, sort_keys=True, separators=(',', ':')).encode())
    return sha.hexdigest()


def changed_paths(before, after, prefix=''):
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        return [p for key in sorted(set(before) | set(after)) for p in changed_paths(
            before.get(key), after.get(key), f'{prefix}.{key}' if prefix else key)]
    return [prefix]


if __name__ == '__main__':
    from pymongo import MongoClient
    from pymongo.uri_parser import parse_uri
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mongo-uri', default='mongodb://127.0.0.1:27219')
    parser.add_argument('--db', default='pc2you_external_catalog_validation_release')
    args = parser.parse_args()
    if any(h not in {'localhost', '127.0.0.1', '::1'} for h, _ in parse_uri(args.mongo_uri)['nodelist']) or not args.db.startswith('pc2you_external_catalog_'):
        parser.error('Replay validation requires an isolated loopback database')
    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[args.db]
    before_rows = {r['id']: r for r in db.components.find({}, {'_id': 0})}
    before = digest(db.components)
    count = db.components.count_documents({})
    checks = []
    for filename in ('buildcores-import-plan.json', 'pc-part-dataset-import-plan.json'):
        print('Replaying', filename, flush=True)
        report = json.loads((ROOT / 'reports' / filename).read_text(encoding='utf-8'))
        replay = stage_and_apply(db, report, promote=True)
        checks.append({'source': report['source'], 'promotions': len(replay['promotions']),
                       'blocked': sum(r['result'] != 'merged' for r in replay['promotions'])})
        candidate = next(c for c in report['candidates'] if c['status'] == 'accepted' and
                         db.components.find_one({'id': c['canonical_id']}) is not None)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: promote_candidate(db.components, candidate), range(32)))
        checks[-1]['concurrent_replays'] = len(results)
        checks[-1]['concurrent_results'] = {status: results.count(status) for status in set(results)}
    after = digest(db.components)
    differences = []
    if before != after:
        for row in db.components.find({}, {'_id': 0}):
            previous = before_rows.get(row['id'])
            if previous != row:
                differences.append({'id': row['id'], 'fields': changed_paths(previous, row)})
    result = {'database': args.db, 'count_before': count, 'count_after': db.components.count_documents({}), 'sha256_before': before,
              'sha256_after': after, 'unchanged': before == after, 'checks': checks, 'differences': differences}
    write_json(ROOT / 'reports/external-replay-validation.json', result)
    print(json.dumps(result), flush=True)
    client.close()
    raise SystemExit(0 if result['unchanged'] and result['count_before'] == result['count_after'] else 1)
