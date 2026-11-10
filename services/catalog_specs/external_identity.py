"""Exact deterministic identities and bounded lookup keys. No fuzzy or LLM matching."""
from collections import defaultdict
import hashlib
import json
import re

from product_matching.normalization import normalize_brand, normalize_text
from .identity import identity_scope
from .normalization import normalize_spec


def category_of(row):
    return 'ram' if row.get('category') == 'kit-ram' else row.get('category')


def lookup_name(value):
    value = normalize_text(value)
    value = re.sub(r'\b(?:placa mae|placa de video|processador|memoria ram|geforce|gamer|lacrado|novo|box|oem)\b', ' ', value)
    value = re.sub(r'\b(?:amd|intel|nvidia)\b', ' ', value)
    value = re.sub(r'\bcore (?=i[3579])', '', value)
    return re.sub(r'[^a-z0-9]', '', value)


def cpu_model(value):
    value = normalize_text(value)
    match = re.search(r'\b((?:ryzen\s+[3579]\s+\d{4}[a-z0-9]*|i[3579]\s+\d{4,5}[a-z]*|core ultra\s+[3579]\s+\d{3}[a-z]*)(?:\s+plus)?)\b', value)
    return lookup_name(match[1]) if match else None


def gpu_model(value):
    match = re.search(r'\b((?:rtx|gtx|rx|arc)\s*[ab]?\d{3,4}(?:\s+(?:ti|super|xtx|xt|gre))*)\b', normalize_text(value))
    return lookup_name(match[1]) if match else None


def valid_mpn(value, category=None):
    """A wattage, capacity, chipset or DDR label cannot identify a commercial SKU."""
    key = lookup_name(value)
    if len(key) < 4 or not re.search(r'\d', key):
        return False
    if re.fullmatch(r'(?:\d+(?:x\d+)?(?:w|gb|tb|mhz)|ddr[2345]\d*|[abhxz]\d{3}[a-z]?|80(?:plus)?(?:gold|bronze|silver|platinum|titanium)|atx\d*)', key):
        return False
    if gpu_model(value) == key:
        return False
    return True


def _value(row, section, key):
    raw = (row.get(section) or {}).get(key)
    return normalize_spec(key, raw) or raw


def discriminators(row):
    cat = category_of(row)
    fields = {
        'gpu': [('technical_specs', 'memory')],
        'ram': [('technical_specs', 'capacity'), ('compatibility', 'memory_type'),
                ('technical_specs', 'speed'), ('technical_specs', 'modules'), ('technical_specs', 'cas_latency')],
        'storage': [('technical_specs', 'capacity')],
        'motherboard': [('compatibility', 'memory_type')],
        'psu': [('technical_specs', 'wattage')],
    }.get(cat, [])
    values = {}
    for section, key in fields:
        value = _value(row, section, key)
        if key == 'memory' and value:
            match = re.match(r'(\d+(?:\.\d+)?GB)', str(value))
            value = match[1] if match else value
        values[key] = value
    return values


def identity_name(row):
    cat, name = category_of(row), normalize_text(row.get('name', ''))
    brand = normalize_brand(row.get('brand', ''))
    if cat == 'cpu':
        return cpu_model(name) or lookup_name(name)
    name = re.sub(r'^' + re.escape(brand) + r'\b', '', name).strip()
    if cat == 'motherboard':
        name = re.sub(r'\b(?:lga\s*\d+|am[45]|ddr[45]|micro atx|matx|atx|mini itx|itx|placa mae)\b', ' ', name)
    if cat == 'storage':
        name = re.sub(r'\b\d+(?:[.,]\d+)?(?:gb|tb)\b', ' ', name)
    return lookup_name(name)


def identity_key(row):
    scope = identity_scope(row)
    scope = 'model' if category_of(row) == 'cpu' else scope
    payload = [category_of(row), normalize_brand(row.get('brand')), scope, identity_name(row), discriminators(row),
               row.get('identity_variant') or None]
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def internal_id(row):
    return f"{category_of(row)}-ext-{hashlib.sha256(identity_key(row).encode()).hexdigest()[:24]}"


