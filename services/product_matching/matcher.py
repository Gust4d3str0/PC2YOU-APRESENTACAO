"""Deterministic catalog identity matcher; scores are evidence heuristics, not probabilities."""
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

from .normalization import normalize_text, normalize_brand, named_brands, capacity_values

VERSION = 'product-match-v1.0'
HIGH = .85
MEDIUM = .65
GPU = re.compile(r'\b(rtx|gtx|rx)[\s-]*(\d{4})[\s-]*(ti\s*super|super|ti|xtx|xt|gre)?\b', re.I)
CPU = re.compile(r'\b(?:ryzen\s*([3579])\s*(\d{4}[a-z0-9]*)|(?:core\s*)?(i[3579])\s*(\d{4,5}[a-z]*))\b')


@dataclass
class MatchResult:
    matched: bool = False
    component_id: str | None = None
    confidence: float = 0
    confidence_level: str = 'low'
    matched_by: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    normalized_key: str = ''
    matcher_version: str = VERSION

    def to_dict(self):
        return asdict(self)


def gpu_models(text):
    return {''.join(m.groups(default='')).replace(' ', '') for m in GPU.finditer(normalize_text(text))}


def features(data):
    text = normalize_text(data.get('title') or data.get('name'))
    specs = {**(data.get('compatibility') or {}), **(data.get('technical_specs') or {}), **(data.get('attributes') or {})}
    spec_text = normalize_text(' '.join(str(v) for v in specs.values() if v is not None))
    all_text = text + ' ' + spec_text
    gpu = gpu_models(all_text)
    cpu = {''.join(m.groups(default='')) for m in CPU.finditer(all_text)}
    kinds = ({'gpu'} if gpu else set()) | ({'cpu'} if cpu else set())
    for kind, pattern in [('motherboard', r'\bplaca mae\b'), ('storage', r'\b(?:ssd|nvme|hdd)\b'),
                          ('ram', r'\bmemoria ram\b')]:
        if re.search(pattern, text):
            kinds.add(kind)
    inferred = 'gpu' if gpu else 'cpu' if cpu else None
    if not inferred:
        for kind, pattern in [('storage', r'\b(?:ssd|nvme|hdd)\b'), ('psu', r'\b(?:fonte|psu)\b'),
                              ('motherboard', r'\bplaca mae\b'), ('ram', r'\b(?:ram|ddr[345])\b')]:
            if re.search(pattern, text):
                inferred = kind
                break
    category = data.get('category') or data.get('component_type') or inferred
    if category == 'kit-ram':
        category = 'ram'
    brands = named_brands(text)
    explicit_brand = normalize_brand(data.get('brand'))
    if explicit_brand:
        brands.add(explicit_brand)
    # GPU chip designers are not board vendors.
    if category == 'gpu':
        brands -= {'amd', 'nvidia', 'intel'}
    capacity_fields = ('capacity', 'memory', 'memory_size', 'memory_capacity', 'video_memory', 'graphics_card_memory')
    explicit_capacity = set().union(*(capacity_values(specs[k]) for k in capacity_fields if specs.get(k)))
    capacity = explicit_capacity | capacity_values(text)
    if category == 'ram':
        kits = re.findall(r'\b(\d+)\s*x\s*(\d+)gb\b', text)
        if kits:
            capacity = explicit_capacity | {int(n) * int(c) for n, c in kits}
    def tokens(pattern):
        return set(re.findall(pattern, all_text))
    module_counts = set(re.findall(r'\b(\d+)\s*x\s*\d+gb\b', all_text))
    single = bool(re.search(r'\b(?:single module|modulo unico|single)\b', all_text))
    module_kind = {'kit'} if re.search(r'\bkit\b', all_text) or any(int(n) > 1 for n in module_counts) else {'single'} if single or module_counts == {'1'} else set()
    models = gpu or cpu
    if category == 'motherboard':
        models = set(re.findall(r'\b[abhxz]\d{3}[a-z]*\b', all_text))
    if not models:
        # Part numbers distinguish named RAM/storage/PSU products from generic descriptions.
        models = {t for t in text.split() if re.fullmatch(r'[a-z]+\d+[a-z0-9]*', t)
                  and not re.fullmatch(r'(?:ddr\d|am[345]|lga\d+|[abx]\d{3}[a-z]?)', t)}
    return {'text': text, 'category': category, 'inferred': inferred, 'brands': brands,
            'modules': module_counts or ({'1'} if single else set()), 'module_kind': module_kind,
            'multiple': len(kinds) > 1 or bool(re.search(r'\b(?:kit upgrade|combo|bundle)\b', text)),
            'model': models, 'capacity': capacity,
            'memory_type': tokens(r'\bddr[345]\b'), 'frequency': tokens(r'\b(\d{3,5})mhz\b'),
            'socket': tokens(r'\b(?:am[345]|lga\s*\d{3,4})\b'),
            'power': tokens(r'\b(\d{3,4})w\b') | set(re.findall(r'\d{3,4}', str(specs.get('wattage', '')))),
            'generation': tokens(r'\b(\d{1,2})[ao]?\s*geracao\b'),
            'format': tokens(r'\b(?:matx|atx|itx|sodimm|dimm)\b'),
            'interface': tokens(r'\b(?:nvme|sata|hdd)\b')}


