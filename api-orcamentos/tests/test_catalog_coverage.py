"""Real catalog regressions, including incomplete and incompatible computers."""
import sys
from pathlib import Path

import pytest
from test_ai import setup, post, request  # noqa: F401
from ai_context import enrich

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_catalog_pcs import SnapshotCatalog, run


def test_ten_varied_real_configurations_use_the_actual_endpoint():
    result = run()
    assert result['passed'] == result['total'] == 10
    for case in result['results']:
        assert case['response']['metadata']['catalog_matches'] == 7
        assert len(case['response']['compatibility']['checked_rules']) == 7
        assert not case['response']['compatibility']['unchecked_rules']


@pytest.mark.parametrize('name,cid', [
    ('Ryzen 5 5600 AMD', 'ryzen-5-5600'), ('Processador AMD Ryzen 5 5600 BOX lacrado', 'ryzen-5-5600'),
    ('Ryzen 5 5600X AMD', 'ryzen-5-5600x'), ('i5-13600K Intel', 'intel-i5-13600k'),
    ('AMD Ryzen 7 7700', 'ryzen-7-7700'),
])
def test_cpu_identity_and_commercial_words(name, cid):
    assert enrich(name, 'cpu', SnapshotCatalog())['catalog_id'] == cid


@pytest.mark.parametrize('name,cid', [
    ('RTX 3060 gamer NVIDIA', 'rtx-3060'), ('RTX 4070 Super', 'rtx-4070-super'),
    ('Placa de video Palit RTX 5050 Dual 8GB', 'palit-rtx-5050-dual-8gb'),
    ('Gigabyte RTX 5060 Ti WINDFORCE MAX OC 8GB', 'gigabyte-rtx-5060-ti-windforce-max-oc-8gb'),
    ('GV-N2060D6-6GD rev. 2.0', 'gigabyte-rtx-2060-d6-6gb-rev2'),
])
def test_gpu_explicit_aliases_and_suffixes(name, cid):
    assert enrich(name, 'gpu', SnapshotCatalog())['catalog_id'] == cid


@pytest.mark.parametrize('name', ['RTX 3060 Ti', 'RTX 4070 Ti Super', 'RTX 4060 Ti 16GB',
                                'Palit RTX 5050 Ti Dual 8GB', 'RTX 3060 8GB'])
def test_absent_gpu_variants_cannot_borrow_the_nearest_model(name):
    assert enrich(name, 'gpu', SnapshotCatalog())['catalog_id'] is None


def body():
    return request(components={'cpu': 'Ryzen 5 5600', 'motherboard': 'Gigabyte B550M K',
        'ram': 'kingston-kf432c16bb-16', 'gpu': 'RTX 3060', 'psu': '650W',
        'storage': ['ssd-nvme-1tb'], 'case': 'gabinete-lian-li-lancool'})


def prepare(setup):
    catalog = SnapshotCatalog()
    setup.catalog.items = catalog.items
    setup.catalog.search_components = catalog.search_components
    return catalog


def test_missing_modules_or_board_limit_cannot_become_compatible(setup):
    catalog = prepare(setup)
    ram = next(r for r in catalog.items if r['id'] == 'kingston-kf432c16bb-16')
    ram['technical_specs'].pop('modules')
    data = post(setup, body()).json()
    assert data['metadata']['catalog_matches'] == 7
    assert data['compatibility']['valid'] is None
    assert data['compatibility']['unchecked_rules'] == ['ram_slots']
    board = next(r for r in catalog.items if r['id'] == 'gigabyte-b550m-k')
    board['technical_specs'].pop('max_memory_gb')
    data = post(setup, body()).json()
    assert set(data['compatibility']['unchecked_rules']) == {'ram_slots', 'ram_capacity'}
    assert data['compatibility']['status'] == 'partial'


def test_real_power_and_socket_incompatibilities_are_reported(setup):
    prepare(setup)
    payload = body()
    payload['components'].update(cpu='AMD Ryzen 5 7600', psu='Corsair CV450')
    data = post(setup, payload).json()
    assert data['metadata']['catalog_matches'] == 7
    assert data['compatibility']['status'] == 'incompatible'
    assert len(data['compatibility']['checked_rules']) == 7
    assert any('sockets' in x for x in data['compatibility']['issues'])
    assert any('potência' in x for x in data['compatibility']['issues'])


def test_chipset_does_not_select_an_arbitrary_commercial_board():
    catalog = SnapshotCatalog()
    assert enrich('B550M', 'motherboard', catalog)['catalog_id'] == 'b550m-am4-ddr4'
    assert enrich('B760M', 'motherboard', catalog)['catalog_id'] is None
    assert enrich('ASUS B550M PRIME unknown-SKU', 'motherboard', catalog)['catalog_id'] is None
