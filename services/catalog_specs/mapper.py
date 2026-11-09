"""Missing-only proposals with exact provenance; no title-derived critical specs."""
from copy import deepcopy
import re
import json
from pathlib import Path

from .normalization import normalize_spec, capacity
from .identity import identity_scope

SOURCE_POLICY = json.loads(Path(__file__).with_name('source_policy.json').read_text(encoding='utf-8'))

# Category-specific: CPU memory controller limits never become motherboard limits.
ATTRIBUTES = {
    'cpu': {
        'compatibility.socket': ('COMPATIBLE_SOCKETS', 'SOCKET', 'CPU_SOCKET'),
        'technical_specs.cores': ('CPU_CORES_NUMBER', 'CORES_NUMBER', 'CORES'),
        'technical_specs.threads': ('CPU_THREADS_NUMBER', 'THREADS_NUMBER', 'THREADS'),
        'technical_specs.tdp_watts': ('TDP', 'THERMAL_DESIGN_POWER'),
    },
    'motherboard': {
        'compatibility.socket': ('COMPATIBLE_SOCKETS', 'SOCKET', 'CPU_SOCKET'),
        'compatibility.memory_type': ('SUPPORTED_RAM_MEMORY_TYPES', 'SUPPORTED_RAM_MEMORY_TYPE', 'MEMORY_TYPE', 'RAM_MEMORY_TYPE'),
        'technical_specs.memory_slots': ('RAM_MEMORY_SLOTS', 'MEMORY_SLOTS', 'MEMORY_SLOTS_NUMBER', 'RAM_MEMORY_SLOTS_NUMBER'),
        'technical_specs.max_memory_gb': ('MAX_RAM_MEMORY_SIZE_SUPPORTED', 'MAX_SUPPORTED_RAM_MEMORY_CAPACITY', 'MAX_MEMORY_SIZE'),
        'compatibility.form_factor': ('MOTHERBOARD_FORM_FACTOR', 'FORM_FACTOR'),
    },
    'ram': {
        'technical_specs.capacity': ('TOTAL_CAPACITY', 'CAPACITY', 'MEMORY_CAPACITY', 'RAM_MEMORY_MODULE_TOTAL_CAPACITY', 'MEMORY_SIZE'),
        'compatibility.memory_type': ('MEMORY_TYPE', 'RAM_MEMORY_TYPE', 'RAM_MEMORY_MODULE_TYPE', 'TECHNOLOGY'),
        'technical_specs.speed': ('MEMORY_SPEED', 'SPEED', 'RAM_MEMORY_SPEED', 'RAM_MEMORY_MODULE_SPEED'),
        'technical_specs.modules': ('MODULES_NUMBER', 'MODULES', 'MEMORY_MODULES_NUMBER', 'MEMORY_UNITS', 'RAM_MEMORY_MODULES'),
    },
    'gpu': {
        'technical_specs.memory': ('MEMORY_SIZE',),
        'technical_specs.length_mm': ('LENGTH',),
        'technical_specs.power_consumption_watts': ('TOTAL_GRAPHICS_POWER',),
        'compatibility.min_psu_watts': ('POWER_REQUIREMENT', 'MIN_POWER_SUPPLY'),
    },
    'psu': {'technical_specs.wattage': ('POWER', 'WATTAGE', 'OUTPUT_POWER', 'POWER_OUTPUT')},
    'case': {
        'compatibility.supported_form_factors': ('SUPPORTED_MOTHERBOARD_FORM_FACTORS', 'SUPPORTED_FORM_FACTORS', 'MOTHERBOARD_COMPATIBILITY'),
        'compatibility.max_gpu_length_mm': ('MAX_GPU_LENGTH', 'MAX_GRAPHICS_CARD_LENGTH'),
    },
    'storage': {
        'technical_specs.capacity': ('CAPACITY',),
        'technical_specs.interface': ('INTERFACE', 'INTERFACES', 'HARD_DRIVE_INTERFACE', 'CONNECTIVITY'),
    },
}
MIRRORS = {
    'cpu': ('socket',), 'motherboard': ('socket', 'memory_type', 'form_factor'),
    'ram': ('memory_type',), 'case': ('supported_form_factors', 'max_gpu_length_mm'),
    'psu': ('wattage',),
}


def get_path(row, path):
    value = row
    for part in path.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def is_missing(value):
    return value is None or value == '' or value == []


