"""Bounded candidate scoring, conservative family views and explicit derived fields."""
from copy import deepcopy
import re

from .human_input import parse_input, cpu_features, gpu_features, model_key
from .normalization import normalize_human_text, normalize_spec
from .external_identity import lookup_name, category_of, valid_mpn
from .identity import identity_scope
from .family_bounds import usable, proves
from product_matching.normalization import normalize_brand

LIMIT = 32
FAMILY_FIELDS = {'cpu': None, 'gpu': {'technical_specs.memory', 'compatibility.min_psu_watts'},
                 'motherboard': {'compatibility.socket', 'compatibility.memory_type', 'compatibility.form_factor'},
                 'psu': {'technical_specs.wattage'}, 'case': {'compatibility.supported_form_factors'},
                 'ram': {'technical_specs.capacity', 'technical_specs.speed', 'technical_specs.modules', 'compatibility.memory_type'},
                 'storage': {'technical_specs.capacity', 'technical_specs.interface'}}


def family_key(parsed):
    f = parsed['features']
    if parsed['category'] == 'motherboard' and f.get('chipset'):
        return f'board:{f["chipset"]}:{f.get("memory_type", "")}'
    if parsed['category'] == 'gpu':
        return model_key(f, 'gpu')
    return None


def candidate_query(parsed):
    category = parsed['category']
    exact = {'category': {'$in': ['ram', 'kit-ram'] if category == 'ram' else [category]},
             'lookup_keys': lookup_name(parsed['normalized'])}
    return exact


def mongo_bundle(collection, parsed):
    """At most 32 exact/feature candidates. Overflow is explicit, never a hidden first pick."""
    rows = list(collection.find(candidate_query(parsed), {'_id': 0}).limit(LIMIT + 1))
    overflow = len(rows) > LIMIT
    if not rows and parsed['category'] == 'cpu' and model_key(parsed['features'], 'cpu'):
        rows = list(collection.find({'category': 'cpu', 'human_lookup_keys': model_key(parsed['features'], 'cpu')}, {'_id': 0}).limit(LIMIT + 1))
        overflow = len(rows) > LIMIT
    if not rows and parsed['generic'] and parsed['category'] in {'gpu', 'motherboard'} and family_key(parsed):
        rows = list(collection.find({'category': parsed['category'], 'human_lookup_keys': 'family:' + family_key(parsed)}, {'_id': 0}).limit(LIMIT + 1))
        overflow = len(rows) > LIMIT
    projection = None
    key = family_key(parsed)
    if key and parsed['generic']:
        meta = collection.database.catalog_human_index_meta.find_one({'_id': 'active'})
        if meta and meta.get('valid'):
            projection = collection.database.catalog_human_families.find_one({'key': key, 'generation': meta.get('generation')}, {'_id': 0})
    return {'candidates': rows[:LIMIT], 'overflow': overflow, 'family': projection}


def _explicit_conflicts(parsed, row):
    errors = []
    for section, values in [('technical_specs', parsed['specifications']), ('compatibility', parsed['compatibility'])]:
        stored = row.get(section) or {}
        for key, value in values.items():
            allowed = FAMILY_FIELDS.get(parsed['category']) if identity_scope(row) == 'family' else None
            if allowed is not None and f'{section}.{key}' not in allowed:
                continue
            other = stored.get(key)
            if other is None:
                continue
            if key == 'memory':
                other = re.match(r'\s*(\d+(?:\.\d+)?\s*GB)', str(other), re.I)
                other = normalize_spec('capacity', other[1]) if other else None
            else:
                other = normalize_spec(key, other) or other
            if other is not None and value != other:
                errors.append('conflicting_' + key)
    return errors


