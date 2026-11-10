"""Reproducible LOCAL import/staging/promotion, real Mongo indexes and endpoint checks.

Never loads .env. Refuses non-loopback database hosts. Does not delete any data.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'services'), str(ROOT / 'scripts'), str(ROOT / 'api-orcamentos')]
from catalog_specs.coverage import audit
from catalog_specs.external_sources import Snapshot, IMPORT_CATEGORIES, POLICY
from catalog_specs.external_import import build_plan
from catalog_specs.external_persistence import stage_and_apply, plan_digest, ensure_import_indexes
from catalog_specs.lookup import LocalCatalog, lookup_mongo, lookup_query
from catalog_specs.identity import identity_scope
from import_external_catalog import read_jsonl, write_json

PCS = [
    ('A: AM4 / 4060 Ti, informal', 'Ryzen 7 5700X', 'Gigabyte B550M K', '32GB DDR4 3200', 'RTX 4060 Ti', '650W', 'NVMe 1TB', 'gabinete ATX'),
    ('B: Intel / 3060, informal', 'Intel i5-12400F', 'B660M DDR4', '16GB DDR4', 'RTX 3060', '650W', 'SSD NVMe 1TB', None),
    ('C: AM5 / RX 7800, informal', 'Ryzen 5 7600', 'B650', '32GB DDR5', 'RX 7800 XT', '750W', 'NVMe', None),
    ('AM4 complete', 'Processador Ryzen 7 5700X', 'Gigabyte B550M K', 'kingston-kf432c16bb-16', 'RTX 4060 Ti', '650W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('Intel complete', 'Intel i5-12400F', 'Gigabyte B660M AORUS PRO', 'kingston-kf432c16bb-16', 'RTX 3060', '650W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('AM5 complete', 'AMD Ryzen 5 7600', 'Gigabyte B650 Gaming X AX V2', 'kit-ram-32gb-ddr5-6000', 'RX 7800 XT', '750W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('CPU suffix X', 'AMD Ryzen 5 5600X', 'ASRock B550 PG VELOCITA', 'kingston-kf432c16bb-32', 'RTX 4070 Super', '750W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('CPU suffix base', 'Ryzen 5 5600', 'Gigabyte B550M K', 'kingston-kf432c16bb-16', 'RTX 4070', '750W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('CPU suffix G', 'AMD Ryzen 5 5600G', 'Gigabyte B550M K', 'kingston-kf432c16bb-16', 'RTX 3060', '650W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('Intel K / DDR4', 'Intel Core i5-13600K', 'Gigabyte B760M K DDR4', 'kit-ram-16gb-ddr4-3200', 'RTX 4070', '750W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('Intel DDR5', 'Intel Core i7-14700K', 'Gigabyte B760M DS3H DDR5', 'kit-ram-64gb-ddr5-6000', 'RTX 4080 Super', '850W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('Socket incompatible', 'Ryzen 5 7600', 'Gigabyte B550M K', 'kingston-kf432c16bb-16', 'RTX 4060', '650W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('DDR incompatible', 'Ryzen 5 5600', 'Gigabyte B550M K', 'kit-ram-32gb-ddr5-6000', 'RTX 3060', '650W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('Power insufficient', 'Ryzen 5 5600', 'Gigabyte B550M K', 'kingston-kf432c16bb-16', 'RTX 4070 Super', 'Corsair CV450', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('GPU expanded family Ti', 'Ryzen 5 5600', 'Gigabyte B550M K', 'kingston-kf432c16bb-16', 'GeForce RTX 3060 Ti', '650W', 'ssd-nvme-1tb', 'gabinete-lian-li-lancool'),
    ('Unknown CPU stays unknown', 'AMD Ryzen 5 5600 XYZ', 'B650', '32GB DDR5', 'RTX 4060 Ti 16GB', '750W', 'NVMe', None),
    ('Missing SKU remains unknown', 'Intel i5-12400F', 'ASUS B550M PRIME unknown-SKU', '16GB DDR4', 'RTX 4070 Ti Super', '650W', 'SN770 2TB', 'gabinete ATX'),
]


class MongoCatalog:
    def __init__(self, collection):
        self.collection, self.lookups = collection, []

    def resolve_components(self, category, name):
        started = perf_counter()
        result = lookup_mongo(self.collection, category, name)
        self.lookups.append((perf_counter() - started) * 1000)
        return result

    def upgrade_candidates(self, category, limit=24):
        rows = list(self.collection.find({'category': category}, {'_id': 0}).limit(limit))
        return [{**r, 'prices': []} for r in rows]

    def list_components(self, category):
        raise AssertionError('Full catalog scans are forbidden in /ai/analyze-pc')


def endpoint_validation(rows, catalog):
    from fastapi.testclient import TestClient
    import ai_routes
    from main import app
    from ai import AIService
    from ai.config import AISettings
    from validate_catalog_pcs import ValidationProseProvider
    service = AIService(AISettings(enabled=True, api_key='offline-no-real-key', cache_ttl=0, requests_per_minute=100), ValidationProseProvider())
    original = ai_routes.get_ai_service
    ai_routes.get_ai_service = lambda: service
    app.dependency_overrides[ai_routes.get_ai_catalog] = lambda: catalog
    configurations = list(PCS)
    # Exercise actual newly imported vendor SKUs and MPNs (never create test specifications).
    expected_imported = {}
    for category in ('gpu', 'ram', 'storage'):
        row = next(r for r in rows if r['category'] == category and '-ext-' in r['id'] and len(r['name']) <= 120
                   and len(catalog.resolve_components(category, r['name'])) == 1)
        base = list(PCS[3])
        base[0] = f'Imported {category} SKU: {row["id"]}'
        base[{'gpu': 4, 'ram': 3, 'storage': 6}[category]] = row['name']
        configurations.append(tuple(base))
        expected_imported[len(configurations)] = row['id']
    by_id = {r['id']: r for r in rows}
    results = []
    try:
        client = TestClient(app)
        for index, (label, cpu, board, ram, gpu, psu, storage, case) in enumerate(configurations, 1):
            components = dict(cpu=cpu, motherboard=board, ram=ram, gpu=gpu, psu=psu, storage=[storage], case=case)
            started = perf_counter()
            response = client.post('/ai/analyze-pc', json={'components': components, 'usage': ['gaming'], 'resolution': '1080p'})
            elapsed = (perf_counter() - started) * 1000
            body = response.json()
            verdict = body.get('compatibility', {})
            matches = []
            for item in body.get('components', []):
                cid = item.get('catalog_id')
                matches.append({'input_category': item['category'], 'catalog_id': cid,
                                'match_scope': identity_scope(by_id[cid]) if cid in by_id else 'unresolved'})
            valid_shape = response.status_code == 200 and len(verdict.get('checked_rules', [])) + len(verdict.get('unchecked_rules', [])) == 7
            if 4 <= index <= 11:
                valid_shape = valid_shape and body.get('metadata', {}).get('catalog_matches') == 7 and verdict.get('valid') is True
            if 12 <= index <= 14:
                valid_shape = valid_shape and verdict.get('valid') is False
            if index == 16:
                valid_shape = valid_shape and matches[0]['catalog_id'] is None
            if index in expected_imported:
                valid_shape = valid_shape and any(m['catalog_id'] == expected_imported[index] for m in matches)
            results.append({'pc': index, 'label': label, 'http_status': response.status_code, 'passed': valid_shape,
                            'recognized': body.get('metadata', {}).get('catalog_matches'), 'matches': matches,
                            'checked_rules': verdict.get('checked_rules'), 'pending_rules': verdict.get('unchecked_rules'),
                            'compatibility': verdict.get('status'), 'elapsed_ms': round(elapsed, 3), 'request': components})
    finally:
        ai_routes.get_ai_service = original
        app.dependency_overrides.pop(ai_routes.get_ai_catalog, None)
    return {'execution': 'real FastAPI route, real local MongoDB catalog, simulated prose only; no Gemini',
            'total': len(results), 'passed': sum(r['passed'] for r in results), 'results': results}


def benchmark(rows, collection=None, iterations=1000):
    catalog = MongoCatalog(collection) if collection is not None else LocalCatalog(rows)
    queries = [('cpu', 'Processador Ryzen 7 5700X'), ('cpu', 'Intel i5-12400F'), ('gpu', 'GeForce RTX 4060 Ti'),
               ('gpu', 'RTX 4070 Super'), ('storage', 'ssd-nvme-1tb'), ('motherboard', 'Gigabyte B550M K'), ('gpu', 'unknown-card')]
    times = []
    for i in range(iterations):
        started = perf_counter()
        catalog.resolve_components(*queries[i % len(queries)])
        times.append((perf_counter() - started) * 1000)
    times.sort()
    result = {'backend': 'MongoDB loopback' if collection is not None else 'in-memory exact index', 'catalog_size': len(rows),
              'iterations': iterations, 'median_ms': round(statistics.median(times), 4),
              'p95_ms': round(times[int(len(times) * .95)], 4), 'max_ms': round(max(times), 4),
              'queries': queries, 'llm_calls': 0, 'github_calls': 0, 'catalog_scans': 0}
    if collection is not None:
        explain = collection.database.command('explain', {'find': collection.name,
            'filter': lookup_query('cpu', 'Ryzen 7 5700X'), 'limit': 33}, verbosity='executionStats')
        result['explain'] = {'winning_plan': explain['queryPlanner']['winningPlan'],
            'documents_examined': explain['executionStats']['totalDocsExamined'],
            'keys_examined': explain['executionStats']['totalKeysExamined']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mongo-uri', default='mongodb://127.0.0.1:27219')
    parser.add_argument('--db', default='pc2you_external_catalog_validation_release')
    parser.add_argument('--reuse-buildcores-plan', action='store_true', help='Replay the immutable local dry-run without rereading upstream data')
    args = parser.parse_args()
    from pymongo.uri_parser import parse_uri
    from pymongo import MongoClient
    if any(host not in {'127.0.0.1', 'localhost', '::1'} for host, _ in parse_uri(args.mongo_uri)['nodelist']):
        parser.error('Validation permits loopback MongoDB only')
    if not args.db.startswith('pc2you_external_catalog_'):
        parser.error('Use an isolated pc2you_external_catalog_* database')
    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[args.db]
    seed = read_jsonl(ROOT / 'demo-data/components.jsonl')
    ensure_import_indexes(db)
    for row in seed:
        db.components.update_one({'id': row['id']}, {'$setOnInsert': deepcopy(row)}, upsert=True)
    before = audit(seed)
    write_json(ROOT / 'reports/external-coverage-before.json', before)
    state, summaries = seed, {}
    for source in [s for s in POLICY['source_priority'] if s in {'buildcores', 'pc_part_dataset'}]:
        print('Planning', source, flush=True)
        if source == 'buildcores' and args.reuse_buildcores_plan:
            report = json.loads((ROOT / 'reports/buildcores-import-plan.json').read_text(encoding='utf-8'))
            if report['review_digest'] != plan_digest(report):
                raise ValueError('BuildCores plan integrity mismatch')
            snapshot = Snapshot(ROOT / 'external-data/buildcores', 'buildcores')
            if snapshot.metadata['commit'] != report['snapshot']['commit']:
                raise ValueError('BuildCores snapshot commit mismatch')
            report['policy'] = POLICY
        else:
            report, _ = build_plan(Snapshot(ROOT / 'external-data' / source, source), state, IMPORT_CATEGORIES)
        report['review_digest'] = plan_digest(report)
        filename = 'buildcores-import-plan.json' if source == 'buildcores' else 'pc-part-dataset-import-plan.json'
        write_json(ROOT / 'reports' / filename, report)
        print('Applying LOCAL staging and promotion', report['summary'], flush=True)
        persistence = stage_and_apply(db, report, promote=True)
        failures = [r for r in persistence['promotions'] if r['result'] != 'merged']
        summaries[source] = {'summary': report['summary'], 'snapshot': report['snapshot'], 'review_digest': report['review_digest'],
                             'rejection_reasons': report['rejection_reasons'], 'promotion_failures': failures,
                             'metadata_migration': persistence['metadata_migration']}
        # Subsequent sources see the real persisted state, including any CAS failures.
        state = list(db.components.find({}, {'_id': 0}))
        write_json(ROOT / 'reports' / (source + '-local-apply.json'), persistence)
        if failures:
            print('Promotion conflicts', len(failures), flush=True)
    local_output = ROOT / 'reports/external-catalog-local.jsonl'
    with local_output.open('w', encoding='utf-8') as handle:
        for row in state:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    after = audit(state)
    write_json(ROOT / 'reports/external-coverage-after.json', after)
    catalog = MongoCatalog(db.components)
    endpoints = endpoint_validation(state, catalog)
    write_json(ROOT / 'reports/external-pc-validation.json', endpoints)
    perf = benchmark(state, db.components)
    write_json(ROOT / 'reports/external-lookup-benchmark.json', perf)
    result = {'sources': summaries, 'mongo_version': client.server_info()['version'], 'database': args.db,
              'before': {k: v for k, v in before.items() if k != 'components'},
              'after': {k: v for k, v in after.items() if k != 'components'},
              'staging_statuses': {r['_id']: r['count'] for r in db.catalog_import_candidates.aggregate([
                  {'$group': {'_id': '$status', 'count': {'$sum': 1}}}])},
              'pcs': endpoints, 'benchmark': perf,
              'lookup_durations_ms': {'median': statistics.median(catalog.lookups), 'max': max(catalog.lookups)}}
    write_json(ROOT / 'reports/external-validation-summary.json', result)
    print(json.dumps({'total': after['total'], 'pcs_passed': endpoints['passed'], 'pcs_total': endpoints['total'], 'benchmark': perf}, default=str), flush=True)
    client.close()
    return 0 if endpoints['passed'] == endpoints['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