def writable(row, path):
    parent, key = path.split('.', 1)
    return (row.get(parent) is None or isinstance(row.get(parent), dict)) and is_missing(get_path(row, path))


def attribute_values(doc):
    attrs = doc.get('attributes') or {}
    if isinstance(attrs, list):
        attrs = {a['id']: a for a in attrs if isinstance(a, dict) and a.get('id')}
    if not isinstance(attrs, dict):
        return {}
    return {k: (v.get('value', v.get('value_name')) if isinstance(v, dict) else v) for k, v in attrs.items()}


def plan_backfill(row, sources=(), references=()):
    category = 'ram' if row.get('category') == 'kit-ram' else row.get('category')
    proposals, rejected = {}, []
    if row.get('spec_provenance') is not None and not isinstance(row['spec_provenance'], dict):
        return {'id': row.get('id'), 'name': row.get('name'), 'changes': [],
                'rejected': [{'reason': 'malformed_spec_provenance_requires_review'}]}

    def offer(path, incoming, source, **evidence):
        if not writable(row, path):
            return
        value = normalize_spec(path, incoming)
        if value is None:
            rejected.append({'field': path, 'source': source, 'reason': 'ambiguous_or_invalid_value', 'raw': incoming})
            return
        proposals.setdefault(path, []).append({'value': value, 'source': source, **evidence})

    external = row.get('external_enrichment')
    linked = external.get('mercado_livre') if isinstance(external, dict) else None
    docs = [linked] if isinstance(linked, dict) else []
    for doc in sources:
        if not isinstance(doc, dict) or not isinstance(doc.get('matches'), dict):
            continue
        match = doc['matches'].get(row.get('id'), {})
        if not isinstance(match, dict):
            continue
        if match.get('status') == 'matched' and not match.get('conflicts'):
            docs.append({**doc, 'match_status': 'matched', 'external_conflict': False,
                         'brand_variant': match.get('brand_variant', False)})
    seen = set()
    for doc in docs:
        pid = doc.get('product_id') or doc.get('catalog_product_id')
        if not pid or pid in seen:
            continue
        seen.add(pid)
        if doc.get('match_status') != 'matched' or doc.get('external_conflict'):
            rejected.append({'source': f'mercado_livre.{pid}', 'reason': 'unverified_or_conflicting_identity'})
            continue
        attrs = attribute_values(doc)
        domain = str(doc.get('domain_id') or '').upper()
        tokens = {'cpu': ('PROCESSORS',), 'motherboard': ('MOTHERBOARDS',), 'gpu': ('GRAPHICS_CARDS',),
                  'ram': ('RAM_MEMORY',), 'psu': ('POWER_SUPPL',), 'storage': ('HARD_DRIVES', 'SSD'),
                  'case': ('CASES', 'CABINETS')}.get(category, ())
        if domain and not any(token in domain for token in tokens):
            rejected.append({'source': f'mercado_livre.{pid}', 'reason': 'category_domain_conflict'})
            continue
        for path, ids in ATTRIBUTES.get(category, {}).items():
            # SKU dimensions and PSU requirements cannot migrate to a generic chip/family.
            if category in {'gpu', 'motherboard', 'case'} and identity_scope(row) == 'family' and path not in {'technical_specs.memory'}:
                continue
            if category == 'gpu' and path == 'technical_specs.length_mm':
                length = normalize_spec('length_mm', attrs.get('LENGTH'))
                width = normalize_spec('length_mm', attrs.get('WIDTH'))
                if length and width and width > length:
                    rejected.append({'field': path, 'source': f'mercado_livre.{pid}.LENGTH', 'reason': 'dimension_axes_inconsistent'})
                    continue
            for aid in ids:
                if aid in attrs:
                    blocked = next((b for b in SOURCE_POLICY['blocked_attributes']
                                    if b['product_id'] == pid and b['attribute'] == aid), None)
                    if blocked:
                        rejected.append({'field': path, 'source': f'mercado_livre.{pid}.{aid}',
                                         'reason': blocked['reason'], 'verification_source': blocked['source']})
                        continue
                    if category == 'gpu' and path == 'compatibility.min_psu_watts':
                        watts = normalize_spec(path, attrs[aid])
                        tgp = normalize_spec('power_consumption_watts', attrs.get('TOTAL_GRAPHICS_POWER'))
                        if watts is not None and (watts < 300 or (tgp and watts <= tgp)):
                            rejected.append({'field': path, 'source': f'mercado_livre.{pid}.{aid}', 'reason': 'power_requirement_semantics_ambiguous'})
                            continue
                    offer(path, attrs[aid], f'mercado_livre.{aid}', product_id=pid,
                          origin='external_enrichment.mercado_livre.attributes', raw=attrs[aid])

    # Current structured catalog fields can populate their canonical rule section.
    for key in MIRRORS.get(category, ()):
        for dst, src in [('compatibility', 'technical_specs'), ('technical_specs', 'compatibility')]:
            raw = get_path(row, f'{src}.{key}')
            if not is_missing(raw):
                offer(f'{dst}.{key}', raw, f'catalog.{src}.{key}')
    if category == 'gpu' and writable(row, 'technical_specs.memory') and get_path(row, 'technical_specs.vram'):
        offer('technical_specs.memory', get_path(row, 'technical_specs.vram'), 'catalog.technical_specs.vram')

    for reference in references:
        if reference.get('id') != row.get('id'):
            continue
        expected = reference.get('identity', {})
        if any(row.get(k) != v for k, v in expected.items()):
            continue
        for path, value in reference.get('fields', {}).items():
            if identity_scope(row) == 'family' and ((category == 'motherboard' and path in {
                    'technical_specs.memory_slots', 'technical_specs.max_memory_gb'}) or
                    (category == 'gpu' and path in {'technical_specs.length_mm', 'compatibility.min_psu_watts'})):
                continue
            offer(path, value, reference['source'], urls=reference.get('urls', []),
                  **{k: reference[k] for k in ('product_id', 'raw') if k in reference})

    # Module counts are parsed only from explicit NxMGB notation in catalog fields/name.
    if category == 'ram' and writable(row, 'technical_specs.modules'):
        match = re.search(r'\b(\d+)\s*[xX×]\s*(\d+)\s*GB\b', row.get('name', ''), re.I)
        if match:
            offer('technical_specs.modules', match.group(), 'catalog.name.explicit_modules')
    changes = []
    for path, candidates in proposals.items():
        unique = {repr(c['value']) for c in candidates}
        if len(unique) > 1:
            rejected.append({'field': path, 'reason': 'conflicting_sources', 'candidates': candidates})
            continue
        changes.append({'field': path, **candidates[0], 'corroborating_sources': candidates[1:]})
    resolved = {c['field']: c for c in changes}
    if category == 'ram':
        modules = get_path(row, 'technical_specs.modules') or resolved.get('technical_specs.modules', {}).get('value')
        total = get_path(row, 'technical_specs.capacity') or resolved.get('technical_specs.capacity', {}).get('value')
        kit = re.fullmatch(r'(\d+)x(\d+)GB', str(normalize_spec('modules', modules) or ''))
        if kit and capacity(total, gb=True) and int(kit[1]) * int(kit[2]) != capacity(total, gb=True):
            changes = [c for c in changes if c['field'] != 'technical_specs.modules']
            rejected.append({'field': 'technical_specs.modules', 'reason': 'module_capacity_conflict'})
    for key in MIRRORS.get(category, ()):
        for dst, src in [('compatibility', 'technical_specs'), ('technical_specs', 'compatibility')]:
            target, origin = f'{dst}.{key}', f'{src}.{key}'
            if target not in proposals and writable(row, target) and origin in resolved:
                changes.append({**resolved[origin], 'field': target,
                                'derived_from': origin})
    return {'id': row.get('id'), 'name': row.get('name'), 'changes': changes, 'rejected': rejected}


def apply_plan(row, plan, *, provenance=True):
    result = deepcopy(row)
    for change in plan['changes']:
        path = change['field']
        if not writable(result, path):
            continue
        section, key = path.split('.')
        if result.get(section) is None:
            result[section] = {}
        result[section][key] = change['value']
        if provenance and isinstance(result.get('spec_provenance', {}), dict):
            result.setdefault('spec_provenance', {}).setdefault(path.replace('.', '__'), deepcopy(change))
        elif provenance and result.get('spec_provenance') is None:
            result['spec_provenance'] = {path.replace('.', '__'): deepcopy(change)}
    return result


def missing_fields(row, sources=(), references=()):
    return {c['field']: c['value'] for c in plan_backfill(row, sources, references)['changes']}
