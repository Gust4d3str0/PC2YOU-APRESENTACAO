import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import mongomock
import pytest

from catalog_audit import audit_components
from catalog_audit.seed_io import load_seed
from catalog_audit.sync import sync_components, validate_manifest

ROOT = Path(__file__).resolve().parents[2]
ROWS = load_seed(ROOT / 'api-catalogo/seed.py')
REFS = json.loads((ROOT / 'api-catalogo/seed_identity_reference.json').read_text(encoding='utf-8'))
MANIFEST = json.loads((ROOT / 'api-catalogo/seed_identity_corrections.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', ROWS, ids=lambda r: r['id'])
def test_every_seed_component_is_internally_consistent(row):
    assert audit_components([row], REFS)['summary']['critical_conflicts'] == 0


def test_whole_seed_has_unique_ids_and_names():
    report = audit_components(ROWS, REFS)
    assert report['total_components'] == 94
    assert not report['duplicate_ids'] and not report['duplicate_names']
    assert not report['suspected']


@pytest.mark.parametrize('cid,expected', [
    ('ryzen-5-7600', 'AMD Ryzen 5 7600'), ('ryzen-7-7800x3d', 'AMD Ryzen 7 7800X3D'),
    ('ryzen-9-7950x', 'AMD Ryzen 9 7950X'), ('ryzen-9-5950x', 'AMD Ryzen 9 5950X'),
    ('ryzen-9-7900x', 'AMD Ryzen 9 7900X'), ('intel-i7-13700k', 'Intel Core i7-13700K'),
    ('intel-i9-13900ks', 'Intel Core i9-13900KS'), ('cooler-deepcool-ak400', 'DeepCool AK400'),
    ('cooler-deepcool-ak620', 'DeepCool AK620'), ('cooler-nzxt-kraken-240', 'NZXT Kraken 240 (2023)'),
    ('cooler-nzxt-kraken-360', 'NZXT Kraken 360 (2023)'), ('gabinete-lian-li-lancool', 'Lian Li LANCOOL 216'),
    ('gabinete-nzxt-h510', 'NZXT H510'), ('cooler-cm-hyper212', 'Cooler Master Hyper 212 Black (RR-S4KK-25SN-R1)')])
def test_confirmed_identity_intentions_are_preserved(cid, expected):
    row = next(r for r in ROWS if r['id'] == cid)
    assert row['name'] == expected


@pytest.mark.parametrize('cid,wrong', [
    ('ryzen-5-7600', 'AMD Ryzen 5 8600G'), ('ryzen-7-7800x3d', 'AMD Ryzen 7 7700'),
    ('ryzen-9-5950x', 'AMD Ryzen 7 5800X'), ('intel-i5-12400f', 'Intel Core i5-12400'),
    ('intel-i9-13900ks', 'Intel Core i9-13900K'), ('intel-i7-13700k', 'Intel Core i7-13700KF'),
    ('rtx-4060', 'GeForce RTX 4060 Ti'), ('rtx-4070-super', 'GeForce RTX 4070'),
    ('rx-7900-xtx', 'Radeon RX 7900 XT'), ('rx-7800-xt', 'Radeon RX 7800'),
    ('cooler-deepcool-ak400', 'Cooler Master Hyper 212'), ('gabinete-nzxt-h510', 'NZXT H5 Flow')])
def test_model_suffix_and_commercial_model_mutations_are_detected(cid, wrong):
    row = deepcopy(next(r for r in ROWS if r['id'] == cid))
    row['name'] = wrong
    assert audit_components([row])['id_name_conflicts']


@pytest.mark.parametrize('path,value', [
    ('category', 'cpu'), ('brand', 'Kingston'), ('technical_specs.capacity', '32GB'),
    ('compatibility.memory_type', 'DDR5'), ('technical_specs.speed', '3600MHz')])
def test_wrong_category_brand_capacity_ddr_and_frequency_are_detected(path, value):
    row = deepcopy(next(r for r in ROWS if r['id'] == 'kit-ram-16gb-ddr4-3200'))
    target = row
    parts = path.split('.')
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    assert audit_components([row])['suspected']


def test_duplicate_ids_and_normalized_names_are_reported():
    row = deepcopy(ROWS[0])
    assert audit_components([row, deepcopy(row)])['duplicate_ids']
    duplicate = {**row, 'id': 'generic-cpu', 'name': row['name'].upper()}
    assert audit_components([row, duplicate])['duplicate_names']


def test_generic_id_does_not_force_commercial_name_or_manufacturer_specs():
    row = {'id': 'fonte-generica', 'name': 'Fonte de alimentação', 'brand': 'Não especificada',
           'category': 'psu', 'technical_specs': {}, 'compatibility': {}}
    assert not audit_components([row])['suspected']
    assert audit_components([row])['warnings']


def test_seed_loader_never_imports_database_or_calls_the_seeder(tmp_path):
    source = (ROOT / 'api-catalogo/seed.py').read_text(encoding='utf-8')
    source = source.replace('from database import get_components_collection', "raise RuntimeError('database accessed')")
    path = tmp_path / 'seed.py'
    path.write_text(source, encoding='utf-8')
    assert len(load_seed(path)) == 94


def old_row_for_entry(entry):
    row = deepcopy(next(c for c in ROWS if c['id'] == entry['id']))
    for change in entry['changes']:
        parts = change['path'].split('.')
        target = row
        for key in parts[:-1]:
            target = target.setdefault(key, {})
        if change['before_exists']:
            target[parts[-1]] = change['before']
        else:
            target.pop(parts[-1], None)
    return row


def test_sync_dry_run_and_apply_preserve_prices_history_quality_and_other_collections():
    validate_manifest(MANIFEST, ROWS, REFS)
    db = mongomock.MongoClient().db
    for entry in MANIFEST['components']:
        row = old_row_for_entry(entry)
        row.update(prices=[{'source': 'mercado_livre', 'price': 123, 'quality': {'verified': True}}],
                   price_history=[{'date': '2026-01-01', 'source': 'manual', 'price': 123}],
                   data_quality={'custom': True}, real_image='persisted-image')
        row['technical_specs']['private_quality_note'] = 'preserve'
        db.components.insert_one(row)
    db.telegram_promotions.insert_one({'raw_text': 'preserve', 'product': {'match_level': 'high'}})
    db.product_price_history.insert_one({'price': 123})
    before = list(db.components.find({}))
    assert sync_components(db.components, MANIFEST)['updated'] == 0
    assert list(db.components.find({})) == before
    assert sync_components(db.components, MANIFEST, apply=True)['updated'] == 29
    for old in before:
        new = db.components.find_one({'id': old['id']})
        for field in ('prices', 'price_history', 'data_quality', 'real_image', 'id'):
            assert new[field] == old[field]
        assert new['technical_specs']['private_quality_note'] == 'preserve'
    assert sync_components(db.components, MANIFEST, apply=True)['updated'] == 0
    assert db.telegram_promotions.find_one()['raw_text'] == 'preserve'
    assert db.product_price_history.find_one()['price'] == 123


def test_sync_skips_missing_duplicate_and_manually_changed_fields():
    entry = MANIFEST['components'][0]
    manifest = {'components': [entry]}
    db = mongomock.MongoClient().db
    assert sync_components(db.components, manifest)['skipped'][0]['reason'] == 'missing'
    row = old_row_for_entry(entry)
    row['name'] = 'Manually changed product'
    db.components.insert_one(deepcopy(row))
    assert sync_components(db.components, manifest, apply=True)['updated'] == 0
    assert db.components.find_one()['name'] == row['name']
    db.components.insert_one(deepcopy(row))
    assert sync_components(db.components, manifest)['skipped'][0]['reason'] == 'duplicate_id'


@pytest.mark.parametrize('path', ['prices', 'price_history', 'id', 'product.match_level', 'technical_specs', 'compatibility', 'data_quality'])
def test_sync_manifest_rejects_protected_paths(path):
    manifest = deepcopy(MANIFEST)
    manifest['components'][0]['changes'][0]['path'] = path
    with pytest.raises(ValueError):
        validate_manifest(manifest, ROWS, REFS)


def test_sync_detects_concurrent_changes_without_overwriting():
    entry = MANIFEST['components'][0]
    row = old_row_for_entry(entry)
    row['_id'] = 'row'
    collection = Mock()
    collection.find.return_value.limit.return_value = [row]
    collection.update_one.return_value.matched_count = 0
    result = sync_components(collection, {'components': [entry]}, apply=True)
    assert result['updated'] == 0 and result['skipped'][0]['reason'] == 'concurrent_change'


def test_manufacturer_reference_catches_wrong_specs_even_with_correct_name_and_id():
    row = deepcopy(next(r for r in ROWS if r['id'] == 'ryzen-9-5950x'))
    row['technical_specs'].update(cores=8, threads=16)
    assert audit_components([row], REFS)['spec_conflicts']
