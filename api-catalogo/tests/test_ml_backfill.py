import importlib.util
import json
import sys
from pathlib import Path

import mongomock
import pytest

import ml_products as ml
from test_commerce import NOW, promo
from test_ml_products import CPU_RAW, GPU_RAW, database

ROOT = Path(__file__).resolve().parents[2]


def load_script():
    spec = importlib.util.spec_from_file_location('enrich_script', ROOT / 'scripts/enrich_mercado_livre_products.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['enrich_script'] = module
    spec.loader.exec_module(module)
    return module


class FakeApi:
    def __init__(self, products=None, items=None):
        self.products, self.items, self.calls = products or {}, items or {}, []

    def get_product(self, product_id):
        self.calls.append(('product', product_id))
        raw = self.products.get(product_id)
        return ml.ApiResult('ok', 200, raw) if raw else ml.ApiResult('not_found', 404)

    def get_item(self, item_id):
        self.calls.append(('item', item_id))
        return ml.ApiResult(*self.items.get(item_id, ('forbidden', 403)))

    def get(self, path, params=None):
        return ml.ApiResult('error')


@pytest.fixture
def script(monkeypatch, tmp_path):
    module = load_script()
    return module


def mapping(tmp_path, data):
    path = tmp_path / 'map.json'
    path.write_text(json.dumps({'components': data}), encoding='utf-8')
    return path


def ml_promo(url, resolved=None):
    row = promo(2789, url=url, store='Mercado Livre')
    row['raw_text'] = 'Gigabyte GeForce RTX 5060 Ti 8GB'
    if resolved:
        row['offer']['resolved_url'] = resolved
    return row


def test_dry_run_counts_ids_without_writing(script, monkeypatch, tmp_path):
    db = database()
    db.telegram_promotions.insert_many([ml_promo('https://meli.la/a', 'https://www.mercadolivre.com.br/social/x?ref=1'),
                                        ml_promo('https://meli.la/b', 'https://www.mercadolivre.com.br/placa/p/MLB78085963?wid=MLB7833387058')])
    fake = FakeApi({'MLB78085963': GPU_RAW})
    monkeypatch.setattr(script.ml_products, 'api', fake)
    before = {name: list(db[name].find({})) for name in ('components', 'telegram_promotions')}
    report = script.run(db, mapping(tmp_path, {}), apply=False)
    stats = report['stats']
    assert stats['ml_promotions_found'] == 2 and stats['product_ids_found_in_promotions'] == 1 and stats['item_ids_found'] == 1
    assert stats['unique_product_ids'] == 1 and stats['products_api_outcomes'] == {'ok': 1}
    assert stats['item_ids_probed'] == 1 and stats['item_api_forbidden'] == 1 and stats['could_validate_price_in_future'] == 0
    assert {name: list(db[name].find({})) for name in before} == before
    assert 'ml_integration_state' not in db.list_collection_names() and 'external_product_enrichment' not in db.list_collection_names()


def test_no_fetch_mode_makes_no_ml_call(script, monkeypatch, tmp_path):
    db = database()
    fake = FakeApi({'MLB78085963': GPU_RAW})
    monkeypatch.setattr(script.ml_products, 'api', fake)
    report = script.run(db, mapping(tmp_path, {'rtx-5060-ti-8gb': ['MLB78085963']}), apply=False, fetch=False)
    assert fake.calls == [] and report['stats']['unique_product_ids'] == 1 and report['stats']['manual_mapping_pairs'] == 1


def test_apply_enriches_each_product_once_and_leaves_promotions_alone(script, monkeypatch, tmp_path):
    db = database()
    db.telegram_promotions.insert_one(ml_promo('https://meli.la/a', 'https://www.mercadolivre.com.br/placa/p/MLB78085963'))
    fake = FakeApi({'MLB78085963': GPU_RAW})
    monkeypatch.setattr(script.ml_products, 'api', fake)
    promos_before = list(db.telegram_promotions.find({}))
    path = mapping(tmp_path, {'rtx-5060-ti-8gb': ['MLB78085963']})
    report = script.run(db, path, apply=True)
    assert [c for c in fake.calls if c[0] == 'product'] == [('product', 'MLB78085963')]
    assert report['pairs'][0]['applied'] and report['pairs'][0]['match'] == 'matched'
    assert db.components.find_one({'id': 'rtx-5060-ti-8gb'})['external_enrichment']['mercado_livre']['product_id'] == 'MLB78085963'
    assert list(db.telegram_promotions.find({})) == promos_before
    script.run(db, path, apply=True)
    assert len([c for c in fake.calls if c[0] == 'product']) == 1                    # second run served from the 24h cache


def test_a_wrong_pair_in_the_map_is_blocked_by_the_matcher(script, monkeypatch, tmp_path):
    db = database()
    monkeypatch.setattr(script.ml_products, 'api', FakeApi({'MLB78085963': GPU_RAW}))
    report = script.run(db, mapping(tmp_path, {'rtx-5060-ti-16gb': ['MLB78085963']}), apply=True)
    assert report['pairs'][0]['applied'] is False and report['pairs'][0]['match'] == 'conflict'
    assert 'external_enrichment' not in db.components.find_one({'id': 'rtx-5060-ti-16gb'})


def test_the_report_never_contains_credentials(script, monkeypatch, tmp_path):
    db = database()
    monkeypatch.setattr(script.ml_products, 'api', FakeApi({'MLB78085963': GPU_RAW}))
    text = json.dumps(script.run(db, mapping(tmp_path, {'rtx-5060-ti-8gb': ['MLB78085963']}), apply=True))
    assert 'access_token' not in text and 'refresh_token' not in text and 'Bearer' not in text
