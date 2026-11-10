"""Identity, ingestion, snapshot trust, staging and atomic additive promotion regressions."""
from copy import deepcopy
from datetime import date
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mongomock
import pytest

from catalog_specs.external_sources import adapt, Snapshot, validate_dataset
from catalog_specs.external_identity import IdentityIndex, identity_key, search_metadata
from catalog_specs.external_import import build_plan, merge_plan, apply_candidate
from catalog_specs.external_persistence import stage_and_apply, promote_candidate, plan_digest
from catalog_specs.lookup import LocalCatalog, lookup_mongo

META = {'source': 'buildcores', 'commit': 'a' * 40, 'license': 'CC-BY-NC-SA-4.0'}
NOW = '2026-11-10T12:00:00+00:00'


def raw(category, name, **changes):
    data = {'metadata': {'name': name, 'manufacturer': 'AMD' if category == 'cpu' else 'ASUS', 'part_numbers': []}}
    defaults = {
        'cpu': {'socket': 'AM4', 'cores': {'total': 6, 'threads': 12}, 'specifications': {'tdp': 65}},
        'gpu': {'chipset': name, 'memory': 8, 'length': 240, 'tdp': 150},
        'motherboard': {'socket': 'AM4', 'form_factor': 'Micro ATX', 'memory': {'ram_type': 'DDR4', 'max': 128, 'slots': 4}},
        'ram': {'form_factor': '288-pin DIMM', 'ram_type': 'DDR4', 'speed': 3200, 'capacity': 16, 'modules': {'quantity': 2, 'capacity_gb': 8}},
        'storage': {'storage_type': 'SSD', 'capacity': 1000, 'interface': 'M.2 PCIe 4.0 x4'},
        'psu': {'wattage': 650, 'form_factor': 'ATX'},
        'case': {'supported_motherboard_form_factors': ['ATX', 'Micro ATX'], 'max_video_card_length': 350},
    }
    data.update(defaults[category])
    data.update(changes)
    return data


def mapped(category, name, **changes):
    return adapt('buildcores', category, raw(category, name, **changes), name, META, NOW)


@pytest.mark.parametrize('name', ['AMD Ryzen 5 5600', 'AMD Ryzen 5 5600X', 'AMD Ryzen 7 5700X',
    'AMD Ryzen 5 7600', 'Intel Core i5-12400F', 'Intel Core i5-13600K'])
def test_cpu_models(name):
    data = raw('cpu', name)
    data['metadata']['manufacturer'] = name.split()[0]
    row = adapt('buildcores', 'cpu', data, name, META, NOW)
    assert row['technical_specs']['cores'] == 6
    catalog = LocalCatalog([row])
    assert catalog.resolve_components('cpu', name)
    if 'Ryzen' in name:
        assert catalog.resolve_components('cpu', 'Processador ' + name.removeprefix('AMD '))


def test_cpu_plus_is_an_identity_suffix_not_a_marketing_word():
    def cpu(name):
        return mapped('cpu', name, socket='LGA1851', metadata={'name': name, 'manufacturer': 'Intel', 'part_numbers': []})
    base = cpu('Intel Core Ultra 5 250K')
    plus = cpu('Intel Core Ultra 5 250K Plus')
    assert identity_key(base) != identity_key(plus)
    assert IdentityIndex([base]).resolve(plus)[0] is None
    assert not LocalCatalog([plus]).resolve_components('cpu', base['name'])


@pytest.mark.parametrize('chip', ['RTX 3060', 'RTX 3060 Ti', 'RTX 4060', 'RTX 4060 Ti', 'RTX 4070',
    'RTX 4070 Super', 'RTX 4080', 'RTX 4080 Super', 'RX 6600', 'RX 7800 XT'])
def test_gpu_chip_suffixes_and_sku_dimensions(chip):
    row = mapped('gpu', 'ASUS Dual ' + chip, chipset=chip)
    assert row['technical_specs']['memory'] == '8GB'
    assert row['technical_specs']['length_mm'] == 240
    assert 'min_psu_watts' not in row['compatibility']
    family = mapped('gpu', chip, chipset=chip)
    assert family['identity_scope'] == 'family' and 'length_mm' not in family['technical_specs']
    assert IdentityIndex([family]).resolve(row)[0] is None


