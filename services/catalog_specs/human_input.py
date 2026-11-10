"""Explicit human-text features. No catalog IO, inferred specifications or LLMs."""
import re

from .normalization import normalize_human_text, normalize_spec, capacity, number
from product_matching.normalization import named_brands

CPU = re.compile(r'\b(?:(ryzen)\s*(?:([3579])\s+)?(\d{4})([a-z0-9]*)|(i[3579])\s+(\d{4,5})([a-z]*)|(core ultra)\s+([3579])\s+(\d{3})([a-z]*))(\s+plus)?\b')
GPU = re.compile(r'\b(rtx|gtx|rx|arc)\s+([ab]?\d{3,4})(?:\s+(ti\s*super|super|ti|xtx|xt|gre))?\b')
CAPACITY = re.compile(r'(?<![\w.])(\d+(?:[.,]\d+)?)\s*(gb|tb)\b')
FORM = re.compile(r'\b(e[-\s]*atx|atx|matx|itx)\b')


def cpu_features(value, *, bare=True):
    match = CPU.search(value)
    if match:
        r, tier, num, suffix, itier, inum, isuffix, ultra, utier, unum, usuffix, plus = match.groups()
        return {'vendor': 'amd' if r else 'intel', 'family': 'ryzen' if r else 'ultra' if ultra else 'core',
                'tier': tier or utier or (itier[1:] if itier else None), 'number': num or inum or unum,
                'suffix': (suffix or isuffix or usuffix or '').upper() + (' PLUS' if plus else '')}, match.span()
    match = re.fullmatch(r'(\d{4,5})(x3d|xt|gt|x|g|kf|ks|k|f|t|s)?', value) if bare else None
    if match:
        return {'number': match[1], 'suffix': (match[2] or '').upper()}, match.span()
    return {}, None


def gpu_features(value):
    match = GPU.search(value)
    return ({'series': match[1], 'number': match[2], 'suffix': ' '.join((match[3] or '').upper().split())}, match.span()) if match else ({}, None)


def model_key(features, category):
    if not features.get('number'):
        return None
    prefix = features.get('series', '') if category == 'gpu' else ''
    return f'{category}:{prefix}:{features["number"]}:{features.get("suffix", "").lower().replace(" ", "")}'


