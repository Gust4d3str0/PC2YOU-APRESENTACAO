"""Indexed catalog lookups: equality predicates only, bounded result sets."""
from collections import defaultdict
from copy import deepcopy
import re

from .external_identity import category_of, lookup_name, search_metadata
from .external_sources import POLICY
from .identity import identity_scope


def lookup_query(category, name):
    categories = ['ram', 'kit-ram'] if category == 'ram' else [category]
    return {'category': {'$in': categories}, 'lookup_keys': lookup_name(name)}


def lookup_mongo(collection, category, name):
    limit = POLICY['lookup_candidate_limit']
    rows = list(collection.find(lookup_query(category, name), {'_id': 0}).limit(limit + 1))
    # Do not settle ambiguity by truncating candidates.
    if len(rows) > limit:
        return []
    return select_exact(rows, name)


def select_exact(rows, name):
    if rows and category_of(rows[0]) == 'cpu':
        brands = set(re.findall(r'\b(amd|intel)\b', name.casefold()))
        if brands:
            rows = [r for r in rows if r.get('brand', '').casefold() in brands]
    key = lookup_name(name)
    ids = [r for r in rows if lookup_name(r['id']) == key]
    if len(ids) == 1:
        return ids
    generic = re.fullmatch(r'(?:\d+w|fonte\d+w|[abhxz]\d{3}[a-z]*(?:ddr[45])?)', key)
    if generic:
        families = [r for r in rows if identity_scope(r) == 'family']
        return families if len(families) == 1 else []
    exact = [r for r in rows if lookup_name(r['name']) == key]
    if len(exact) == 1:
        return exact
    # An explicit MPN/alias can select a SKU, but a generic chip query never selects a vendor card.
    return rows if len(rows) == 1 else []


class LocalCatalog:
    """Offline equivalent of equality indexes; used in reproducible validation/benchmark."""
    def __init__(self, rows):
        self.items = rows
        self.by_key = defaultdict(list)
        self.by_category = defaultdict(list)
        self.by_human = defaultdict(list)
        from .human_input import human_keys
        from .human_index import family_projections
        self.human_families = {p['key']: p for p in family_projections(rows)}
        for original in rows:
            metadata = search_metadata(original)
            for key in metadata['lookup_keys']:
                self.by_key[(category_of(original), key)].append(original)
            self.by_category[original['category']].append(original)
            for key in human_keys(original):
                self.by_human[(category_of(original), key)].append(original)

    def human_candidates(self, category, name):
        from .human_input import parse_input, model_key
        from .human_resolver import family_key
        parsed = parse_input(name, category)
        rows = self.by_key.get((category, lookup_name(parsed['normalized'])), [])
        if not rows and category == 'cpu':
            rows = self.by_human.get((category, model_key(parsed['features'], category)), [])
        if not rows and parsed['generic'] and category in {'gpu', 'motherboard'} and family_key(parsed):
            rows = self.by_human.get((category, 'family:' + family_key(parsed)), [])
        return {'candidates': deepcopy(rows[:32]), 'overflow': len(rows) > 32,
                'family': deepcopy(self.human_families.get(family_key(parsed))) if parsed['generic'] else None}

    def resolve_components(self, category, name):
        rows = self.by_key.get(('ram' if category == 'kit-ram' else category, lookup_name(name)), [])
        if len(rows) > POLICY['lookup_candidate_limit']:
            return []
        return deepcopy(select_exact(rows, name))

    def search_components(self, category, name):
        return self.resolve_components(category, name)

    def upgrade_candidates(self, category, limit=24):
        return deepcopy(self.by_category.get(category, [])[:limit])

    def list_components(self, category):
        return deepcopy(self.by_category.get(category, []))
