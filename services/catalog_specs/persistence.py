"""Atomic, missing-only persistence shared by maintenance and official enrichment."""

def write_mongo_plan(collection, row, plan):
    """Compare-and-set each field AND its provenance. A concurrent value always wins."""
    applied = []
    for change in plan['changes']:
        section, key = change['field'].split('.')
        predicate = {'_id': row['_id']}
        if row.get(section) is None:
            predicate[section] = None if section in row else {'$exists': False}
            update = {section: {key: change['value']}}
        else:
            predicate[section] = {'$type': 'object'}
            predicate[change['field']] = row[section][key] if key in row[section] else {'$exists': False}
            update = {change['field']: change['value']}
        provenance_key = change['field'].replace('.', '__')
        provenance = row.get('spec_provenance', {})
        if provenance is None:
            predicate['spec_provenance'] = None
            update['spec_provenance'] = {provenance_key: change}
        elif not isinstance(provenance, dict):
            continue
        elif provenance_key not in provenance:
            provenance_path = f'spec_provenance.{provenance_key}'
            predicate[provenance_path] = {'$exists': False}
            update[provenance_path] = change
        outcome = collection.update_one(predicate, {'$set': update}, upsert=False)
        if outcome.modified_count:
            applied.append(change['field'])
            if row.get(section) is None:
                row[section] = {}
            row[section][key] = change['value']
            if row.get('spec_provenance') is None:
                row['spec_provenance'] = {provenance_key: change}
    return applied
