"""Offline import planning: additive patches, exact identity, auditable conflicts."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from .coverage import audit
from .external_identity import IdentityIndex, identity_key, search_metadata
from .external_sources import adapt, POLICY
from .mapper import get_path
from .normalization import normalize_spec
from .import_resources import check_memory_budget


def set_path(row, path, value):
    parts = path.split('.')
    for key in parts[:-1]:
        if row.get(key) is None:
            row[key] = {}
        row = row[key]
    row[parts[-1]] = value


def fields(row):
    return {f'{section}.{key}': value for section in ('technical_specs', 'compatibility')
            for key, value in (row.get(section) or {}).items()}


def equal(path, left, right):
    a, b = normalize_spec(path, left), normalize_spec(path, right)
    return (a == b) if a is not None and b is not None else left == right


def candidate_id(source, external_id, commit):
    return hashlib.sha256(f'{source}:{external_id}:{commit}'.encode()).hexdigest()


def merge_plan(current, incoming):
    changes, confirmations, conflicts = [], [], []
    for path, value in fields(incoming).items():
        existing = get_path(current, path)
        provenance = incoming['spec_provenance'][path.replace('.', '__')]
        if existing is None or existing == '':
            changes.append({'field': path, 'value': value, 'provenance': provenance})
        elif equal(path, existing, value):
            confirmations.append({'field': path, 'value': value, 'provenance': provenance})
        else:
            conflicts.append({'field': path, 'current': existing, 'incoming': value, 'provenance': provenance})
    return changes, confirmations, conflicts


def apply_candidate(row, candidate):
    """Pure local simulation; no IO and never mutates a caller's document."""
    row = deepcopy(row)
    if candidate.get('conflicts') or candidate.get('status') not in {'accepted', 'merged'}:
        return row
    for section in ('spec_provenance', 'external_ids'):
        if row.get(section) is None:
            row[section] = {}
    for change in candidate['changes']:
        if get_path(row, change['field']) not in (None, ''):
            continue
        set_path(row, change['field'], change['value'])
        row.setdefault('spec_provenance', {})[change['field'].replace('.', '__')] = deepcopy(change['provenance'])
    for confirmation in candidate['confirmations']:
        path, provenance = confirmation['field'], confirmation['provenance']
        if not equal(path, get_path(row, path), confirmation['value']):
            continue
        key = path.replace('.', '__')
        existing = (row.get('spec_provenance') or {}).get(key)
        # An existing audited value's primary attribution is retained.
        if not existing:
            existing = {'source': 'pc2you_audited', 'sources': ['pc2you_audited'], 'field': path}
            row.setdefault('spec_provenance', {})[key] = existing
        existing['sources'] = sorted(set(existing.get('sources') or [existing.get('source', 'pc2you_audited')]) | {provenance['source']})
        confirmations = existing.get('confirmations') or []
        signature = lambda p: tuple(p.get(k) for k in ('source', 'source_id', 'commit', 'source_field'))
        if signature(existing) != signature(provenance) and not any(signature(p) == signature(provenance) for p in confirmations):
            existing.setdefault('confirmations', []).append(deepcopy(provenance))
    incoming = candidate['component']
    for source, values in incoming['external_ids'].items():
        prior = (row.get('external_ids') or {}).get(source, [])
        prior = prior if isinstance(prior, list) else [prior]
        row.setdefault('external_ids', {})[source] = sorted(set(prior) | set(values))
    row['mpn'] = sorted(set(row.get('mpn') or []) | set(incoming.get('mpn') or []))
    row['aliases'] = sorted(set(row.get('aliases') or []) | set(incoming.get('aliases') or []))
    row.update(search_metadata(row))
    return row


