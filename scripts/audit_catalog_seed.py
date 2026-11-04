"""Offline seed audit. Does not import database and cannot write to MongoDB."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_audit import audit_components
from catalog_audit.seed_io import load_seed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=Path, default=ROOT / 'api-catalogo/seed.py')
    parser.add_argument('--references', type=Path, default=ROOT / 'api-catalogo/seed_identity_reference.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--baseline-snapshot', type=Path, help='Compare to an archived seed JSON, without Mongo')
    args = parser.parse_args(argv)
    rows = load_seed(args.seed)
    refs = json.loads(args.references.read_text(encoding='utf-8')) if args.references.exists() else {}
    report = audit_components(rows, refs)
    if args.baseline_snapshot:
        before_rows = json.loads(args.baseline_snapshot.read_text(encoding='utf-8'))
        before = audit_components(before_rows, refs)
        old_ids, new_ids = set(before['suspected']), set(report['suspected'])
        old_by_id = {row['id']: row for row in before_rows}
        protected = ('id', 'prices', 'price_history', 'benchmark', 'image')
        unchanged = len(old_by_id) == len(rows) and all(row['id'] in old_by_id and
                    all(row[field] == old_by_id[row['id']][field] for field in protected) for row in rows)
        report['comparison'] = {'total_components': len(rows), 'suspected_before': len(old_ids),
                                'corrected_components': len(old_ids - new_ids), 'suspected_remaining': len(new_ids),
                                'new_suspects': sorted(new_ids - old_ids), 'duplicate_ids': len(report['duplicate_ids']),
                                'duplicate_names': len(report['duplicate_names']), 'protected_seed_fields_unchanged': unchanged}
    if args.snapshot and args.snapshot.exists():
        raise SystemExit('Snapshot already exists; choose another path to preserve the original.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.snapshot:
        args.snapshot.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary']))
    return int(bool(report['summary']['critical_conflicts']))


if __name__ == '__main__':
    raise SystemExit(main())
