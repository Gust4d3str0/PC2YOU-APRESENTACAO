import mongomock

from scripts.audit_seed_commercial_data import archive, audit

SEED_PRICE = {'store': 'Kabum', 'price': 100, 'url': 'https://www.kabum.com.br/busca/x', 'source': 'seed'}
SEED_HISTORY = {'date': '2026-02-01', 'min_price': 90, 'source': 'seed'}
ML_PRICE = {'store': 'ML', 'price': 120, 'url': 'https://produto.mercadolivre.com.br/MLB-1', 'source': 'mercado_livre'}
REAL_HISTORY = {'date': '2026-11-01', 'min_price': 110, 'source': 'mercado_livre'}


def collection():
    c = mongomock.MongoClient().db.components
    c.insert_many([{'id': 'a', 'prices': [SEED_PRICE, ML_PRICE], 'price_history': [SEED_HISTORY, REAL_HISTORY]},
                   {'id': 'b', 'prices': [SEED_PRICE, {**SEED_PRICE, 'store': 'Pichau'}], 'price_history': [SEED_HISTORY]},
                   {'id': 'c', 'prices': [], 'price_history': []}, {'id': 'd'}])
    return c


def test_dry_run_counts_seed_and_real_entries_without_writing():
    c = collection()
    before = list(c.find({}, {'_id': 0}))
    report = audit(c.find({}))
    assert report['components'] == 4 and report['with_seed_prices'] == 2 and report['seed_prices'] == 3 and report['seed_history'] == 2
    assert report['real_prices_by_source'] == {'mercado_livre': 1} and report['real_history'] == 1
    assert report['seed_stores'] == {'Kabum': 2, 'Pichau': 1}
    assert list(c.find({}, {'_id': 0})) == before


def test_apply_archives_only_seed_entries_and_is_idempotent():
    c = collection()
    assert archive(c) == 2
    a = c.find_one({'id': 'a'})
    assert a['prices'] == [ML_PRICE] and a['price_history'] == [REAL_HISTORY]
    assert a['legacy_seed_commercial']['prices'] == [SEED_PRICE] and a['legacy_seed_commercial']['price_history'] == [SEED_HISTORY]
    assert c.find_one({'id': 'b'})['prices'] == [] and len(c.find_one({'id': 'b'})['legacy_seed_commercial']['prices']) == 2
    assert c.find_one({'id': 'c'}) == {'_id': c.find_one({'id': 'c'})['_id'], 'id': 'c', 'prices': [], 'price_history': []}
    assert archive(c) == 0
    after = audit(c.find({}))
    assert after['seed_prices'] == 0 and after['seed_history'] == 0 and after['already_archived'] == 2