def parse_input(original, category):
    normalized = normalize_human_text(original)
    result = {'original': original, 'normalized': normalized, 'category': category, 'features': {},
              'specifications': {}, 'compatibility': {}, 'field_sources': {}, 'errors': [], 'generic': False}
    f, specs, compat = result['features'], result['specifications'], result['compatibility']
    consumed = []
    primary = re.sub(r'^(?:(?:amd|intel|nvidia|processador|geforce|radeon)\s+)+', '', normalized)
    primary = re.sub(r'^core\s+(?=i[3579])', '', primary)
    cpu_span, gpu_span = cpu_features(primary, bare=False)[1], gpu_features(primary)[1]
    if (category != 'cpu' and cpu_span and cpu_span[0] == 0) or (category != 'gpu' and gpu_span and gpu_span[0] == 0):
        result['errors'].append('category_conflict')

    def record(path, value):
        if value is not None:
            section, key = path.split('.')
            target = specs if section == 'technical_specs' else compat
            if key in target and target[key] != value:
                result['errors'].append('conflicting_' + key)
            target[key] = value
            result['field_sources'][path] = 'user_text'

    def matches(pattern, key, convert=lambda m: m[1], flags=0):
        found = list(re.finditer(pattern, normalized, flags))
        values = [convert(m) for m in found]
        unique = list(dict.fromkeys(v for v in values if v is not None))
        if len(unique) > 1:
            result['errors'].append('conflicting_' + key)
        if len(unique) == 1:
            f[key] = unique[0]
        consumed.extend(m.span() for m in found)
        return unique[0] if len(unique) == 1 else None

    if re.search(r'\b(?:ou|or|talvez|nao|not|sem)\b|\d\s*[-/]\s*\d', normalized):
        result['errors'].append('alternative_range_or_negation')
    brands = named_brands(normalized)
    f['brands'] = sorted(brands)
    if category == 'cpu':
        features, span = cpu_features(normalized)
        f.update(features)
        if span:
            consumed.append(span)
        if len(list(CPU.finditer(normalized))) > 1:
            result['errors'].append('multiple_models')
        vendors = brands & {'amd', 'intel'}
        if features.get('vendor') and ((vendors and vendors != {features['vendor']}) or brands - {'amd', 'intel'}):
            result['errors'].append('manufacturer_conflict')
    if category == 'gpu':
        features, span = gpu_features(normalized)
        f.update(features)
        if span:
            consumed.append(span)
        if len(list(GPU.finditer(normalized))) > 1:
            result['errors'].append('multiple_models')
        memory = matches(r'(?<!\w)(\d+)\s*gb\b', 'vram', lambda m: f'{int(m[1])}GB')
        record('technical_specs.memory', memory)
        length = matches(r'\b(?:comprimento|length)\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)\b',
                         'length_mm', lambda m: normalize_spec('length_mm', m[1] + m[2]))
        record('technical_specs.length_mm', length)
        if ('amd' in brands and f.get('series') in {'rtx', 'gtx'}) or ('nvidia' in brands and f.get('series') == 'rx'):
            result['errors'].append('manufacturer_conflict')
    if category in {'ram', 'storage'}:
        kits = list(re.finditer(r'\b(\d+)\s*x\s*(\d+)\s*gb\b', normalized)) if category == 'ram' else []
        if kits:
            if len(kits) != 1:
                result['errors'].append('multiple_kits')
            kit = kits[0]
            qty, each = int(kit[1]), int(kit[2])
            if not 1 <= qty <= 16 or not 1 <= each <= 256:
                result['errors'].append('invalid_kit')
            f.update(modules=f'{qty}x{each}GB', module_capacity=f'{each}GB', capacity=f'{qty * each}GB')
            record('technical_specs.modules', f['modules'])
            consumed.extend(m.span() for m in kits)
        caps = [m for m in CAPACITY.finditer(normalized) if not any(a <= m.start() < b for a, b in consumed)]
        values = {capacity(m[1] + m[2]) for m in caps}
        if len(values) > 1 or (values and f.get('capacity') and f['capacity'] not in values):
            result['errors'].append('conflicting_capacity')
        if len(values) == 1:
            f['capacity'] = next(iter(values))
        consumed.extend(m.span() for m in caps)
        record('technical_specs.capacity', f.get('capacity'))
    if category in {'ram', 'motherboard'}:
        ddr = matches(r'\bddr([2345])\b', 'memory_type', lambda m: 'DDR' + m[1])
        record('compatibility.memory_type', ddr)
        if category == 'ram':
            record('technical_specs.memory_type', ddr)
            speed = matches(r'(?<![\w.])(\d{3,5})\s*(?:mhz|mt/s)?\b', 'speed', lambda m: normalize_spec('speed', m[1]))
            cl = matches(r'\bcl\s*(\d{1,3})\b', 'cas_latency', lambda m: int(m[1]))
            record('technical_specs.speed', speed)
            record('technical_specs.cas_latency', cl)
    if category == 'psu':
        watts = matches(r'(?<!\w)(\d{2,4})\s*(?:w|watts?)\b', 'wattage', lambda m: int(m[1]))
        if watts and watts > 3000:
            result['errors'].append('invalid_wattage')
        record('technical_specs.wattage', watts)
        rating = matches(r'\b80\s*\+?\s*(?:plus\s*)?(bronze|silver|gold|platinum|titanium|white)\b', 'efficiency', lambda m: m[1].title())
        record('technical_specs.efficiency', rating)
    if category == 'storage':
        interfaces = [label for label, pattern in [('NVMe', r'\bnvme\b'), ('SATA', r'\bsata\b')] if re.search(pattern, normalized)]
        if len(interfaces) > 1:
            result['errors'].append('conflicting_interface')
        gen = matches(r'\b(?:pci[-\s]?e|gen)\s*([345])(?:\.0)?\b', 'pcie_generation', lambda m: int(m[1]))
        interface = interfaces[0] if len(interfaces) == 1 else None
        if interface == 'NVMe' and gen:
            interface += f' PCIe {gen}.0'
        record('technical_specs.interface', interface)
        types = [label for label in ('ssd', 'hdd') if re.search(r'\b' + label + r'\b', normalized)]
        if len(types) > 1:
            result['errors'].append('conflicting_storage_type')
        if len(types) == 1:
            record('technical_specs.type', types[0].upper())
        if re.search(r'\bm\.2\b', normalized):
            record('technical_specs.form_factor', 'M.2')
        consumed.extend(m.span() for m in re.finditer(r'\b(?:nvme|sata|ssd|hdd|m\.2)\b', normalized))
    if category == 'motherboard':
        matches(r'\b([abhxz]\d{3}[a-z]*)\b', 'chipset', lambda m: m[1].upper())
        socket = matches(r'\b(am[2345]|lga\s*\d{3,4})\b', 'socket', lambda m: normalize_spec('socket', m[1]))
        record('compatibility.socket', socket)
        form = matches(FORM.pattern, 'form_factor', lambda m: normalize_spec('form_factor', m[1]))
        record('compatibility.form_factor', form)
    if category == 'case':
        forms = list(FORM.finditer(normalized))
        supported = list(dict.fromkeys(normalize_spec('form_factor', m[1]) for m in forms))
        consumed.extend(m.span() for m in forms)
        if supported:
            record('compatibility.supported_form_factors', supported)
        max_length = matches(r'\b(?:gpu|placa(?: de video)?)\s*(?:ate|max(?:imo)?|de ate)?\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)\b',
                             'max_gpu_length_mm', lambda m: normalize_spec('max_gpu_length_mm', m[1] + m[2]))
        record('compatibility.max_gpu_length_mm', max_length)
        result['support_complete'] = bool(re.search(r'\b(?:apenas|somente|only)\b', normalized))
    rest = list(normalized)
    for a, b in consumed:
        rest[a:b] = ' ' * (b - a)
    rest = ''.join(rest)
    rest = re.sub(r'\b(?:processador|cpu|amd|intel|nvidia|geforce|radeon|placa mae|motherboard|placa de video|gpu|memoria|ram|fonte|psu|gabinete|case|suporta|suporte|para|e|apenas|somente|only|gamer|box|oem|lacrado|novo)\b', ' ', rest)
    for brand in sorted(brands, key=len, reverse=True):
        rest = re.sub(r'\b' + re.escape(brand) + r'\b', ' ', rest)
    result['residual'] = re.sub(r'[^a-z0-9]+', '', rest)
    result['generic'] = not result['residual']
    if result['errors']:
        result['specifications'], result['compatibility'], result['field_sources'] = {}, {}, {}
    return result


def human_keys(row):
    """Small indexed feature keys; built offline, never by scanning at request time."""
    category = 'ram' if row.get('category') == 'kit-ram' else row.get('category')
    name = normalize_human_text(row.get('name', ''))
    features = cpu_features(name, bare=False)[0] if category == 'cpu' else gpu_features(name)[0] if category == 'gpu' else {}
    key = model_key(features, category)
    keys = [key] if key else []
    from .identity import identity_scope
    if identity_scope(row) == 'family':
        if category == 'gpu' and key:
            keys.append('family:' + key)
        elif category == 'motherboard':
            parsed = parse_input(row.get('name', ''), category)
            chip = parsed['features'].get('chipset')
            ddr = normalize_spec('memory_type', (row.get('compatibility') or {}).get('memory_type'))
            if chip:
                keys.append(f'family:board:{chip}:')
                if ddr:
                    keys.append(f'family:board:{chip}:{ddr}')
    return keys
