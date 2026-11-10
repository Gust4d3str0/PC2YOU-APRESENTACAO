"""Technical enrichment must reject ambiguity and preserve every existing value."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import mongomock
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from backfill_demo_specs import backfill_collection, backfill_jsonl
from catalog_specs import plan_backfill, apply_plan, normalize_spec
from catalog_specs.persistence import write_mongo_plan


def component(category='cpu', **attributes):
    return {'id': 'real-sku', 'name': 'Real SKU', 'category': category, 'technical_specs': {},
            'compatibility': {}, 'identity_scope': 'sku', 'prices': [{'price': 123}],
            'external_enrichment': {'mercado_livre': {'product_id': 'MLB12345678', 'match_status': 'matched',
                'source': 'mercado_livre_product_api', 'attributes': {k: {'value': v} for k, v in attributes.items()}}}}


@pytest.mark.parametrize('key,raw,expected', [
    ('wattage', '650 W', 650), ('capacity', '16 GB', '16GB'), ('memory_type', 'DDR 4', 'DDR4'),
    ('memory_type', 'DDR4 SDRAM', 'DDR4'), ('form_factor', 'Micro ATX', 'Micro-ATX'),
    ('socket', 'AM 4', 'AM4'), ('socket', 'FCLGA1700', 'LGA1700'),
    ('socket', 'AM4 Socket', 'AM4'), ('length_mm', '26,21 cm', 262.1),
    ('max_memory_gb', '128 GB', 128), ('max_memory_gb', 128, 128),
    ('modules', '2 x 8 GB', '2x8GB'), ('memory_slots', '4 x DIMM', 4),
    ('speed', '3.2 GHz', '3200MHz'), ('speed', '3200 MT/s', '3200MHz'),
    ('interface', 'NVMe (PCIe Gen 3 x4)', 'NVMe PCIe 3.0'),
])
def test_normalization(key, raw, expected):
    assert normalize_spec(key, raw) == expected


@pytest.mark.parametrize('key,raw', [
    ('socket', 'AM4, AM5'), ('socket', 'FCBGA1700, FCLGA1700'), ('socket', '1700'),
    ('memory_type', 'DDR4, DDR5'), ('wattage', '500-650 W'), ('wattage', True),
    ('length_mm', '30 x 20 cm'), ('modules', '8 GB'), ('cores', '6/12'), ('capacity', '16GB or 32GB'),
    ('memory_slots', '2 x 32 GB'), ('interface', 'SATA III, SATA II'),
])
def test_ambiguous_values_do_not_become_specs(key, raw):
    assert normalize_spec(key, raw) is None


def test_all_components_jsonl_dry_run_idempotence_and_existing_values(tmp_path):
    rows = [component(CPU_CORES_NUMBER='6', CPU_THREADS_NUMBER='12', TDP='65 W', COMPATIBLE_SOCKETS='AM4'),
            component('psu', POWER_OUTPUT='650 W')]
    rows[1]['id'] = 'real-psu'
    rows[0]['technical_specs']['threads'] = 8  # Existing data wins, even when the API disagrees.
    path = tmp_path / 'components.jsonl'
    original = ''.join(json.dumps(r) + '\n' for r in rows)
    path.write_text(original, encoding='utf-8')
    plans = backfill_jsonl(path, sources=[], references=[])
    assert len(plans) == 2 and path.read_text(encoding='utf-8') == original
    backfill_jsonl(path, True, sources=[], references=[])
    result = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert result[0]['technical_specs']['threads'] == 8
    assert result[0]['technical_specs']['cores'] == 6
    assert result[0]['technical_specs']['socket'] == 'AM4'
    assert result[0]['prices'] == rows[0]['prices']
    assert result[1]['technical_specs']['wattage'] == 650
    assert result[0]['spec_provenance']['technical_specs__cores']['product_id'] == 'MLB12345678'
    assert backfill_jsonl(path, True, sources=[], references=[]) == []


def test_mongo_null_sections_concurrent_changes_and_no_inserts():
    collection = mongomock.MongoClient().catalog.components
    row = component(CPU_CORES_NUMBER='6', CPU_THREADS_NUMBER='12', TDP='65 W', COMPATIBLE_SOCKETS='AM4')
    row['technical_specs'] = None
    row['spec_provenance'] = None
    collection.insert_one(row)
    assert backfill_collection(collection, references=[])
    assert collection.find_one()['technical_specs'] is None
    backfill_collection(collection, True, references=[])
    assert collection.find_one()['technical_specs']['threads'] == 12
    assert backfill_collection(collection, True, references=[]) == []
    assert collection.count_documents({}) == 1
    assert backfill_collection(mongomock.MongoClient().catalog.components, True) == []

    collection.update_one({}, {'$unset': {'technical_specs.cores': '', 'spec_provenance.technical_specs__cores': ''}})
    stale = collection.find_one()
    plan = plan_backfill(stale)
    collection.update_one({}, {'$set': {'technical_specs.cores': 99}})
    assert write_mongo_plan(collection, stale, plan) == []
    assert collection.find_one()['technical_specs']['cores'] == 99


def test_conflicts_domains_and_generic_gpu_dimensions_are_not_propagated():
    row = component('gpu', LENGTH='208 mm', WIDTH='120 mm', POWER_REQUIREMENT='650 W', MEMORY_SIZE='8 GB')
    row['identity_scope'] = 'gpu-model-and-vram-class'
    plan = plan_backfill(row)
    assert {c['field'] for c in plan['changes']} == {'technical_specs.memory'}
    row['identity_scope'] = 'sku'
    row['external_enrichment']['mercado_livre']['attributes']['WIDTH']['value'] = '300 mm'
    assert not any(c['field'] == 'technical_specs.length_mm' for c in plan_backfill(row)['changes'])
    row['external_enrichment']['mercado_livre']['external_conflict'] = True
    assert not plan_backfill(row)['changes']


def test_conflicting_sources_leave_missing_and_cpu_ram_does_not_fill_board():
    row = component(CPU_CORES_NUMBER='6', SUPPORTED_RAM_MEMORY_TYPES='DDR4, DDR5', MAX_RAM_MEMORY_SIZE_SUPPORTED='128 GB')
    doc = {'product_id': 'MLB87654321', 'attributes': {'CPU_CORES_NUMBER': {'value': '8'}},
           'matches': {row['id']: {'status': 'matched', 'conflicts': []}}}
    assert not plan_backfill(row, [doc])['changes']
    assert any(r['reason'] == 'conflicting_sources' for r in plan_backfill(row, [doc])['rejected'])
    assert 'max_memory_gb' not in apply_plan(row, plan_backfill(row))['technical_specs']


def test_bad_persisted_tdp_is_explicitly_blocked():
    row = component(TDP='65 W')
    row['external_enrichment']['mercado_livre']['product_id'] = 'MLB27860992'
    assert plan_backfill(row)['changes'] == []
    assert plan_backfill(row)['rejected'][0]['verification_source'].startswith('https://www.intel.com/')


def test_module_total_conflict_and_wrong_domain_remain_unchecked():
    row = component('ram', RAM_MEMORY_MODULE_TOTAL_CAPACITY='32 GB', RAM_MEMORY_MODULES='1 x 2 GB')
    assert not any(c['field'] == 'technical_specs.modules' for c in plan_backfill(row)['changes'])
    row = component(CPU_CORES_NUMBER='6')
    row['external_enrichment']['mercado_livre']['domain_id'] = 'MLB-NOTEBOOKS'
    assert plan_backfill(row)['changes'] == []
    row['external_enrichment'] = []
    assert plan_backfill(row)['changes'] == []


def test_reviewed_expansion_is_reproducible_and_has_no_synthetic_commercial_data():
    from build_catalog_coverage import build
    before = (ROOT / 'api-catalogo/catalog_coverage_v2.json').read_bytes()
    rows, _ = build()
    assert (ROOT / 'api-catalogo/catalog_coverage_v2.json').read_bytes() == before
    assert len({r['id'] for r in rows}) == len(rows) == 29
    for row in rows:
        assert row['prices'] == row['price_history'] == [] and row['benchmark'] == {}
        assert row['external_enrichment']['mercado_livre']['product_id']
        assert row['spec_provenance']