def build_plan(snapshot, existing, categories, *, limit=None, newer_than=None, policy=None):
    policy = policy or POLICY
    # Existing values always win. Rank only orders new records, never permits overwrites.
    if policy.get('preserve_existing') is not True:
        raise ValueError('preserve_existing must remain true')
    now = datetime.now(timezone.utc).isoformat()
    metadata = {k: v for k, v in snapshot.metadata.items() if k != 'files'}
    candidates, prepared, rejected = [], [], []
    read = 0
    for category, external_id, raw, filename, error in snapshot.records(categories, limit):
        read += 1
        if read % 100 == 0:
            check_memory_budget()
        candidate = dict(id=candidate_id(snapshot.source, external_id, metadata['commit']), source=snapshot.source,
                         external_id=external_id, snapshot=metadata, source_file=filename, imported_at=now,
                         status='pending', confidence=0, conflicts=[], changes=[], confirmations=[])
        try:
            if error:
                raise ValueError(error)
            row = adapt(snapshot.source, category, raw, external_id, metadata, now, newer_than)
            candidate.update(component=row, proposed_identity=identity_key(row), confidence=1.0)
            prepared.append(candidate)
        except (ValueError, TypeError, KeyError) as exc:
            candidate.update(status='rejected', reason=str(exc)[:180], category=category)
            rejected.append(candidate)
    # Same-source collisions are checked BEFORE promotion; iteration order never settles conflicting specs.
    groups = {}
    for candidate in prepared:
        groups.setdefault(candidate['proposed_identity'], []).append(candidate)
    blocked = set()
    for group in groups.values():
        anchor = group[0]['component']
        for other in group[1:]:
            conflicts = merge_plan(anchor, other['component'])[2]
            mpns_a, mpns_b = set(anchor.get('mpn') or []), set(other['component'].get('mpn') or [])
            if conflicts or (anchor['category'] != 'cpu' and mpns_a and mpns_b and not mpns_a & mpns_b):
                for entry in group:
                    blocked.add(entry['id'])
                    entry.update(status='conflict', conflicts=conflicts or [{'field': 'mpn', 'reason': 'disjoint_identifiers'}],
                                 reason='same_source_identity_collision')
                break
    state = {r['id']: deepcopy(r) for r in existing}
    index = IdentityIndex(list(state.values()))
    for position, candidate in enumerate(prepared):
        if position % 100 == 0:
            check_memory_budget()
        if candidate['id'] in blocked:
            candidates.append(candidate)
            continue
        incoming = candidate['component']
        current, reason = index.resolve(incoming)
        candidate['match_reason'] = reason
        if current is None and reason not in {'new', 'distinct_variant'}:
            candidate.update(status='conflict', reason=reason, conflicts=[{'field': 'identity', 'reason': reason}])
        elif current is None:
            if snapshot.source == 'pc_part_dataset' and not incoming.get('mpn') and index.possible_dataset_duplicate(incoming):
                candidate.update(status='conflict', reason='possible_duplicate_without_stable_sku_id',
                                 conflicts=[{'field': 'identity', 'reason': 'existing_manufacturer_hardware_class_requires_review'}])
                candidates.append(candidate)
                continue
            row = deepcopy(incoming)
            row.update(search_metadata(row))
            candidate.update(status='accepted', action='insert', canonical_id=row['id'], component=row,
                             changes=[{'field': p, 'value': v, 'provenance': row['spec_provenance'][p.replace('.', '__')]}
                                      for p, v in fields(row).items()])
            state[row['id']] = row
            index.add(row)
        else:
            changes, confirmations, conflicts = merge_plan(current, incoming)
            candidate.update(canonical_id=current['id'], action='merge', changes=changes,
                             confirmations=confirmations, conflicts=conflicts,
                             status='conflict' if conflicts else 'merged')
            if not conflicts:
                row = apply_candidate(current, candidate)
                state[row['id']] = row
                index.add(row)
        candidates.append(candidate)
    candidates.extend(rejected)
    counts = Counter(c['status'] for c in candidates)
    report = dict(source=snapshot.source, snapshot=metadata, imported_at=now, mode='dry-run',
                  filters={'categories': sorted(categories), 'limit': limit, 'newer_than': str(newer_than) if newer_than else None},
                  policy=policy, summary=dict(read=read, eligible=len(prepared), new=counts['accepted'],
                      merged=counts['merged'], conflicts=counts['conflict'], rejected=counts['rejected'],
                      fields_filled=sum(len(c['changes']) for c in candidates if c['status'] in {'accepted', 'merged'})),
                  rejection_reasons=dict(Counter(c['reason'] for c in rejected)),
                  coverage_before=audit(existing), coverage_after=audit(list(state.values())), candidates=candidates)
    return report, list(state.values())