def search_metadata(row):
    names = [row.get('name', ''), row.get('id', ''), *(row.get('aliases') or []),
             *[v for v in row.get('mpn') or [] if valid_mpn(v, category_of(row))]]
    keys = {lookup_name(name) for name in names if name}
    if category_of(row) == 'cpu':
        model = cpu_model(row.get('name', ''))
        if model:
            keys.add(model)
    if identity_scope(row) == 'family' and category_of(row) == 'psu':
        watts = _value(row, 'technical_specs', 'wattage')
        if watts:
            keys.update({lookup_name(f'{watts}W'), lookup_name(f'Fonte {watts}W')})
    if identity_scope(row) == 'family' and category_of(row) == 'motherboard':
        chipsets = set(re.findall(r'\b[abhxz]\d{3}[a-z]*\b', normalize_text(row.get('name', ''))))
        ddr = _value(row, 'compatibility', 'memory_type')
        if len(chipsets) == 1 and ddr:
            chip = next(iter(chipsets))
            keys.update({lookup_name(chip), lookup_name(chip + ' ' + ddr)})
    return {'normalized_name': lookup_name(row.get('name', '')), 'normalized_identity': identity_key(row),
            'model': identity_name(row), 'lookup_keys': sorted(keys - {''})}


def compatible_identity(left, right):
    if category_of(left) != category_of(right) or normalize_brand(left.get('brand')) != normalize_brand(right.get('brand')):
        return False
    if category_of(left) != 'cpu' and identity_scope(left) != identity_scope(right):
        return False
    # Never erase a known capacity, DDR generation, kit configuration or GPU suffix.
    a, b = discriminators(left), discriminators(right)
    if any(a[k] != b[k] for k in a if a[k] is not None and b[k] is not None):
        return False
    if category_of(left) == 'gpu' and gpu_model(left['name']) != gpu_model(right['name']):
        return False
    if category_of(left) in {'ram', 'storage', 'motherboard', 'gpu'} and any((a[k] is None) != (b[k] is None) for k in a):
        return False
    return True


class IdentityIndex:
    """Built once per offline import. No per-record full catalog scans."""
    def __init__(self, rows):
        self.rows = {r['id']: r for r in rows}
        self.names, self.mpns, self.external, self.classes = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
        for row in rows:
            self.add(row)

    def add(self, row):
        self.rows[row['id']] = row
        base = (category_of(row), normalize_brand(row.get('brand')))
        self.names[(*base, identity_name(row))].add(row['id'])
        self.classes[self.review_class(row)].add(row['id'])
        for value in row.get('mpn') or []:
            if valid_mpn(value, category_of(row)):
                self.mpns[(*base, lookup_name(value))].add(row['id'])
        for source, values in (row.get('external_ids') or {}).items():
            for value in values if isinstance(values, list) else [values]:
                self.external[(source, str(value))].add(row['id'])

    @staticmethod
    def review_class(row):
        cat, traits = category_of(row), discriminators(row)
        if cat == 'gpu':
            discriminator = (gpu_model(row.get('name', '')), traits.get('memory'))
        elif cat == 'psu':
            discriminator = traits.get('wattage')
        elif cat in {'storage', 'ram'}:
            discriminator = traits.get('capacity')
        else:
            chips = re.findall(r'\b[abhxz]\d{3}[a-z]*\b', normalize_text(row.get('name', '')))
            discriminator = (chips[0] if chips else '', traits.get('memory_type'))
        return cat, normalize_brand(row.get('brand')), discriminator

    def possible_dataset_duplicate(self, row):
        return category_of(row) != 'cpu' and bool(self.classes.get(self.review_class(row)))

    def resolve(self, row):
        base, ids, reason = (category_of(row), normalize_brand(row.get('brand'))), set(), 'exact_name'
        for source, values in (row.get('external_ids') or {}).items():
            for value in values if isinstance(values, list) else [values]:
                ids.update(self.external.get((source, str(value)), set()))
        if ids:
            reason = 'external_id'
        else:
            for value in row.get('mpn') or []:
                if valid_mpn(value, category_of(row)):
                    ids.update(self.mpns.get((*base, lookup_name(value)), set()))
            if ids:
                reason = 'mpn'
            else:
                ids = self.names.get((*base, identity_name(row)), set()).copy()
        matched = [self.rows[cid] for cid in ids if compatible_identity(row, self.rows[cid])]
        if reason in {'external_id', 'mpn'} and len(matched) != len(ids):
            return None, 'identifier_conflict'
        if len(matched) > 1:
            return None, 'ambiguous_identity'
        if matched:
            current = matched[0]
            if category_of(row) != 'cpu' and row.get('identity_variant') != current.get('identity_variant'):
                if reason in {'external_id', 'mpn'}:
                    return None, 'identifier_conflict'
                if row.get('identity_variant') and current.get('identity_variant'):
                    return None, 'distinct_variant'
                return None, 'ambiguous_variant'
            if reason == 'exact_name' and category_of(row) != 'cpu' and row.get('mpn') and current.get('mpn'):
                if not {lookup_name(x) for x in row['mpn']} & {lookup_name(x) for x in current['mpn']}:
                    return None, 'ambiguous_mpn'
            return current, reason
        return None, 'new'
