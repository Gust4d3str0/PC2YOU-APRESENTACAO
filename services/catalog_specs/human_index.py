"""Offline search projections of existing components; never creates catalog components."""
from collections import defaultdict
import hashlib
import json
import re

from .human_input import human_keys, parse_input, model_key
from .normalization import normalize_human_text, normalize_spec
from .family_bounds import summarize


def family_projections(rows):
    boards, gpus = defaultdict(list), defaultdict(list)
    for row in rows:
        category = row.get('category')
        if category not in {'motherboard', 'gpu'}:
            continue
        parsed = parse_input(row.get('name', ''), category)
        f = parsed['features']
        if category == 'gpu' and model_key(f, 'gpu'):
            gpus[model_key(f, 'gpu')].append(row)
        if category == 'motherboard' and f.get('chipset'):
            ddr = normalize_spec('memory_type', (row.get('compatibility') or {}).get('memory_type'))
            boards[f'board:{f["chipset"]}:'].append(row)
            if ddr:
                boards[f'board:{f["chipset"]}:{ddr}'].append(row)
    projections = []
    for key, members in boards.items():
        fields = {}
        # No slot counts, max RAM, GPU dimensions or connector layouts in a family view.
        for field in ('socket', 'memory_type', 'form_factor'):
            values = [normalize_spec(field, (r.get('compatibility') or {}).get(field)) for r in members]
            if values and all(v is not None for v in values) and all(v == values[0] for v in values):
                fields['compatibility.' + field] = values[0]
        projections.append({'key': key, 'category': 'motherboard', 'fields': fields, 'members': len(members),
                            'bounds': summarize(members, 'motherboard'),
                            'method': 'complete_catalog_unanimous_fields', 'version': 2})
    for key, members in gpus.items():
        f = parse_input(members[0]['name'], 'gpu')['features']
        name = ' '.join(p for p in (f['series'].upper(), f['number'], f.get('suffix')) if p)
        memories = []
        for row in members:
            memory = re.match(r'\s*(\d+(?:\.\d+)?\s*GB)', str((row.get('technical_specs') or {}).get('memory', '')), re.I)
            if memory:
                memories.append(normalize_spec('capacity', memory[1]))
        projections.append({'key': key, 'category': 'gpu', 'model': name, 'fields': {}, 'members': len(members),
                            'vram_options': sorted(set(memories)), 'bounds': summarize(members, 'gpu'),
                            'method': 'model_presence_only_no_physical_specs', 'version': 2})
    return projections


def build_human_index(database):
    collection = database.components
    before = collection.count_documents({})
    database.catalog_human_index_meta.update_one({'_id': 'active'}, {'$set': {'valid': False}}, upsert=True)
    collection.create_index([('category', 1), ('human_lookup_keys', 1)], name='ix_catalog_human_lookup_keys')
    database.catalog_human_families.create_index('key', unique=True, name='uq_catalog_human_family_key')
    rows = list(collection.find({}, {'_id': 0}))  # Explicit offline maintenance only.
    def fingerprint(items):
        digest=hashlib.sha256()
        for item in sorted(items,key=lambda r:r['id']):
            facts={key:item.get(key) for key in ('id','name','category','brand','technical_specs','compatibility','aliases','mpn','identity_scope')}
            digest.update(json.dumps(facts,sort_keys=True,ensure_ascii=True).encode())
        return digest.hexdigest()
    source_hash=fingerprint(rows)
    changed = 0
    for row in rows:
        keys = human_keys(row)
        if row.get('human_lookup_keys') == keys:
            continue
        query = {'id': row['id'], 'name': row['name']}
        changed += collection.update_one(query, {'$set': {'human_lookup_keys': keys}}).modified_count
    projections = family_projections(rows)
    generation = hashlib.sha256(json.dumps(sorted(projections, key=lambda p: p['key']),sort_keys=True).encode()).hexdigest()
    for projection in projections:
        projection['generation'] = generation
        database.catalog_human_families.update_one({'key': projection['key']}, {'$set': projection}, upsert=True)
    after = collection.count_documents({})
    if before != after or fingerprint(collection.find({}, {'_id':0})) != source_hash:
        raise RuntimeError('Catalog changed concurrently during offline indexing; rerun the job')
    database.catalog_human_index_meta.update_one({'_id': 'active'}, {'$set': {'version': 1, 'valid': True, 'generation': generation,
        'components': before, 'projections': len(projections)}}, upsert=True)
    return {'before': before, 'after': after, 'keys_updated': changed, 'family_projections': len(projections),
            'catalog_components_added': 0, 'technical_specs_updated': 0, 'technical_snapshot_sha256':source_hash}
