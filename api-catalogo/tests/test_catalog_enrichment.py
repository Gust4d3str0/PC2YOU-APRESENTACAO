import json
from copy import deepcopy
from pathlib import Path

import mongomock
import pytest
from catalog_audit import audit_components
from catalog_audit.seed_io import load_seed
from catalog_enrichment import sync_new
from product_matching.matcher import match_product, compare_product, HIGH, MEDIUM
from schemas import Component
from services import _public_component, price_summary

ROOT = Path(__file__).resolve().parents[2]
NEW = json.loads((ROOT / 'api-catalogo/catalog_enrichment_v1.json').read_text(encoding='utf-8'))
BASE = load_seed(ROOT / 'api-catalogo/seed.py')
REFS = json.loads((ROOT / 'api-catalogo/catalog_enrichment_sources.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', NEW, ids=lambda r: r['id'])
def test_new_component_audited_sourced_and_has_no_fabricated_prices_or_scores(row):
    assert not audit_components([row], REFS)['suspected']
    assert REFS[row['id']]['sources']
    assert row['prices'] == row['price_history'] == []
    assert row['benchmark'] == {}
    public = _public_component(deepcopy(row))
    assert Component.model_validate(public).id == row['id']
    assert price_summary(public)['best_offer'] is None
    assert price_summary(public)['min_price'] is None


def test_expansion_does_not_reuse_baseline_ids_or_names():
    assert len(BASE) == 94
    assert len(NEW) == 27
    report = audit_components(BASE + NEW, REFS)
    assert report['summary']['critical_conflicts'] == 0
    assert not report['duplicate_ids'] and not report['duplicate_names']
    assert HIGH == .85 and MEDIUM == .65


@pytest.mark.parametrize('title,cid', [
    ('Placa de video MSI RTX 5060 8GB', 'rtx-5060-8gb'),
    ('INNO3D RTX 5060 Ti 8GB', 'rtx-5060-ti-8gb'),
    ('ASUS RTX 5060 Ti 16GB', 'rtx-5060-ti-16gb'),
    ('INNO3D RTX 5050 8GB', 'rtx-5050-8gb'),
    ('PowerColor Radeon RX 9060 XT 16GB', 'rx-9060-xt-16gb'),
    ('Sapphire RX 9070 XT 16GB', 'rx-9070-xt-16gb'),
    ('AMD Ryzen 5 5500X3D', 'ryzen-5-5500x3d'),
    ('AMD Ryzen 5 7500F', 'ryzen-5-7500f'),
    ('AMD Ryzen 5 8400F', 'ryzen-5-8400f'),
    ('AMD Ryzen 7 5800X3D', 'ryzen-7-5800x3d'),
    ('AMD Ryzen 5 8600G', 'ryzen-5-8600g'),
    ('AMD Ryzen 7 5700', 'ryzen-7-5700'),
    ('AMD Ryzen 7 5800XT', 'ryzen-7-5800xt'),
    ('AMD Ryzen 7 7700', 'ryzen-7-7700'),
    ('AMD Ryzen 9 7900', 'ryzen-9-7900'),
    ('AMD Ryzen 5 9600X', 'ryzen-5-9600x'),
    ('AMD Ryzen 7 9700X', 'ryzen-7-9700x'),
    ('AMD Ryzen 9 5900XT', 'ryzen-9-5900xt'),
    ('Intel Core i5-14600KF', 'intel-i5-14600kf'),
    ('Intel Core i7-14700KF', 'intel-i7-14700kf'),
    ('Placa mae MSI A520M AM4 DDR4', 'a520m-am4-ddr4'),
    ('Placa mae ASRock B450M AM4 DDR4', 'b450m-am4-ddr4'),
    ('Placa mae Asus B760M DDR4', 'b760m-lga1700-ddr4'),
    ('Placa mae MSI B760M DDR5', 'b760m-lga1700-ddr5'),
    ('Placa mae ASRock B850M AM5 DDR5', 'b850m-am5-ddr5'),
    ('Placa mae MSI B840M AM5 DDR5', 'b840m-am5-ddr5'),
    ('SSD WD Green WDS200T5G0A 2TB SATA', 'ssd-wd-green-wds200t5g0a-2tb'),
])
def test_each_added_identity_is_representable_without_variant_collision(title, cid):
    match = match_product({'title': title}, BASE + NEW)
    assert match.confidence_level == 'high' and match.component_id == cid


@pytest.mark.parametrize('left,right', [
    ('RTX 5060 8GB', 'rtx-5060-ti-8gb'),
    ('RTX 5060 Ti 8GB', 'rtx-5060-ti-16gb'),
    ('RTX 5060 Ti 16GB', 'rtx-5060-ti-8gb'),
    ('RTX 5070 12GB', 'rtx-5070-ti'),
    ('RX 9070 16GB', 'rx-9070-xt-16gb'),
    ('Placa mae B650 AM5 DDR5', 'b850m-am5-ddr5'),
    ('Placa mae B650M AM5 DDR5', 'b850m-am5-ddr5'),
    ('AMD Ryzen 5 5600G', 'ryzen-5-5600'),
    ('AMD Ryzen 5 5600X', 'ryzen-5-5600'),
    ('AMD Ryzen 7 9700X', 'ryzen-7-9800x3d'),
    ('SSD WD Green WDS200T5G0A 1TB SATA', 'ssd-wd-green-wds200t5g0a-2tb'),
    ('Placa mae B760M DDR4', 'b760m-lga1700-ddr5'),
])
def test_critical_suffix_and_capacity_conflicts_remain(left, right):
    row = next(r for r in BASE + NEW if r['id'] == right)
    match = compare_product({'title': left}, row)
    assert match.confidence_level == 'low' and match.conflicts


def test_unspecified_5060ti_memory_and_b760m_ddr_are_ambiguous():
    assert 'variant_ambiguous' in match_product({'title': 'RTX 5060 Ti'}, BASE + NEW).conflicts
    assert 'variant_ambiguous' in match_product({'title': 'Placa mae B760M'}, BASE + NEW).conflicts


def test_insert_only_sync_is_dry_by_default_and_preserves_every_existing_field():
    db = mongomock.MongoClient().db
    db.components.create_index('id', unique=True)
    existing = {**deepcopy(NEW[0]), 'prices': [{'price': 123}], 'price_history': [{'custom': True}],
                'real_image': 'original', 'images': ['custom'], 'quality': {'verified': True}, 'observations': ['keep']}
    db.components.insert_one(existing)
    original = deepcopy(list(db.components.find()))
    assert sync_new(db.components, NEW)['inserted'] == 0
    assert list(db.components.find()) == original
    result = sync_new(db.components, NEW, apply=True)
    assert result['inserted'] == len(NEW) - 1
    assert db.components.find_one({'id': existing['id']}) == original[0]
    assert sync_new(db.components, NEW, apply=True)['inserted'] == 0
    assert db.components.count_documents({}) == len(NEW)