def compare_product(product, component, *, _product_features=None, _component_features=None):
    p = _product_features or features(product)
    c = _component_features or features(component)
    conflicts, signals = [], []
    if p['category'] and c['category'] != p['category'] or p['inferred'] and p['category'] != p['inferred']:
        conflicts.append('category_conflict')
    if len(p['model']) > 1 or p['multiple']:
        conflicts.append('multiple_products')
    for name, conflict in [('model', 'variant_conflict'), ('brands', 'brand_conflict'),
                           ('modules', 'ram_module_conflict'),
                           ('module_kind', 'ram_module_kind_conflict'),
                           ('capacity', 'capacity_conflict'), ('memory_type', 'memory_type_conflict'),
                           ('frequency', 'frequency_conflict'), ('socket', 'socket_conflict'),
                           ('power', 'power_conflict'), ('format', 'format_conflict'), ('interface', 'storage_conflict'),
                           ('generation', 'generation_conflict')]:
        # A GPU's minimum PSU requirement is not the GPU's own power identity.
        if name == 'power' and c['category'] != 'psu':
            continue
        if name in {'modules', 'module_kind'} and c['category'] != 'ram':
            continue
        if p[name] and c[name]:
            if p[name] != c[name]:
                conflicts.append(conflict)
            else:
                signals.append({'brands': 'brand', 'capacity': 'vram' if c['category'] == 'gpu' else 'capacity'}.get(name, name))
    key = '|'.join([str(c['category'] or ''), ','.join(sorted(p['model'])), ','.join(sorted(p['brands'])),
                    ','.join(sorted(str(v) for v in p['capacity'])), ','.join(sorted(p['memory_type']))])
    if conflicts:
        return MatchResult(confidence=.2, matched_by=signals, conflicts=conflicts, normalized_key=key)
    score = .05 if p['category'] else 0
    if p['category']:
        signals.append('category')
    if 'model' in signals:
        score += .80
    else:
        score += .35
    weights = {'brand': .08, 'vram': .08, 'capacity': .12, 'memory_type': .10,
               'frequency': .04, 'socket': .04, 'power': .22, 'format': .03, 'interface': .10, 'generation': .03}
    score += sum(weights.get(s, 0) for s in signals)
    if p['text'] == c['text'] and len(p['text']) > 5:
        signals.append('exact_name')
        score = max(score, .9)
    elif not p['model'] and not c['model'] and SequenceMatcher(None, p['text'], c['text']).ratio() >= .94:
        signals.append('name_typo')
        score = max(score, .7)
    # Generic families/specifications identify a class, not an exact commercial SKU.
    generic = not c['model'] and not c['brands']
    if generic and 'exact_name' not in signals:
        score = min(score, .80)
    if not p['model'] and c['model']:
        score = min(score, .64)
    if c['brands'] and not p['brands'] and (c['category'] != 'cpu' or 'exact_name' not in signals):
        score = min(score, .80)
    if c['category'] == 'ram' and not (p['capacity'] and p['memory_type']):
        score = min(score, .64)
    if c['category'] == 'storage' and not (p['capacity'] and p['interface']):
        score = min(score, .64)
    if c['category'] == 'psu' and not p['power']:
        score = min(score, .64)
    score = round(min(score, .99), 2)
    level = 'high' if score >= HIGH else 'medium' if score >= MEDIUM else 'low'
    return MatchResult(score >= MEDIUM, str(component['id']) if score >= MEDIUM else None,
                       score, level, signals, [], key)


class CatalogMatcher:
    """Compile one catalog snapshot shared across a batch, without a global stale cache."""
    def __init__(self, catalog):
        self.rows = list(catalog)
        self.features = {str(c['id']): features(c) for c in self.rows}

    def __iter__(self):
        return iter(self.rows)


def match_product(product, catalog):
    catalog = catalog if isinstance(catalog, CatalogMatcher) else CatalogMatcher(catalog)
    candidates = catalog.rows
    explicit = product.get('component_id')
    product_features = features(product)
    evaluated = [(c, compare_product(product, c, _product_features=product_features,
                                    _component_features=catalog.features[str(c['id'])]))
                 for c in candidates if not explicit or str(c.get('id')) == str(explicit)]
    possible = [(c, r) for c, r in evaluated if r.matched]
    if len(possible) > 1:
        result = max((r for _, r in possible), key=lambda r: r.confidence)
        return MatchResult(confidence=.64, conflicts=['variant_ambiguous'], normalized_key=result.normalized_key)
    if possible:
        return possible[0][1]
    if not evaluated:
        return MatchResult(conflicts=['catalog_component_missing' if explicit else 'catalog_unavailable'])
    # Keep diagnostics from the closest variant; never return its ID as a resolved match.
    p = features(product)
    evaluated.sort(key=lambda item: (item[0].get('category') == p['category'],
                                     len(item[1].matched_by), item[1].confidence), reverse=True)
    return evaluated[0][1]