def score_candidate(parsed, row):
    category, f = parsed['category'], parsed['features']
    rejected, evidence, score = [], [], 0
    if category_of(row) != category:
        return 0, [], ['category_conflict']
    literal_id = parsed['original'].strip().casefold() == str(row.get('id', '')).casefold()
    names = [row.get('name', ''), *(row.get('aliases') or [])]
    exact = lookup_name(parsed['normalized']) in {lookup_name(normalize_human_text(n)) for n in names if n}
    mpn = lookup_name(parsed['normalized']) in {lookup_name(m) for m in row.get('mpn') or [] if valid_mpn(m, category)}
    if literal_id:
        score += 1000
        evidence.append('literal_catalog_id')
    if mpn:
        score += 1000
        evidence.append('exact_mpn')
    if exact:
        score += 200
        evidence.append('exact_name_or_alias')
    scope = identity_scope(row)
    explicit_brands = set(f.get('brands') or []) - {'amd', 'intel', 'nvidia'}
    if scope == 'sku' and explicit_brands and normalize_brand(row.get('brand')) not in explicit_brands:
        rejected.append('manufacturer_conflict')
    if category in {'cpu', 'gpu'} and f.get('number'):
        candidate = (cpu_features(normalize_human_text(row['name']), bare=False)[0] if category == 'cpu'
                     else gpu_features(normalize_human_text(row['name']))[0])
        for key in ('number', 'suffix', 'series', 'vendor', 'tier', 'family'):
            if f.get(key) is not None and f[key] != candidate.get(key):
                rejected.append('model_conflict_' + key)
        if not rejected:
            score += 150
            evidence.extend(['exact_model', 'exact_suffix'])
        vendors = set(f.get('brands') or [])
        if category == 'cpu' and vendors & {'amd', 'intel'} and normalize_brand(row.get('brand')) not in vendors:
            rejected.append('manufacturer_conflict')
    if category == 'gpu' and parsed['generic'] and scope == 'sku' and not literal_id and not mpn:
        rejected.append('generic_input_cannot_select_sku')
    if category in {'ram', 'psu', 'storage', 'case', 'motherboard'} and parsed['generic'] and scope == 'sku' and not literal_id and not mpn:
        rejected.append('generic_input_cannot_select_sku')
    if not (literal_id or mpn or exact):
        if category == 'cpu' and f.get('number') and parsed['generic']:
            evidence.append('omitted_tier_candidate_lookup')
        elif scope == 'family' and category == 'gpu' and parsed['generic'] and f.get('number'):
            evidence.append('exact_gpu_family_model_and_suffix')
        elif scope == 'family' and category == 'motherboard' and parsed['generic']:
            chips = re.findall(r'\b[abhxz]\d{3}[a-z]*\b', normalize_human_text(row['name']))
            if f.get('chipset', '').lower() not in chips:
                rejected.append('chipset_conflict')
            else:
                score += 150
                evidence.append('explicit_chipset_family')
        else:
            rejected.append('no_exact_identity_evidence')
    rejected.extend(_explicit_conflicts(parsed, row))
    score += 10 * len(parsed['specifications']) + 10 * len(parsed['compatibility'])
    return score, evidence, sorted(set(rejected))


def _catalog_component(row, parsed):
    scope = identity_scope(row)
    scope = 'model' if parsed['category'] == 'cpu' else scope
    specs, compat, sources = {}, {}, {}
    allowed = FAMILY_FIELDS.get(parsed['category']) if scope == 'family' else None
    for section, destination in [('technical_specs', specs), ('compatibility', compat)]:
        for key, value in (row.get(section) or {}).items():
            path = f'{section}.{key}'
            if value is not None and (allowed is None or path in allowed):
                destination[key] = deepcopy(value)
                sources[path] = 'catalog'
    # Explicit facts may fill an absent field, never contradict a catalog value.
    for section, destination in [('technical_specs', specs), ('compatibility', compat)]:
        for key, value in (parsed['specifications'] if section == 'technical_specs' else parsed['compatibility']).items():
            if key not in destination:
                destination[key] = value
                sources[f'{section}.{key}'] = 'user_text'
    return {'name': row['name'], 'category': parsed['category'], 'source': 'catalog', 'catalog_id': row['id'],
            'resolution_scope': scope, 'specifications': specs, 'compatibility': compat, 'field_sources': sources,
            '_catalog_category': row['category'], '_support_complete': True}


