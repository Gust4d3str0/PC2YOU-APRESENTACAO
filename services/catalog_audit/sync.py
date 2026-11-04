"""Compare-and-set updates restricted to audited identity fields; no inserts/deletes."""
from . import audit_components, get_field

ALLOWED = {'name', 'brand', 'category', 'description'}


def validate_manifest(manifest, seed_rows, references):
    if audit_components(seed_rows, references)['summary']['critical_conflicts']:
        raise ValueError('Seed still has critical conflicts')
    by_id = {row['id']: row for row in seed_rows}
    seen = set()
    for entry in manifest['components']:
        cid = entry['id']
        if cid in seen or cid not in by_id:
            raise ValueError('Duplicate or missing component in correction manifest')
        seen.add(cid)
        paths = set()
        for change in entry['changes']:
            path = change['path']
            parts = path.split('.')
            if path in paths or any(not part or not part.replace('_', '').isalnum() for part in parts):
                raise ValueError('Invalid correction path')
            if path not in ALLOWED and not (len(parts) >= 2 and parts[0] in {'technical_specs', 'compatibility'}):
                raise ValueError('Correction targets protected data')
            paths.add(path)
            present, value = get_field(by_id[cid], path)
            if present != change['after_exists'] or present and value != change['after']:
                raise ValueError('Correction manifest does not match current seed')


def sync_components(collection, manifest, *, apply=False):
    report = {'mode': 'apply' if apply else 'dry-run', 'updated': 0, 'would_update': 0,
              'unchanged': 0, 'skipped': [], 'changes': []}
    for entry in manifest['components']:
        cid = entry['id']
        matches = list(collection.find({'id': cid}).limit(2))
        if len(matches) != 1:
            report['skipped'].append({'id': cid, 'reason': 'missing' if not matches else 'duplicate_id'})
            continue
        row = matches[0]
        selector, sets, unsets, changes = {'_id': row['_id'], 'id': cid}, {}, {}, []
        divergent = []
        for change in entry['changes']:
            path = change['path']
            present, value = get_field(row, path)
            if present == change['after_exists'] and (not present or value == change['after']):
                continue
            if present != change['before_exists'] or present and value != change['before']:
                divergent.append(path)
                continue
            selector[path] = {'$eq': value, '$exists': True} if present else {'$exists': False}
            if change['after_exists']:
                sets[path] = change['after']
            else:
                unsets[path] = ''
            changes.append(path)
        if divergent:
            report['skipped'].append({'id': cid, 'reason': 'divergent_current_value', 'fields': divergent})
            continue
        if not changes:
            report['unchanged'] += 1
            continue
        report['would_update'] += 1
        report['changes'].append({'id': cid, 'fields': changes})
        if apply:
            update = {}
            if sets:
                update['$set'] = sets
            if unsets:
                update['$unset'] = unsets
            result = collection.update_one(selector, update)
            if result.matched_count:
                report['updated'] += result.modified_count
            else:
                report['skipped'].append({'id': cid, 'reason': 'concurrent_change'})
    return report
