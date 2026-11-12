"""Conservative per-field statistics for a family of catalog candidates.

Built offline (see human_index.family_projections); never computed from a request-time scan.
A bound is only a proof for "every candidate in the family" when its coverage is safe:

* full coverage (every candidate has a valid value), or
* a model-level field (``MODEL_LEVEL``) that at least one family-scope row defines. Vendor
  SKUs rarely repeat the chip-level recommended PSU, and a family row is the authority for it.

Missing or invalid values are never guessed. ``safe_min``/``safe_max`` are the only numbers a
rule may use: ``safe_min`` is true for ALL candidates as a floor, ``safe_max`` as a ceiling.
"""
from .identity import identity_scope
from .mapper import get_path
from .normalization import normalize_spec

NUMERIC = {
    'motherboard': ['technical_specs.memory_slots', 'technical_specs.max_memory_gb'],
    'gpu': ['compatibility.min_psu_watts', 'technical_specs.length_mm'],
}
CATEGORICAL = {
    'motherboard': ['compatibility.socket', 'compatibility.memory_type', 'compatibility.form_factor'],
    'gpu': [],
}
MODEL_LEVEL = {'compatibility.min_psu_watts'}
FAMILY_SOURCES = {'catalog_family_consensus', 'catalog_family_min', 'catalog_family_max', 'catalog_family_bound'}


def _value(row, path):
    return normalize_spec(path, get_path(row, path))


def summarize_field(rows, path, *, numeric):
    pairs = [(row, _value(row, path)) for row in rows]
    known = [(row, v) for row, v in pairs if v is not None]
    stats = {'field': path, 'candidate_count': len(rows), 'known_count': len(known),
             'coverage': round(len(known) / len(rows), 4) if rows else 0.0,
             'min': None, 'max': None, 'consensus': None, 'safe_min': None, 'safe_max': None}
    if not known:
        return stats
    values = [v for _, v in known]
    full = len(known) == len(rows)
    if numeric:
        stats['min'], stats['max'] = min(values), max(values)
        distinct = set(values)
    else:
        distinct = {tuple(v) if isinstance(v, list) else v for v in values}
        stats['values'] = sorted(str(v) for v in distinct)
    if full and len(distinct) == 1:
        stats['consensus'] = values[0]
    if numeric:
        model = [v for row, v in known if identity_scope(row) == 'family']
        stats['model_level_known'] = len(model)
        if full:
            stats['safe_min'], stats['safe_max'] = stats['min'], stats['max']
        elif path in MODEL_LEVEL and model:
            stats['safe_min'], stats['safe_max'] = min(model), stats['max']
    return stats


def summarize(rows, category):
    result = {}
    for path in NUMERIC.get(category, []):
        result[path] = summarize_field(rows, path, numeric=True)
    for path in CATEGORICAL.get(category, []):
        result[path] = summarize_field(rows, path, numeric=False)
    return result


def usable(stats):
    """Evidence present and structurally sane (counts consistent, not empty)."""
    return (isinstance(stats, dict) and isinstance(stats.get('candidate_count'), int)
            and isinstance(stats.get('known_count'), int)
            and 0 < stats['known_count'] <= stats['candidate_count'])


def complete(stats):
    return usable(stats) and stats['known_count'] == stats['candidate_count']


def proves(stats, source):
    """Does this bound satisfy the evidence demanded by `source`?"""
    if not usable(stats):
        return False
    if source == 'catalog_family_consensus':
        return stats.get('consensus') is not None
    if source == 'catalog_family_min':
        return stats.get('safe_min') is not None
    if source == 'catalog_family_max':
        return stats.get('safe_max') is not None
    if source == 'catalog_family_bound':
        return stats.get('safe_min') is not None or stats.get('safe_max') is not None or complete(stats)
    return False