@pytest.mark.parametrize('chip', ['A520', 'B450', 'B550', 'B650', 'X670', 'H610', 'B660', 'B760', 'Z690', 'Z790'])
def test_board_chipsets_are_actual_skus(chip):
    row = mapped('motherboard', 'ASUS ' + chip + ' PRIME')
    assert row['identity_scope'] == 'sku'
    assert row['technical_specs']['max_memory_gb'] == 128
    assert not LocalCatalog([row]).resolve_components('motherboard', chip)


@pytest.mark.parametrize('generation,total', [('DDR4', 8), ('DDR4', 16), ('DDR4', 32), ('DDR5', 16), ('DDR5', 32)])
def test_dimm_capacity_generation_and_kits(generation, total):
    one = mapped('ram', f'ASUS RAM {total}GB {generation}', capacity=total, ram_type=generation, modules={'quantity': 1, 'capacity_gb': total})
    two = mapped('ram', f'ASUS RAM {total}GB {generation}', capacity=total, ram_type=generation, modules={'quantity': 2, 'capacity_gb': total // 2})
    assert identity_key(one) != identity_key(two)
    assert IdentityIndex([one]).resolve(two)[0] is None


@pytest.mark.parametrize('watts', [450, 550, 650, 750, 850])
def test_psu_watts(watts):
    assert mapped('psu', f'ASUS PRIME {watts}W', wattage=watts)['technical_specs']['wattage'] == watts


@pytest.mark.parametrize('interface,expected', [('M.2 PCIe 3.0 x4', 'PCIe 3.0 x4'), ('M.2 PCIe 4.0 x4', 'PCIe 4.0 x4'), ('SATA 6.0 Gb/s', 'SATA III')])
def test_ssd_interfaces_and_decimal_capacities(interface, expected):
    one = mapped('storage', 'ASUS SN770', interface=interface)
    two = mapped('storage', 'ASUS SN770', interface=interface, capacity=2000)
    assert one['technical_specs'] == {'capacity': '1TB', 'interface': expected}
    assert IdentityIndex([one]).resolve(two)[0] is None


@pytest.mark.parametrize('category,left,right', [('cpu', 'AMD Ryzen 5 5600', 'AMD Ryzen 5 5600X'),
    ('cpu', 'AMD Ryzen 5 5600', 'AMD Ryzen 5 5600G'), ('gpu', 'RTX 3060', 'RTX 3060 Ti'),
    ('gpu', 'RTX 4070', 'RTX 4070 Super'), ('gpu', 'RTX 4070 Ti', 'RTX 4070 Ti Super')])
def test_mandatory_suffix_nonmatches(category, left, right):
    a, b = mapped(category, left), mapped(category, right)
    assert identity_key(a) != identity_key(b)
    assert IdentityIndex([a]).resolve(b)[0] is None
    assert not LocalCatalog([a]).resolve_components(category, right)


def test_board_ddr_and_vendor_skus_remain_distinct():
    a = mapped('motherboard', 'ASUS B760 PRIME DDR4')
    b = mapped('motherboard', 'ASUS B760 PRIME DDR5', memory={'ram_type': 'DDR5', 'max': 192, 'slots': 4})
    assert IdentityIndex([a]).resolve(b)[0] is None
    b = deepcopy(a)
    b['brand'] = 'gigabyte'
    assert IdentityIndex([a]).resolve(b)[0] is None
    cpu = mapped('cpu', 'AMD Ryzen 5 5600')
    assert not LocalCatalog([cpu]).resolve_components('cpu', 'Intel Ryzen 5 5600')


def test_existing_external_id_cannot_silently_switch_color_variant():
    a = mapped('gpu', 'ASUS Dual RTX 4060', chipset='RTX 4060')
    b = deepcopy(a)
    a['identity_variant'], b['identity_variant'] = 'black', 'white'
    assert IdentityIndex([a]).resolve(b) == (None, 'identifier_conflict')


def test_only_explicit_families_receive_chipset_and_wattage_aliases():
    psu = mapped('psu', 'ASUS PRIME 650W')
    assert not LocalCatalog([psu]).resolve_components('psu', '650W')
    psu['identity_scope'] = 'family'
    assert LocalCatalog([psu]).resolve_components('psu', '650W')[0]['id'] == psu['id']
    board = mapped('motherboard', 'ASUS B550M PRIME')
    assert not LocalCatalog([board]).resolve_components('motherboard', 'B550M')
    board['identity_scope'] = 'family'
    assert LocalCatalog([board]).resolve_components('motherboard', 'B550M DDR4')
    assert not LocalCatalog([board]).resolve_components('motherboard', 'B550M DDR5')


@pytest.mark.parametrize('label', ['850W', '16GB', '2x16GB', 'DDR4', 'B650', 'RTX 4070', 'ATX 3.0'])
def test_generic_source_labels_cannot_become_mpns_or_lookup_aliases(label):
    from catalog_specs.external_identity import valid_mpn
    assert not valid_mpn(label, 'gpu')
    row = mapped('psu', 'ASUS PRIME 850W', wattage=850)
    row['mpn'] = [label]
    assert not LocalCatalog([row]).resolve_components('psu', label)


def test_generic_chip_input_prefers_explicit_family_over_a_partial_sku_name():
    sku = mapped('motherboard', 'B650')
    family = deepcopy(sku)
    family.update(id='family-b650', name='Placa-mae B650 AM5 DDR5', identity_scope='family')
    family['compatibility']['memory_type'] = 'DDR5'
    assert not LocalCatalog([sku]).resolve_components('motherboard', 'B650')
    assert LocalCatalog([sku, family]).resolve_components('motherboard', 'B650')[0]['id'] == 'family-b650'


def test_no_price_or_physical_guess_and_all_fields_have_provenance():
    row = mapped('gpu', 'ASUS Dual RTX 4060', price=1234, chipset='RTX 4060')
    assert row['prices'] == row['price_history'] == [] and row['benchmark'] == {}
    assert row['spec_provenance']['technical_specs__length_mm']['source'] == 'buildcores'
    assert row['spec_provenance']['technical_specs__length_mm']['license'] == META['license']
    assert row['id'] != row['external_ids']['buildcores_opendb'][0]


def test_missing_dataset_fields_remain_absent_and_no_scraper_needed():
    meta = {**META, 'source': 'pc_part_dataset', 'license': 'MIT'}
    row = adapt('pc_part_dataset', 'cpu', {'name': 'AMD Ryzen 7 5700X', 'core_count': 8, 'tdp': 65}, 'hash', meta, NOW)
    assert row['technical_specs'] == {'cores': 8, 'tdp_watts': 65}
    assert row['compatibility'] == {}
    with pytest.raises(ValueError, match='desktop_dimm_not_confirmed'):
        adapt('pc_part_dataset', 'ram', {'name': 'Corsair Vengeance 32GB', 'speed': [5, 6000], 'modules': [2, 16]}, 'hash', meta, NOW)
    with pytest.raises(ValueError, match='date_unavailable'):
        adapt('pc_part_dataset', 'cpu', {'name': 'AMD Ryzen 7 5700X', 'core_count': 8}, 'hash', meta, NOW, date(2024, 1, 1))


@pytest.mark.parametrize('category,name,extra', [('cpu', 'AMD Ryzen 7 5800H', {}), ('cpu', 'Intel Core i5-7500', {}),
    ('ram', 'ASUS DDR4 16GB', {'form_factor': '260-pin SO-DIMM'}), ('storage', 'ASUS drive', {'storage_type': 'HDD'}),
    ('ram', 'ASUS DDR4 16GB', {'capacity': 32}), ('cpu', 'AMD EPYC 7601', {})])
def test_scope_and_quality_rejections(category, name, extra):
    with pytest.raises(ValueError):
        mapped(category, name, **extra)


def snapshot_double(records):
    return SimpleNamespace(source='buildcores', metadata=META,
        records=lambda categories, limit: iter(records[:limit] if limit else records))


def test_planner_preserves_audited_values_conflicts_and_dry_run():
    current = mapped('cpu', 'AMD Ryzen 7 5700X')
    current['id'] = 'legacy-internal-id'
    current['external_ids'] = {}
    current['technical_specs']['cores'] = 8
    before = deepcopy(current)
    source = snapshot_double([('cpu', 'uuid', raw('cpu', current['name']), 'source.json', None)])
    report, after = build_plan(source, [current], {'cpu'})
    assert current == before == after[0]
    assert report['summary']['conflicts'] == 1 and report['summary']['new'] == 0
    assert report['candidates'][0]['canonical_id'] == 'legacy-internal-id'


def test_same_source_disagreement_quarantines_both_before_any_insert():
    source = snapshot_double([('cpu', 'a', raw('cpu', 'AMD Ryzen 5 5600'), 'a.json', None),
        ('cpu', 'b', raw('cpu', 'AMD Ryzen 5 5600', cores={'total': 8, 'threads': 12}), 'b.json', None)])
    report, after = build_plan(source, [], {'cpu'})
    assert after == [] and report['summary']['conflicts'] == 2


def test_dataset_unmatched_sku_in_existing_hardware_class_requires_review():
    current = mapped('psu', 'ASUS PRIME 650W')
    source = SimpleNamespace(source='pc_part_dataset', metadata={**META, 'source': 'pc_part_dataset', 'license': 'MIT'},
        records=lambda categories, limit: iter([('psu', 'hash', {'name': 'Asus ROG STRIX 650W', 'wattage': 650, 'type': 'ATX'}, 'data.json', None)]))
    report, after = build_plan(source, [current], {'psu'})
    assert len(after) == 1 and report['summary']['conflicts'] == 1
    assert report['candidates'][0]['reason'] == 'possible_duplicate_without_stable_sku_id'


def test_staging_only_then_promotion_and_replay_preserve_specs_and_prices():
    source = snapshot_double([('cpu', 'a', raw('cpu', 'AMD Ryzen 5 5600'), 'a.json', None)])
    report, after = build_plan(source, [], {'cpu'})
    db = mongomock.MongoClient().db
    stage_and_apply(db, report)
    assert db.components.count_documents({}) == 0
    assert db.catalog_import_candidates.find_one()['status'] == 'pending'
    stage_and_apply(db, report, promote=True)
    first = db.components.find_one()
    stage_and_apply(db, report, promote=True)
    assert db.components.find_one() == first and db.components.count_documents({}) == 1
    assert db.catalog_import_jobs.count_documents({}) == 1
    assert lookup_mongo(db.components, 'cpu', 'Processador Ryzen 5 5600')[0]['id'] == first['id']


def test_second_source_confirmation_retains_original_provenance():
    row = mapped('cpu', 'AMD Ryzen 5 5600')
    incoming = deepcopy(row)
    incoming['external_ids'] = {'pc_part_dataset': ['b']}
    for p in incoming['spec_provenance'].values():
        p['source'] = 'pc_part_dataset'
        p['source_id'] = 'b'
    changes, confirmations, conflicts = merge_plan(row, incoming)
    candidate = {'status': 'merged', 'changes': changes, 'confirmations': confirmations, 'conflicts': conflicts, 'component': incoming}
    updated = apply_candidate(row, candidate)
    p = updated['spec_provenance']['technical_specs__cores']
    assert p['source'] == 'buildcores' and p['sources'] == ['buildcores', 'pc_part_dataset']
    assert apply_candidate(updated, candidate) == updated


def test_nullable_legacy_sections_are_filled_without_touching_commerce():
    incoming = mapped('cpu', 'AMD Ryzen 5 5600')
    current = deepcopy(incoming)
    current.update(technical_specs=None, spec_provenance=None, external_ids=None, prices=[{'price': 123}])
    changes, confirmations, conflicts = merge_plan(current, incoming)
    candidate = {'status': 'merged', 'changes': changes, 'confirmations': confirmations, 'conflicts': conflicts,
                 'component': incoming, 'action': 'merge', 'canonical_id': current['id']}
    updated = apply_candidate(current, candidate)
    assert updated['technical_specs']['cores'] == 6 and updated['prices'] == [{'price': 123}]
    db = mongomock.MongoClient().db
    db.components.insert_one(current)
    assert promote_candidate(db.components, candidate) == 'merged'
    assert db.components.find_one()['technical_specs']['threads'] == 12


def test_late_merge_field_does_not_gain_empty_confirmation_on_replay():
    current = mapped('gpu', 'ASUS Dual RTX 4060', chipset='RTX 4060')
    current['technical_specs'].pop('length_mm')
    current['spec_provenance'].pop('technical_specs__length_mm')
    source = snapshot_double([('gpu', 'second-record', raw('gpu', current['name'], chipset='RTX 4060'), 'b.json', None)])
    report, _ = build_plan(source, [current], {'gpu'})
    db = mongomock.MongoClient().db
    db.components.insert_one(current)
    stage_and_apply(db, report, promote=True)
    first = db.components.find_one()
    assert 'confirmations' not in first['spec_provenance']['technical_specs__length_mm']
    stage_and_apply(db, report, promote=True)
    assert db.components.find_one() == first


def test_concurrent_field_update_and_identity_change_block_promotion():
    current = mapped('cpu', 'AMD Ryzen 5 5600')
    current['technical_specs'].pop('threads')
    db = mongomock.MongoClient().db
    db.components.insert_one(current)
    source = snapshot_double([('cpu', 'a', raw('cpu', current['name']), 'a.json', None)])
    report, _ = build_plan(source, [current], {'cpu'})
    db.components.update_one({}, {'$set': {'technical_specs.threads': 24}})
    assert promote_candidate(db.components, report['candidates'][0]) == 'concurrent_spec_conflict'
    assert db.components.find_one()['technical_specs']['threads'] == 24
    db.components.update_one({}, {'$set': {'name': 'AMD Ryzen 5 5600X'}})
    assert promote_candidate(db.components, report['candidates'][0]) == 'concurrent_identity_conflict'


def test_review_digest_changes_with_data_but_not_timestamps():
    source = snapshot_double([('cpu', 'a', raw('cpu', 'AMD Ryzen 5 5600'), 'a.json', None)])
    report, _ = build_plan(source, [], {'cpu'})
    changed = deepcopy(report)
    changed['candidates'][0]['imported_at'] = 'another time'
    assert plan_digest(report) == plan_digest(changed)
    changed['candidates'][0]['component']['technical_specs']['cores'] = 99
    assert plan_digest(report) != plan_digest(changed)


def test_snapshot_checksum_schema_size_and_path_checks(tmp_path):
    root = tmp_path
    (root / 'schemas').mkdir()
    (root / 'open-db/CPU').mkdir(parents=True)
    schema = {'type': 'object', 'required': ['metadata'], 'properties': {'metadata': {'type': 'object'}}}
    data = raw('cpu', 'AMD Ryzen 5 5600', opendb_id='abc')
    files = {'schemas/CPU.schema.json': schema, 'open-db/CPU/abc.json': data}
    checksums = {}
    for name, value in files.items():
        encoded = json.dumps(value).encode()
        (root / name).write_bytes(encoded)
        checksums[name] = hashlib.sha256(encoded).hexdigest()
    (root / 'snapshot.json').write_text(json.dumps({**META, 'files': checksums}))
    snapshot = Snapshot(root, 'buildcores')
    assert len(list(snapshot.records({'cpu'}))) == 1
    with pytest.raises(ValueError, match='unsafe_path'):
        snapshot.read('../outside.json')
    (root / 'open-db/CPU/abc.json').write_text('{}')
    record = next(Snapshot(root, 'buildcores').records({'cpu'}))
    assert record[-1] == 'checksum_mismatch'
    with pytest.raises(ValueError, match='schema'):
        validate_dataset({'name': 'AMD CPU', 'core_count': True}, 'cpu')


def test_import_memory_budget_is_enforced(monkeypatch):
    from catalog_specs import import_resources
    assert import_resources.check_memory_budget() > 0
    monkeypatch.setattr(import_resources, 'MAX_RSS_BYTES', 1)
    with pytest.raises(MemoryError):
        import_resources.check_memory_budget()


def test_cli_dry_run_staging_review_and_local_apply(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    import import_external_catalog as cli
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    source = tmp_path / 'snapshot'
    (source / 'schemas').mkdir(parents=True)
    (source / 'open-db/CPU').mkdir(parents=True)
    checksums = {}
    for name, data in {'schemas/CPU.schema.json': {'type': 'object'},
        'open-db/CPU/abc.json': raw('cpu', 'AMD Ryzen 5 5600', opendb_id='abc')}.items():
        encoded = json.dumps(data).encode()
        (source / name).write_bytes(encoded)
        checksums[name] = hashlib.sha256(encoded).hexdigest()
    (source / 'snapshot.json').write_text(json.dumps({**META, 'files': checksums}))
    seed = tmp_path / 'seed.jsonl'
    seed.write_text('')
    reviewed, staged, applied, target = [tmp_path / p for p in ('reviewed.json', 'staged.json', 'applied.json', 'expanded.jsonl')]
    common = ['--snapshot', str(source), '--jsonl', str(seed), '--category', 'cpu', '--local-output', str(target)]
    cli.main('buildcores', common + ['--dry-run', '--output', str(reviewed)])
    assert not target.exists() and seed.read_text() == ''
    cli.main('buildcores', common + ['--apply', '--output', str(staged)])
    assert not target.exists()
    cli.main('buildcores', common + ['--apply', '--promote', '--review-plan', str(reviewed), '--output', str(applied)])
    assert len(cli.read_jsonl(target)) == 1 and seed.read_text() == ''
    modified = json.loads(reviewed.read_text())
    modified['candidates'][0]['component']['technical_specs']['cores'] = 99
    reviewed.write_text(json.dumps(modified))
    with pytest.raises(ValueError, match='Plan changed'):
        cli.main('buildcores', common + ['--apply', '--promote', '--review-plan', str(reviewed), '--output', str(applied)])
