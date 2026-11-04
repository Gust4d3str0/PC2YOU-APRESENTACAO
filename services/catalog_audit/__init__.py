"""Read-only consistency audit, intentionally independent of Mongo and score thresholds."""
import re
from collections import Counter

from product_matching.normalization import normalize_text, normalize_brand, named_brands, capacity_values
from product_matching.matcher import gpu_models, CPU

VALID_CATEGORIES = {'cpu', 'gpu', 'motherboard', 'ram', 'kit-ram', 'storage', 'psu', 'case', 'cooler'}
MODEL_BRANDS = {'amd', 'intel', 'nvidia', 'asus', 'gigabyte', 'galax', 'msi', 'xfx', 'sapphire',
                'kingston', 'corsair', 'crucial', 'nzxt', 'noctua', 'deepcool', 'phanteks', 'seagate',
                'cooler master', 'lian li', 'rise mode', 'xpg', 'seasonic'}


def get_field(row, path):
    value = row
    for part in path.split('.'):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def cpu_models(text):
    text = normalize_text(text)
    # Slugs omit Core/AMD; suffixes remain part of the full token.
    return {''.join(m.groups(default='')) for m in CPU.finditer(text)}


def _category_from_id(cid):
    for pattern, category in [(r'^(?:intel|ryzen)-', 'cpu'), (r'^(?:rtx|gtx|rx)-', 'gpu'),
                              (r'^kit-ram-', 'kit-ram'), (r'^ram-', 'ram'),
                              (r'^(?:ssd|hdd)-', 'storage'), (r'^fonte-', 'psu'),
                              (r'^gabinete-', 'case'), (r'^cooler-', 'cooler'),
                              (r'^[abhxz]\d{3}', 'motherboard')]:
        if re.search(pattern, cid):
            return category
    return None


def _id_model(cid):
    parts = normalize_text(cid).split()
    if parts[:2] == ['cooler', 'cm']:
        parts[1] = 'coolermaster'
    # Only explicit commercial identities; generic IDs deliberately have no exact-name rule.
    if cid.startswith('cooler-') and any(b in cid for b in ('deepcool', 'cm-', 'noctua', 'nzxt', 'corsair')):
        return ''.join(parts[2:])
    if cid.startswith('gabinete-nzxt-'):
        return ''.join(parts[2:])
    if cid.startswith('gabinete-phanteks-'):
        return ''.join(parts[2:])
    if cid.startswith('gabinete-lian-li-'):
        return ''.join(parts[3:])
    return None


