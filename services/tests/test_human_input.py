"""Human input features, strict variants, field trust and bounded resolution."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mongomock
import pytest

from catalog_specs.human_input import parse_input, human_keys
from catalog_specs.human_resolver import resolve_input, score_candidate, mongo_bundle
from catalog_specs.human_index import build_human_index, family_projections
from catalog_specs.external_identity import search_metadata

INPUTS = [
    ('cpu', 'ryzen 7 5700x', 'number', '5700'), ('cpu', 'AMD Ryzen 7 5700X', 'suffix', 'X'),
    ('cpu', 'Processador Ryzen 7 5700X', 'tier', '7'), ('cpu', 'Ryzen5700X', 'number', '5700'),
    ('cpu', 'Ryzen 5700X', 'suffix', 'X'), ('cpu', '5700X', 'suffix', 'X'),
    ('cpu', '5600X', 'suffix', 'X'), ('cpu', '5600G', 'suffix', 'G'),
    ('cpu', '7800X3D', 'suffix', 'X3D'), ('cpu', 'i5 12400F', 'suffix', 'F'),
    ('cpu', 'i5-13600K', 'suffix', 'K'), ('cpu', 'Intel Core i5-13600KF', 'suffix', 'KF'),
    ('gpu', 'rtx4060ti', 'suffix', 'TI'), ('gpu', 'RTX 4060 Ti', 'number', '4060'),
    ('gpu', 'GeForce RTX4060Ti', 'suffix', 'TI'), ('gpu', 'Nvidia GeForce RTX 4060 Ti', 'series', 'rtx'),
    ('gpu', 'RTX 4070', 'suffix', ''), ('gpu', 'RTX 4070 Super', 'suffix', 'SUPER'),
    ('gpu', 'RTX 4070 Ti', 'suffix', 'TI'), ('gpu', 'RTX4070TiSuper', 'suffix', 'TI SUPER'),
    ('gpu', 'RX 7800 XT', 'suffix', 'XT'), ('gpu', 'RX7900XTX', 'suffix', 'XTX'),
    ('gpu', 'RX 7900 GRE', 'suffix', 'GRE'), ('gpu', 'RTX 4060 Ti 16GB', 'vram', '16GB'),
    ('ram', '32GB DDR4 3200', 'capacity', '32GB'), ('ram', '2x16GB DDR4 3200', 'modules', '2x16GB'),
    ('ram', '16 GB 3200 DDR4', 'speed', '3200MHz'), ('ram', 'DDR5 32GB 6000', 'memory_type', 'DDR5'),
    ('ram', '2×16GB DDR5 6000 CL30', 'capacity', '32GB'), ('ram', 'DDR4 8GB 2666MHz', 'capacity', '8GB'),
    ('ram', '4x8GB DDR4 3200 CL16', 'cas_latency', 16), ('ram', 'DDR5 16GB 5600MT/s', 'speed', '5600MHz'),
    ('psu', '650w', 'wattage', 650), ('psu', '650W 80 plus gold', 'efficiency', 'Gold'),
    ('psu', 'Fonte 750 watts', 'wattage', 750), ('psu', 'Corsair 650W', 'wattage', 650),
    ('psu', '450 watts', 'wattage', 450), ('psu', '850W 80+ Platinum', 'efficiency', 'Platinum'),
    ('storage', '1TB NVMe', 'capacity', '1TB'), ('storage', 'SSD 1TB', 'capacity', '1TB'),
    ('storage', 'NVMe 2TB', 'capacity', '2TB'), ('storage', '500GB SATA SSD', 'capacity', '500GB'),
    ('storage', 'NVMe 1TB PCIe 4.0 M.2', 'pcie_generation', 4),
    ('motherboard', 'B550M', 'chipset', 'B550M'), ('motherboard', 'B550M DDR4', 'memory_type', 'DDR4'),
    ('motherboard', 'B650 DDR5', 'chipset', 'B650'), ('motherboard', 'B760M DDR4', 'memory_type', 'DDR4'),
    ('motherboard', 'Z790 DDR5', 'chipset', 'Z790'), ('motherboard', 'AM5 B650 ATX DDR5', 'socket', 'AM5'),
    ('case', 'ATX', None, None), ('case', 'mATX', None, None), ('case', 'Mini-ITX GPU até 300mm', 'max_gpu_length_mm', 300),
]


@pytest.mark.parametrize('category,text,key,value', INPUTS)
def test_explicit_features(category, text, key, value):
    parsed = parse_input(text, category)
    assert parsed['errors'] == []
    if key:
        assert parsed['features'][key] == value
    else:
        assert parsed['compatibility']['supported_form_factors']


AMBIGUOUS = [('ram', '16GB ou 32GB DDR4'), ('ram', 'DDR4 DDR5 32GB'), ('ram', '3200 3600 DDR4 16GB'),
             ('ram', '32GB 2x8GB DDR4'), ('psu', '650W 750W'), ('psu', '500-650W'),
             ('storage', '1TB 2TB NVMe'), ('storage', '1TB SATA NVMe'),
             ('cpu', 'Ryzen 5600X ou 5600G'), ('gpu', 'RTX 4070 RTX 4070 Super')]


@pytest.mark.parametrize('category,text', AMBIGUOUS)
def test_ambiguous_explicit_values_fail_closed(category, text):
    parsed = parse_input(text, category)
    assert parsed['errors']
    result, _ = resolve_input(parsed, {'candidates': []})
    assert result['source'] == 'user' and not result['specifications'] and not result['compatibility']


def row(category, name, **changes):
    result = {'id': name.lower().replace(' ', '-'), 'name': name, 'category': category, 'brand': 'AMD' if category == 'cpu' else 'NVIDIA',
              'technical_specs': {}, 'compatibility': {}, 'identity_scope': 'model' if category == 'cpu' else 'family'}
    result.update(changes)
    result.update(search_metadata(result))
    return result


@pytest.mark.parametrize('category,left,right', [('cpu','5600','5600X'), ('cpu','5600','5600G'), ('cpu','5700','5700X'),
    ('gpu','RTX 3060','RTX 3060 Ti'), ('gpu','RTX 4060','RTX 4060 Ti'), ('gpu','RTX 4070','RTX 4070 Super'),
    ('gpu','RTX 4070','RTX 4070 Ti'), ('gpu','RX 7800','RX 7800 XT')])
def test_suffix_conflicts_are_mandatory_even_with_a_misleading_alias(category, left, right):
    candidate_name = 'AMD Ryzen 5 ' + right if category == 'cpu' else right
    candidate = row(category, candidate_name, aliases=[left])
    parsed = parse_input(left, category)
    _, _, rejected = score_candidate(parsed, candidate)
    assert any('model_conflict' in error for error in rejected)


@pytest.mark.parametrize('category,query,section,key,stored', [
    ('ram','16GB DDR4 3200','technical_specs','capacity','32GB'),
    ('ram','32GB DDR4 3200','compatibility','memory_type','DDR5'),
    ('storage','1TB NVMe','technical_specs','capacity','2TB'),
    ('psu','650W','technical_specs','wattage',750),
    ('gpu','RTX 4060 Ti 16GB','technical_specs','memory','8GB GDDR6'),
])
def test_explicit_discriminators_reject_conflicting_catalog_values(category, query, section, key, stored):
    candidate = row(category, query)
    candidate[section][key] = stored
    assert 'conflicting_' + key in score_candidate(parse_input(query, category), candidate)[2]


def test_generic_ram_never_selects_even_a_single_vendor_sku():
    candidate = row('ram', '16GB DDR4 3200', brand='Kingston', identity_scope='sku')
    result, trace = resolve_input(parse_input('16GB DDR4 3200', 'ram'), {'candidates': [candidate]})
    assert result['source'] == 'derived' and result['catalog_id'] is None and result['resolution_scope'] == 'generic'
    assert result['specifications']['capacity'] == '16GB'
    assert trace['candidates'][0]['rejections'] == ['generic_input_cannot_select_sku']


def test_family_cannot_supply_physical_sku_fields():
    gpu = row('gpu', 'RTX 4060 Ti', technical_specs={'memory': '8GB', 'length_mm': 240}, compatibility={'min_psu_watts': 550})
    result, _ = resolve_input(parse_input('rtx4060ti', 'gpu'), {'candidates': [gpu]})
    assert result['resolution_scope'] == 'family' and 'length_mm' not in result['specifications']
    board = row('motherboard', 'Placa mae B550M AM4 DDR4', identity_scope='family', brand='AMD',
                technical_specs={'memory_slots': 4, 'max_memory_gb': 128}, compatibility={'socket': 'AM4', 'memory_type': 'DDR4'})
    result, _ = resolve_input(parse_input('B550M', 'motherboard'), {'candidates': [board]})
    assert result['compatibility']['socket'] == 'AM4'
    assert result['specifications'] == {}


def test_no_truncation_or_first_winner_on_ambiguous_cpu_tiers():
    candidates = [row('cpu', f'AMD Ryzen {tier} 5700X') for tier in (5, 7)]
    result, trace = resolve_input(parse_input('Ryzen5700X', 'cpu'), {'candidates': candidates})
    assert result['source'] == 'user' and 'ambiguous_best_candidates' in trace['rejections']
    result, _ = resolve_input(parse_input('Ryzen5700X', 'cpu'), {'candidates': candidates[:1], 'overflow': True})
    assert result['source'] == 'user'


def test_offline_index_does_not_create_or_change_technical_components_and_has_indexed_keys():
    db = mongomock.MongoClient().db
    rows = [row('cpu','AMD Ryzen 7 5700X'), row('motherboard','ASUS B660M DDR4', identity_scope='sku',
            compatibility={'socket':'LGA1700','memory_type':'DDR4','form_factor':'Micro-ATX'})]
    db.components.insert_many(deepcopy(rows))
    before = list(db.components.find({}, {'_id':0}))
    report = build_human_index(db)
    assert report['before'] == report['after'] == 2
    for a, b in zip(before, db.components.find({}, {'_id':0})):
        b.pop('human_lookup_keys')
        assert a == b
    parsed = parse_input('Ryzen5700X','cpu')
    bundle = mongo_bundle(db.components,parsed)
    assert resolve_input(parsed,bundle)[0]['catalog_id'] == rows[0]['id']
    assert db.components.index_information()['ix_catalog_human_lookup_keys']['key'] == [('category',1),('human_lookup_keys',1)]
    projection = db.catalog_human_families.find_one({'key':'board:B660M:DDR4'})
    assert projection['fields']['compatibility.socket'] == 'LGA1700'
    assert not any('slots' in p or 'max_memory' in p for p in projection['fields'])


def test_family_projection_requires_complete_unanimous_evidence():
    a = row('motherboard','ASUS B660M DDR4', compatibility={'socket':'LGA1700','memory_type':'DDR4','form_factor':'Micro-ATX'})
    b = row('motherboard','Gigabyte B660M DDR4', compatibility={'memory_type':'DDR4','form_factor':'ATX'})
    projection = next(p for p in family_projections([a,b]) if p['key']=='board:B660M:DDR4')
    assert 'compatibility.socket' not in projection['fields']
    assert 'compatibility.form_factor' not in projection['fields']


@pytest.mark.parametrize('category,text', [('cpu','Gigabyte Ryzen 7 5700X'), ('ram','RTX 4060 16GB'),
    ('gpu','AMD Ryzen 7 5700X'), ('storage','Intel Core i5 12400F 1TB')])
def test_category_and_manufacturer_contradictions_cannot_supply_fields(category,text):
    parsed = parse_input(text,category)
    result,_ = resolve_input(parsed,{'candidates':[]})
    assert parsed['errors'] and result['source']=='user'
    assert result['field_sources']=={}


def test_generic_power_label_cannot_be_promoted_via_a_bad_mpn():
    candidate = row('psu','Corsair unknown',brand='Corsair',identity_scope='sku',mpn=['650W'])
    result,_ = resolve_input(parse_input('650W','psu'),{'candidates':[candidate]})
    assert result['source']=='derived' and result['catalog_id'] is None


def test_explicit_gpu_length_belongs_to_the_user_not_a_family_representative():
    gpu=row('gpu','RTX 4060 Ti',technical_specs={'memory':'8GB','length_mm':240},compatibility={'min_psu_watts':550})
    result,_=resolve_input(parse_input('RTX 4060 Ti comprimento 400mm','gpu'),{'candidates':[gpu]})
    assert result['catalog_id']==gpu['id'] and result['specifications']['length_mm']==400
    assert result['field_sources']['technical_specs.length_mm']=='user_text'


def test_conflicting_socket_cannot_be_smuggled_through_a_derived_board_family():
    parsed=parse_input('B550M AM5 DDR4','motherboard')
    result,trace=resolve_input(parsed,{'candidates':[],'family':{'fields':{'compatibility.socket':'AM4'}}})
    assert result['source']=='user' and trace['rejections']==['family_field_conflict_socket']