def attach_family_bounds(result, parsed, projection):
    """Expose offline family statistics on a family-scope component, never as scalar specs."""
    bounds = (projection or {}).get('bounds')
    if (not parsed['generic'] or parsed['category'] not in {'motherboard', 'gpu'}
            or result.get('resolution_scope') != 'family' or not isinstance(bounds, dict)):
        return result
    kept = {path: stats for path, stats in bounds.items() if usable(stats)}
    if not kept:
        return result
    result['family_bounds'] = deepcopy(kept)
    result['_family_label'] = projection.get('model') or projection.get('key')
    for path, stats in kept.items():
        section, key = path.split('.')
        values = result['specifications'] if section == 'technical_specs' else result['compatibility']
        if key not in values and proves(stats, 'catalog_family_bound'):
            result['field_sources'][path] = 'catalog_family_bound'
    return result


def resolve_input(parsed, bundle):
    trace = {'input': parsed['original'], 'normalized': parsed['normalized'], 'features': parsed['features'],
             'candidates': [], 'overflow': bundle.get('overflow', False), 'rejections': list(parsed['errors']),
             'family_evidence': bundle.get('family')}
    unknown = {'name': parsed['original'], 'category': parsed['category'], 'source': 'user', 'catalog_id': None,
               'resolution_scope': 'unresolved', 'specifications': {}, 'compatibility': {}, 'field_sources': {}}
    if parsed['errors']:
        return unknown, trace
    scored = []
    for row in bundle.get('candidates', [])[:LIMIT]:
        score, evidence, rejections = score_candidate(parsed, row)
        trace['candidates'].append({'catalog_id': row['id'], 'scope': identity_scope(row), 'score': score,
                                    'evidence': evidence, 'rejections': rejections})
        if not rejections:
            scored.append((score, row))
    if not trace['overflow'] and scored:
        best = max(score for score, _ in scored)
        winners = [row for score, row in scored if score == best]
        if len(winners) == 1:
            resolved = _catalog_component(winners[0], parsed)
            projection = bundle.get('family') or {}
            if parsed['category'] == 'gpu' and resolved['resolution_scope'] == 'family' and not parsed['features'].get('vram') and len(projection.get('vram_options', [])) > 1:
                resolved['specifications'].pop('memory', None)
                resolved['field_sources'].pop('technical_specs.memory', None)
            return attach_family_bounds(resolved, parsed, projection), trace
        trace['rejections'].append('ambiguous_best_candidates')
    elif trace['overflow']:
        trace['rejections'].append('candidate_limit_exceeded')
    specs, compat, field_sources = deepcopy(parsed['specifications']), deepcopy(parsed['compatibility']), deepcopy(parsed['field_sources'])
    projection = bundle.get('family')
    scope = 'generic'
    if projection and parsed['generic']:
        if parsed['category'] == 'motherboard':
            for path, value in projection.get('fields', {}).items():
                section, key = path.split('.')
                explicit = parsed['specifications'] if section == 'technical_specs' else parsed['compatibility']
                if key in explicit and explicit[key] != value:
                    trace['rejections'].append('family_field_conflict_' + key)
                    return unknown, trace
            for path, value in projection.get('fields', {}).items():
                section, key = path.split('.')
                destination = specs if section == 'technical_specs' else compat
                if key not in destination:
                    destination[key] = value
                    field_sources[path] = 'catalog_family_consensus'
            scope = 'family'
        elif parsed['category'] == 'gpu':
            scope = 'family'
            specs['model'] = projection['model']
            field_sources['technical_specs.model'] = 'catalog_family_consensus'
    if specs or compat:
        derived = {'name': parsed['original'], 'category': parsed['category'], 'source': 'derived', 'catalog_id': None,
                   'resolution_scope': scope, 'specifications': specs, 'compatibility': compat,
                   'field_sources': field_sources, '_support_complete': parsed.get('support_complete', False)}
        return attach_family_bounds(derived, parsed, projection), trace
    trace['rejections'].append('no_unique_identity_or_explicit_technical_fields')
    return unknown, trace


def resolve_human(name, category, catalog):
    parsed = parse_input(name, category)
    bundle = catalog.human_candidates(category, name) if not parsed['errors'] else {'candidates': []}
    result, trace = resolve_input(parsed, bundle)
    trace.update(resolution={k: v for k, v in result.items() if not k.startswith('_')},
                 derived_fields={p: v for p, v in result.get('field_sources', {}).items() if v == 'user_text'})
    return result, trace
