from copy import deepcopy
import mongomock
import seed
import pytest
from product_matching.matcher import match_product
from services import price_summary, _public_component
from catalog_specs.coverage import audit
import json
from pathlib import Path


def test_startups_and_module_reload_preserve_all_existing_fields(monkeypatch):
    collection = mongomock.MongoClient().db.components
    collection.create_index('id', unique=True)
    monkeypatch.setattr(seed, 'get_components_collection', lambda: collection)
    assert seed.seed_components() == 150
    collection.update_one({'id': 'ryzen-5-7600'}, {'$set': {'name': 'Corrected manually', 'prices': [], 'observations': ['keep'], 'real_image': 'keep'}})
    snapshot = deepcopy(list(collection.find()))
    assert seed.seed_components() == 0
    assert seed.seed_components() == 0
    assert list(collection.find()) == snapshot


def test_existing_ids_are_preserved_even_with_empty_or_custom_fields(monkeypatch):
    collection = mongomock.MongoClient().db.components
    collection.insert_one({'id': 'ryzen-5-7600', 'name': 'User identity', 'price_history': ['preserve']})
    before = collection.find_one({'id': 'ryzen-5-7600'})
    monkeypatch.setattr(seed, 'get_components_collection', lambda: collection)
    seed.seed_components()
    assert collection.find_one({'id': 'ryzen-5-7600'}) == before


def test_fresh_mongo_seed_has_the_same_technical_coverage_as_the_backfilled_snapshot(monkeypatch):
    collection = mongomock.MongoClient().db.components
    monkeypatch.setattr(seed, 'get_components_collection', lambda: collection)
    seed.seed_components()
    snapshot = [json.loads(line) for line in (Path(__file__).resolve().parents[2] / 'demo-data/components.jsonl').read_text(encoding='utf-8').splitlines()]
    assert audit(list(collection.find()))['categories'] == audit(snapshot)['categories']


@pytest.mark.parametrize('title,cid', [('AMD Ryzen 5 7600', 'ryzen-5-7600'),
    ('AMD Ryzen 7 7800X3D 8 nucleos 16 threads', 'ryzen-7-7800x3d'),
    ('AMD Ryzen 7 7800X3D AM5', 'ryzen-7-7800x3d'),
    ('AMD Ryzen 7 7800X3D 4.2GHz', 'ryzen-7-7800x3d')])
def test_four_audited_suspect_descriptions_resolve_correctly_after_identity_sync(title, cid):
    result = match_product({'title': title}, seed.COMPONENTS)
    assert result.component_id == cid and result.confidence_level == 'high'


def test_explicitly_expired_catalog_coupon_is_not_a_current_offer():
    item = deepcopy(seed.COMPONENTS[0])
    item['prices'] = [{'price': 1, 'store': 'Original', 'source': 'seed', 'coupon': 'OLD', 'valid_until': '2000-01-01T00:00:00Z'}]
    assert price_summary(item)['best_offer'] is None
    assert not _public_component(item)['prices']
