"""Offline, deterministic coverage discovery. Never changes matching rules."""
import re
from collections import Counter, defaultdict
from product_matching.matcher import features
from product_matching.normalization import normalize_text, capacity_label
from product_matching.promotions import promotion_match


def discover(promotions, catalog):
    from product_matching import CatalogMatcher
    matcher = CatalogMatcher(catalog)
    groups = defaultdict(list)
    low = 0
    for row in promotions:
        if promotion_match(row, matcher).confidence_level != 'low':
            continue
        low += 1
        p = row.get('product') or {}
        title = p.get('name') or row.get('raw_text') or ''
        data = {'title': title, 'brand': p.get('brand'), 'category': p.get('component_type')}
        f = features(data)
        text = normalize_text(title)
        if re.search(r'\b(?:notebook|laptop|smartphone|celular|monitor|headset|mouse|teclado|mini pc|computador|pc gamer)\b', text):
            continue
        # Only parsed identity tokens leave this function; no raw messages or IDs.
        if f['multiple'] or len(f['model']) != 1 or not f['category']:
            continue
        model = next(iter(f['model']))
        patterns = {'gpu': r'(?:rtx|gtx|rx)\d{4}(?:ti|super|tisuper|xt|xtx|gre)?',
                    'cpu': r'(?:[3579]\d{4}[a-z0-9]*|i[3579]\d{4,5}[a-z]*)',
                    'motherboard': r'[abhxz]\d{3}[a-z]*',
                    'storage': r'(?:sn\d+[a-z]*|nv[23]|nm\d+|wds[a-z0-9]+|sdss[a-z0-9]+)',
                    'ram': r'(?:mv\d+[a-z0-9]*|kf\d+[a-z0-9]*|cm[ak][a-z0-9]+)',
                    'psu': r'(?:rm\d+x?|mag\d+[a-z0-9]*|bn\d+[a-z0-9]*)'}
        if not re.fullmatch(patterns.get(f['category'], r'(?!)'), model):
            continue
        # Existing identities that merely conflict with an advert are not missing models.
        if any(model in cf['model'] for cf in matcher.features.values()):
            continue
        if f['category'] in {'gpu', 'cpu', 'motherboard', 'storage', 'ram', 'psu'}:
            groups[(f['category'], model)].append((data, f))
    candidates = []
    for (category, model), rows in groups.items():
        brands = sorted(set().union(*(f['brands'] for _, f in rows)))
        capacities = sorted(set().union(*(f['capacity'] for _, f in rows)))
        variants = Counter()
        for _, f in rows:
            variants['|'.join([','.join(sorted(f['brands'])), ','.join(capacity_label(v) for v in sorted(f['capacity'])),
                               ','.join(sorted(f['memory_type'])), ','.join(sorted(f['frequency']))])] += 1
        item = {'normalized_model': model, 'category': category, 'occurrences': len(rows),
                'brands_seen': brands, 'capacities_seen': [capacity_label(v) for v in capacities],
                'sample_count': min(5, len(rows)), 'variants': dict(variants),
                'verification_status': 'candidate_requires_source_verification',
                'model_clarity': 'explicit_token',
                'priority_score': len(rows) * 10 + (5 if category in {'gpu', 'cpu'} else 3),
                'estimated_high_matches': None}
        candidates.append(item)
    candidates.sort(key=lambda v: (-v['priority_score'], v['category'], v['normalized_model']))
    return {'total_promotions': len(promotions), 'total_low_promotions': low,
            'missing_model_candidates': len(candidates), 'candidates': candidates,
            'limitations': ['Ambiguous multi-product titles excluded; explicit tokens are candidates, not verified SKUs.',
                            'Occurrence counts are messages, not unique products or independent sellers.']}


def sync_new(collection, components, *, apply=False):
    """Insert-only, including on a race; never update an existing document."""
    from pymongo.errors import DuplicateKeyError
    result = {'mode': 'apply' if apply else 'dry-run', 'inserted': 0, 'would_insert': [], 'existing_skipped': []}
    for row in components:
        cid = row['id']
        if collection.find_one({'id': cid}) is not None:
            result['existing_skipped'].append(cid)
            continue
        result['would_insert'].append(cid)
        if apply:
            # A unique id index is required by the caller before applying.
            try:
                outcome = collection.update_one({'id': cid}, {'$setOnInsert': row}, upsert=True)
                result['inserted'] += outcome.upserted_id is not None
            except DuplicateKeyError:
                result['existing_skipped'].append(cid)
    return result


def baseline_divergences(base, current):
    """Compare identity, never prices/quality/images. Duplicate live IDs also block apply."""
    grouped = defaultdict(list)
    for row in current:
        grouped[row['id']].append(row)
    differences = []
    for row in base:
        found = grouped[row['id']]
        if len(found) != 1:
            differences.append({'id': row['id'], 'fields': ['missing_or_duplicate_id']})
            continue
        fields = [k for k in ('name', 'brand', 'category', 'technical_specs', 'compatibility')
                  if found[0].get(k) != row.get(k)]
        if fields:
            differences.append({'id': row['id'], 'fields': fields})
    return differences
