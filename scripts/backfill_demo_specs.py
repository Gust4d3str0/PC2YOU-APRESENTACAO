"""Audit/backfill every component. Dry-run by default; missing-only atomic Mongo updates.

No deletes, replacements, inserts, upserts, scraping or AI. Credentials never appear in reports.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_specs import plan_backfill, apply_plan
from catalog_specs.persistence import write_mongo_plan


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def repository_references():
    from catalog_audit.seed_io import load_seed
    refs = []
    groups = [('api-catalogo/seed.py', load_seed(ROOT / 'api-catalogo/seed.py'))]
    for name in ('catalog_enrichment_v1.json', 'catalog_coverage_v2.json'):
        path = ROOT / 'api-catalogo' / name
        if path.exists():
            groups.append((f'api-catalogo/{name}', json.loads(path.read_text(encoding='utf-8'))))
    for source, rows in groups:
        for row in rows:
            refs.append({'id': row['id'], 'identity': {k: row[k] for k in ('name', 'category', 'brand')},
                         'fields': {f'{section}.{key}': value for section in ('technical_specs', 'compatibility')
                                    for key, value in row.get(section, {}).items()}, 'source': source})
    curated = ROOT / 'api-catalogo/catalog_spec_references.json'
    if curated.exists():
        refs.extend(json.loads(curated.read_text(encoding='utf-8')))
    return refs


def missing_fields(row):
    return {c['field']: c['value'] for c in plan_backfill(row, references=repository_references())['changes']}


def backfill_jsonl(path, apply=False, sources=None, references=None):
    path = Path(path)
    sources = sources if sources is not None else read_jsonl(ROOT / 'demo-data/external_product_enrichment.jsonl')
    references = references if references is not None else repository_references()
    lines, plans = path.read_text(encoding='utf-8').splitlines(keepends=True), []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        row = json.loads(line)
        plan = plan_backfill(row, sources, references)
        if plan['changes']:
            plans.append(plan)
            lines[index] = json.dumps(apply_plan(row, plan), ensure_ascii=False) + '\n'
    if apply and plans:
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(''.join(lines), encoding='utf-8')
        temporary.replace(path)
    return plans


def backfill_collection(collection, apply=False, sources=(), references=None):
    references = references if references is not None else repository_references()
    plans = []
    for row in collection.find({}):
        plan = plan_backfill(row, sources, references)
        if not plan['changes']:
            continue
        if apply:
            plan['applied_fields'] = write_mongo_plan(collection, row, plan)
        plans.append(plan)
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jsonl', type=Path, default=ROOT / 'demo-data/components.jsonl')
    parser.add_argument('--sources-jsonl', type=Path, default=ROOT / 'demo-data/external_product_enrichment.jsonl')
    parser.add_argument('--mongo-uri', help='Use MONGO_URI to avoid exposing credentials in shell history')
    parser.add_argument('--mongo', action='store_true', help='Use MONGO_URI from process environment')
    parser.add_argument('--db', default=os.getenv('MONGO_DB', 'orcapc_catalog'))
    parser.add_argument('--report', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.mongo or args.mongo_uri:
        from pymongo import MongoClient
        uri = args.mongo_uri or os.getenv('MONGO_URI')
        if not uri:
            parser.error('--mongo requires MONGO_URI')
        try:
            with MongoClient(uri, serverSelectionTimeoutMS=10000) as client:
                db = client[args.db]
                plans = backfill_collection(db.components, args.apply, list(db.external_product_enrichment.find({})))
        except Exception as exc:
            raise SystemExit(f'MongoDB operation failed ({type(exc).__name__}); credentials omitted') from None
    else:
        sources = read_jsonl(args.sources_jsonl) if args.sources_jsonl.exists() else []
        plans = backfill_jsonl(args.jsonl, args.apply, sources)
    report = {'mode': 'apply' if args.apply else 'dry-run', 'components': len(plans),
              'fields': sum(len(p['changes']) for p in plans), 'changes': plans}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
