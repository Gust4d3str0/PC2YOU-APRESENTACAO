"""Shared CLI: dry-run by default; stage explicitly; promote only a reviewed plan."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_specs.external_sources import Snapshot, IMPORT_CATEGORIES, POLICY
from catalog_specs.external_import import build_plan
from catalog_specs.external_persistence import plan_digest, stage_and_apply


def read_jsonl(path):
    rows, total = [], 0
    with Path(path).open(encoding='utf-8') as handle:
        for line in handle:
            total += len(line.encode())
            if len(line.encode()) > POLICY['max_record_bytes'] or total > POLICY['max_snapshot_bytes'] or len(rows) >= POLICY['max_records']:
                raise ValueError('Local catalog exceeds resource limits')
            if line.strip():
                row = json.loads(line)
                row.pop('_id', None)  # Demo exports use Extended JSON; internal Mongo IDs are never portable.
                rows.append(row)
    return rows


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
        handle.write('\n')


def main(source, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true', help='Write candidates to staging only, unless --promote is supplied')
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'external-data' / source)
    parser.add_argument('--category', choices=sorted(IMPORT_CATEGORIES), action='append')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--newer-than', type=date.fromisoformat)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--jsonl', type=Path, default=ROOT / 'demo-data/components.jsonl')
    parser.add_argument('--local-output', type=Path, default=ROOT / 'reports/external-catalog-local.jsonl')
    parser.add_argument('--mongo', action='store_true', help='Read MONGO_URI from environment only; never load .env implicitly')
    parser.add_argument('--db', default='pc2you_external_catalog_local')
    parser.add_argument('--promote', action='store_true', help='Requires --apply --review-plan; promote safe candidates')
    parser.add_argument('--review-plan', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports' / ('buildcores-import-plan.json' if source == 'buildcores' else 'pc-part-dataset-import-plan.json'))
    args = parser.parse_args(argv)
    if args.limit is not None and not 1 <= args.limit <= POLICY['max_records']:
        parser.error(f"--limit must be 1..{POLICY['max_records']}")
    if args.promote and (not args.apply or not args.review_plan):
        parser.error('--promote requires --apply --review-plan with the exact dry-run report')
    if args.mongo and not os.getenv('MONGO_URI'):
        parser.error('--mongo requires an explicitly exported MONGO_URI')
    client = None
    try:
        if args.mongo:
            from pymongo import MongoClient
            client = MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=20000)
            database = client[args.db]
            existing = list(database.components.find({}))
        else:
            existing = read_jsonl(args.jsonl)
        snapshot = Snapshot(args.snapshot, source)
        policy = json.loads(args.policy.read_text(encoding='utf-8')) if args.policy else POLICY
        if set(policy['source_priority']) != set(POLICY['source_priority']):
            raise ValueError('source_priority must contain every documented source')
        report, after = build_plan(snapshot, existing, set(args.category or IMPORT_CATEGORIES), limit=args.limit, newer_than=args.newer_than, policy=policy)
        report['review_digest'] = plan_digest(report)
        if args.promote:
            reviewed = json.loads(args.review_plan.read_text(encoding='utf-8'))
            if plan_digest(reviewed) != report['review_digest'] or reviewed.get('review_digest') != report['review_digest']:
                raise ValueError('Plan changed since review; run dry-run and review the new plan')
        if args.apply:
            report['mode'] = 'apply-promote' if args.promote else 'apply-staging'
            if args.mongo:
                report['persistence'] = stage_and_apply(database, report, promote=args.promote)
            else:
                candidates_path = ROOT / 'reports/external-candidates-local.jsonl'
                candidates_path.parent.mkdir(parents=True, exist_ok=True)
                with candidates_path.open('w', encoding='utf-8') as handle:
                    for c in report['candidates']:
                        handle.write(json.dumps(c, ensure_ascii=False) + '\n')
                if args.promote:
                    # Atomic rename into a separate local artifact; source catalog is never overwritten.
                    if args.local_output.resolve() == args.jsonl.resolve():
                        raise ValueError('--local-output must differ from input catalog')
                    args.local_output.parent.mkdir(parents=True, exist_ok=True)
                    temp = args.local_output.with_suffix('.jsonl.tmp')
                    with temp.open('w', encoding='utf-8') as handle:
                        for row in after:
                            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
                    temp.replace(args.local_output)
        write_json(args.output, report)
        print(json.dumps({'source': source, 'mode': report['mode'], **report['summary'], 'review_digest': report['review_digest']}))
    except Exception as exc:
        # Never echo driver errors/URIs, which can include credentials or server addresses.
        if args.mongo:
            raise SystemExit(f'Import failed ({type(exc).__name__}); connection details omitted') from None
        raise
    finally:
        if client is not None:
            client.close()
    return 0
