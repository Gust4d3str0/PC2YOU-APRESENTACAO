"""Staging and atomic compare-and-set promotion. No deletes or document replacement."""
from copy import deepcopy
import hashlib
import json

from pymongo.errors import DuplicateKeyError

from .external_identity import search_metadata, identity_key
from .external_import import apply_candidate, fields, merge_plan
from .mapper import get_path


def plan_digest(report):
    """Ignore execution times; bind review to source commit, filters, exact actions and data."""
    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items() if k not in {'imported_at', 'downloaded_at'}}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return value
    data = {k: report[k] for k in ('source', 'snapshot', 'filters', 'policy', 'candidates')}
    return hashlib.sha256(json.dumps(stable(data), sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def ensure_import_indexes(database):
    components = database.components
    components.create_index('id', unique=True, name='uq_components_id')
    components.create_index('normalized_identity', unique=True, sparse=True, name='uq_external_normalized_identity')
    for source in ('buildcores_opendb', 'pc_part_dataset'):
        path = f'external_ids.{source}'
        components.create_index(path, unique=True, partialFilterExpression={path: {'$exists': True}}, name=f'uq_external_{source}')
    for key in ('lookup_keys', 'normalized_name', 'brand', 'model', 'mpn'):
        components.create_index([('category', 1), (key, 1)], name=f'ix_catalog_{key}')
    components.create_index([('category', 1), ('brand', 1), ('mpn', 1)], unique=True,
                            partialFilterExpression={'mpn.0': {'$exists': True}}, name='uq_catalog_mpn')
    database.catalog_import_candidates.create_index('id', unique=True, name='uq_catalog_candidate_id')
    database.catalog_import_candidates.create_index([('status', 1), ('source', 1)], name='ix_catalog_candidate_status')
    database.catalog_import_jobs.create_index('digest', unique=True, name='uq_catalog_import_job')


def prepare_lookup_metadata(collection):
    """Explicit offline migration, CAS guarded; never runs in an analysis request."""
    counts = {'updated': 0, 'collisions': 0}
    for row in collection.find({}):
        metadata = search_metadata(row)
        query = {'id': row['id'], 'name': row.get('name'), 'category': row.get('category'), 'brand': row.get('brand')}
        # Guard both source sections: a concurrent technical edit invalidates this projection.
        for key in ('technical_specs', 'compatibility', 'aliases', 'mpn', 'identity_scope', 'identity_variant'):
            query[key] = row[key] if key in row else {'$exists': False}
        try:
            result = collection.update_one(query, {'$set': metadata})
            counts['updated'] += result.modified_count
        except DuplicateKeyError:
            counts['collisions'] += 1
    return counts


def promote_candidate(collection, candidate):
    if candidate['status'] not in {'accepted', 'merged'} or candidate['conflicts']:
        return 'blocked'
    incoming = candidate['component']
    target_id = candidate['canonical_id']
    if candidate['action'] == 'insert':
        try:
            collection.update_one({'id': target_id}, {'$setOnInsert': deepcopy(incoming)}, upsert=True)
        except DuplicateKeyError:
            # A concurrent importer may have assigned the same identity a legacy internal ID.
            concurrent = collection.find_one({'normalized_identity': identity_key(incoming)})
            if not concurrent:
                return 'concurrent_identity_conflict'
            target_id = concurrent['id']
    current = collection.find_one({'id': target_id})
    if not current:
        return 'concurrent_missing'
    # Re-resolve against CURRENT identity, including MPN/capacity/DDR/scope.
    from .external_identity import IdentityIndex
    resolved, reason = IdentityIndex([current]).resolve(incoming)
    if not resolved:
        return 'concurrent_identity_conflict'
    changes, confirmations, conflicts = merge_plan(current, incoming)
    if conflicts:
        return 'concurrent_spec_conflict'
    live = {**candidate, 'status': 'merged', 'changes': changes, 'confirmations': confirmations, 'conflicts': []}
    updated = apply_candidate(current, live)
    query = {'id': target_id}
    for key in ('name', 'brand', 'category', 'technical_specs', 'compatibility', 'external_ids',
                'spec_provenance', 'aliases', 'mpn', 'identity_scope', 'identity_variant'):
        query[key] = current[key] if key in current else {'$exists': False}
    patch = {}
    # Entire sections are guarded in the predicate but only individual leaves are written.
    for change in changes:
        path = change['field']
        section = path.split('.')[0]
        if current.get(section) is None:
            patch[section] = updated[section]
        else:
            patch[path] = change['value']
    if current.get('spec_provenance') is None:
        patch['spec_provenance'] = updated.get('spec_provenance', {})
    else:
        for key, value in updated.get('spec_provenance', {}).items():
            if (current.get('spec_provenance') or {}).get(key) != value:
                patch[f'spec_provenance.{key}'] = value
    for key in ('external_ids', 'mpn', 'aliases'):
        if current.get(key) != updated.get(key):
            if key == 'external_ids' and current.get(key) is not None:
                for source, value in updated[key].items():
                    if (current.get(key) or {}).get(source) != value:
                        patch[f'{key}.{source}'] = value
            else:
                patch[key] = updated[key]
    patch.update(search_metadata(updated))
    try:
        result = collection.update_one(query, {'$set': patch})
    except DuplicateKeyError:
        return 'concurrent_identifier_conflict'
    return 'merged' if result.matched_count else 'concurrent_update_retry_required'


def stage_and_apply(database, report, *, promote=False):
    ensure_import_indexes(database)
    migration = prepare_lookup_metadata(database.components) if promote else None
    results = []
    for candidate in report['candidates']:
        staging = deepcopy(candidate)
        staging['planned_status'] = staging['status']
        if staging['status'] in {'accepted', 'merged'}:
            staging['status'] = 'pending'
        # Replaying a job never resets a previous review or successful promotion.
        database.catalog_import_candidates.update_one({'id': staging['id']}, {'$setOnInsert': staging}, upsert=True)
        if not promote or candidate['status'] not in {'accepted', 'merged'}:
            continue
        stored = database.catalog_import_candidates.find_one({'id': staging['id']})
        if stored.get('status') in {'rejected', 'conflict'}:
            results.append({'id': staging['id'], 'result': 'blocked_by_staging_review'})
            continue
        result = promote_candidate(database.components, candidate)
        status = candidate['status'] if result == 'merged' else 'conflict'
        database.catalog_import_candidates.update_one({'id': staging['id']}, {'$set': {'status': status, 'promotion_result': result}})
        results.append({'id': staging['id'], 'result': result})
    digest = plan_digest(report)
    database.catalog_import_jobs.update_one({'digest': digest}, {'$setOnInsert': {
        'digest': digest, 'snapshot': report['snapshot'], 'filters': report['filters'], 'policy': report['policy'],
        'summary': report['summary'], 'imported_at': report['imported_at']}, '$set': {'promote_requested': promote}}, upsert=True)
    return {'metadata_migration': migration, 'promotions': results}