def audit_components(rows, references=None):
    references = references or {}
    buckets = {k: [] for k in ('id_name_conflicts', 'brand_conflicts', 'category_conflicts', 'spec_conflicts')}
    warnings = []
    def issue(bucket, row, code, field, expected=None, actual=None):
        buckets[bucket].append({'id': row.get('id'), 'code': code, 'field': field,
                                'expected': expected, 'actual': actual})
    for row in rows:
        cid, name, category = row.get('id', ''), row.get('name', ''), row.get('category')
        plain = normalize_text(name)
        specs, compat = row.get('technical_specs') or {}, row.get('compatibility') or {}
        category_id = _category_from_id(cid)
        if category not in VALID_CATEGORIES or category_id and category != category_id:
            issue('category_conflicts', row, 'id_category_mismatch', 'category', category_id, category)
        if category == 'cpu':
            expected, actual = cpu_models(cid), cpu_models(name)
            if expected and expected != actual:
                issue('id_name_conflicts', row, 'cpu_model_mismatch', 'name', sorted(expected), sorted(actual))
        if category == 'gpu':
            expected, actual = gpu_models(cid), gpu_models(name)
            if expected and expected != actual:
                issue('id_name_conflicts', row, 'gpu_variant_mismatch', 'name', sorted(expected), sorted(actual))
        exact = _id_model(cid)
        if exact and exact not in plain.replace(' ', ''):
            issue('id_name_conflicts', row, 'commercial_model_mismatch', 'name', exact, name)
        expected_brand = next((b for b in ('deepcool', 'noctua', 'nzxt', 'corsair', 'phanteks') if b in cid.split('-')), None)
        if cid.startswith('cooler-cm-'):
            expected_brand = 'cooler master'
        if cid.startswith('gabinete-lian-li-'):
            expected_brand = 'lian li'
        brand = normalize_brand(row.get('brand'))
        if expected_brand and brand != expected_brand:
            issue('brand_conflicts', row, 'id_brand_mismatch', 'brand', expected_brand, row.get('brand'))
        brands_in_name = named_brands(name) | {b for b in MODEL_BRANDS if re.search(r'\b' + re.escape(b) + r'\b', plain)}
        if category == 'gpu':
            brands_in_name -= {'amd', 'nvidia', 'intel'}
        brand_root = next((b for b in sorted(MODEL_BRANDS, key=len, reverse=True) if brand == b or brand.startswith(b + ' ')), brand)
        if brands_in_name and brand_root not in brands_in_name:
            issue('brand_conflicts', row, 'name_brand_mismatch', 'brand', sorted(brands_in_name), row.get('brand'))
        elif brand_root != brand and brand_root in MODEL_BRANDS:
            issue('brand_conflicts', row, 'series_in_manufacturer_field', 'brand', brand_root, row.get('brand'))
        if category in {'ram', 'kit-ram', 'storage'}:
            id_capacity, name_capacity = capacity_values(cid), capacity_values(name)
            spec_capacity = capacity_values(specs.get('capacity', ''))
            kits = re.findall(r'\b(\d+)\s*x\s*(\d+)gb\b', plain)
            if kits:
                name_capacity = {int(n) * int(size) for n, size in kits}
            for field, actual in [('name', name_capacity), ('technical_specs.capacity', spec_capacity)]:
                if id_capacity and actual != id_capacity:
                    issue('spec_conflicts', row, 'capacity_mismatch', field, sorted(map(str, id_capacity)), sorted(map(str, actual)))
        for key in ('socket', 'memory_type', 'form_factor', 'wattage', 'max_gpu_length_mm', 'max_tdp_watts', 'supported_form_factors'):
            if key in specs and key in compat and specs[key] != compat[key]:
                issue('spec_conflicts', row, 'spec_compatibility_mismatch', 'compatibility.' + key, specs[key], compat[key])
        ddr = re.search(r'\bddr[345]\b', normalize_text(cid))
        if ddr:
            for field, value in [('name', plain), ('technical_specs.memory_type', normalize_text(specs.get('memory_type'))),
                                 ('compatibility.memory_type', normalize_text(compat.get('memory_type')))]:
                stated = re.search(r'\bddr[345]\b', value)
                if stated and ddr[0] != stated[0]:
                    issue('spec_conflicts', row, 'memory_type_mismatch', field, ddr[0], value)
        watt = re.search(r'\b(\d+)w\b', normalize_text(cid)) if category == 'psu' else None
        if watt and (specs.get('wattage') != int(watt[1]) or compat.get('wattage') != int(watt[1])):
            issue('spec_conflicts', row, 'power_mismatch', 'technical_specs.wattage', int(watt[1]), specs.get('wattage'))
        name_watt = re.search(r'\b(\d+)w\b', plain)
        if watt and name_watt and watt[1] != name_watt[1]:
            issue('spec_conflicts', row, 'power_mismatch', 'name', watt[1], name_watt[1])
        if category in {'ram', 'kit-ram'}:
            frequency = re.search(r'-(\d{4,5})$', cid)
            expected_speed = frequency[1] if frequency else None
            name_speed = re.search(r'\b(\d{4,5})mhz\b', plain)
            spec_speed = re.search(r'(\d{4,5})', str(specs.get('speed', '')))
            speeds = {value[1] for value in (name_speed, spec_speed) if value}
            if expected_speed:
                speeds.add(expected_speed)
            if len(speeds) > 1:
                issue('spec_conflicts', row, 'frequency_mismatch', 'technical_specs.speed', expected_speed, sorted(speeds))
        if category == 'motherboard':
            chipset = re.search(r'\b([abhxz]\d{3}[a-z]*)\b', plain)
            known = normalize_text(specs.get('chipset'))
            # M in a commercial board name may describe Micro-ATX, not a different chipset.
            if chipset and known and chipset[1].removesuffix('m') != known.removesuffix('m'):
                issue('spec_conflicts', row, 'chipset_mismatch', 'technical_specs.chipset', chipset[1], known)
        if category == 'storage':
            expected_interface = 'nvme' if '-nvme-' in cid else 'sata' if '-sata-' in cid else None
            for field, text in [('name', plain), ('technical_specs.interface', normalize_text(specs.get('interface')))]:
                actual_interfaces = set(re.findall(r'\b(?:nvme|sata)\b', text))
                if expected_interface and actual_interfaces and actual_interfaces != {expected_interface}:
                    issue('spec_conflicts', row, 'storage_interface_mismatch', field, expected_interface, sorted(actual_interfaces))
        if category == 'cpu':
            cores, threads = specs.get('cores'), specs.get('threads')
            if not isinstance(cores, int) or not isinstance(threads, int) or cores <= 0 or threads < cores:
                issue('spec_conflicts', row, 'invalid_cpu_topology', 'technical_specs', 'positive cores and threads >= cores', [cores, threads])
        for field, expected in references.get(cid, {}).get('expected', {}).items():
            present, actual = get_field(row, field)
            if expected == {'absent': True}:
                mismatch = present
            else:
                mismatch = not present or actual != expected
            if mismatch:
                issue('spec_conflicts', row, 'manufacturer_reference_mismatch', field, expected, actual)
        if category in {'gpu', 'motherboard', 'psu', 'ram', 'kit-ram', 'storage', 'case', 'cooler'} and cid not in references:
            warnings.append({'id': cid, 'code': 'commercial_sku_not_independently_verified',
                             'note': 'Consistência interna não comprova SKU, dimensões ou todos os atributos do fabricante.'})
    ids = Counter(r.get('id') for r in rows)
    names = Counter(normalize_text(r.get('name')) for r in rows)
    duplicate_ids = [{'id': k, 'count': v} for k, v in ids.items() if v > 1]
    duplicate_names = [{'name': k, 'count': v, 'ids': [r['id'] for r in rows if normalize_text(r['name']) == k]}
                       for k, v in names.items() if v > 1]
    affected = {r['id'] for values in buckets.values() for r in values}
    affected |= {r['id'] for r in duplicate_ids}
    affected |= {cid for r in duplicate_names for cid in r['ids']}
    return {'total_components': len(rows), 'suspected': sorted(affected), 'duplicate_ids': duplicate_ids,
            'duplicate_names': duplicate_names, **buckets, 'warnings': warnings,
            'summary': {'suspected_components': len(affected), 'critical_conflicts': sum(map(len, buckets.values())) + len(duplicate_ids) + len(duplicate_names)},
            'categories': dict(Counter(r.get('category') for r in rows)),
            'verification_coverage': [{'id': row['id'], 'internal_checks': True,
                                      'manufacturer_fields': list(references.get(row['id'], {}).get('expected', {})),
                                      'sources': references.get(row['id'], {}).get('sources', []),
                                      'unverified_technical_fields': [k for k in (row.get('technical_specs') or {})
                                          if 'technical_specs.' + k not in references.get(row['id'], {}).get('expected', {})]}
                                     for row in rows]}
