"""Real pricing: the seed is technical identity only; prices, conditions and status come from real offers."""
import json
from datetime import timedelta

import mongomock
import pytest
from fastapi.testclient import TestClient

import commerce
import main
import seed
import services
from database import get_components_collection
from dependencies import get_current_user
from test_commerce import NOW, database, promo

KABUM = 'https://www.kabum.com.br/produto/123/placa'
PICHAU = 'https://www.pichau.com.br/placa-de-video-inno3d-geforce-rtx-5060-ti'


def text_promo(text, price=2000, days=0, **offer):
    row = promo(price, days, **offer)
    row['raw_text'] = 'INNO3D RTX 5060 Ti 8GB ' + text
    return row


def snapshot(*promos):
    db = database()
    db.telegram_promotions.insert_many(promos)
    return commerce.build_snapshot(db, NOW), db


def only(result):
    return result['promotions'][0]


@pytest.fixture
def api():
    db = database()
    db.components.update_one({'id': 'gpu'}, {'$set': {'image': '/components/default-gpu.svg', 'description': 'GPU', 'benchmark': {}}})
    commerce._cache.clear()
    main.app.dependency_overrides[get_components_collection] = lambda: db.components
    main.app.dependency_overrides[get_current_user] = lambda: {'sub': '7'}
    try:
        yield TestClient(main.app), db
    finally:
        main.app.dependency_overrides.clear()
        commerce._cache.clear()


# --- seed is technical only -----------------------------------------------------------------------------

def test_seed_generates_no_prices_history_or_store_links():
    assert seed.COMPONENTS and all(c['prices'] == [] and c['price_history'] == [] for c in seed.COMPONENTS)
    dump = json.dumps(seed.COMPONENTS)
    for fragment in ('kabum.com.br', 'pichau.com.br', 'terabyteshop', '"source": "seed"'):
        assert fragment not in dump
    assert not hasattr(seed, '_prices') and not hasattr(seed, '_price_history')


def test_new_seed_component_keeps_technical_fields():
    item = seed.COMPONENTS[0]
    assert item['technical_specs'] and item['compatibility'] and item['benchmark'] and item['id'] and item['name']


# --- catalog works without commercial fields ------------------------------------------------------------

def test_component_without_prices_or_history_fields_loads_everywhere(api):
    client, db = api
    db.components.update_one({'id': 'gpu'}, {'$unset': {'prices': '', 'price_history': ''}})
    body = client.get('/components/gpu')
    assert body.status_code == 200 and body.json()['prices'] == [] and body.json()['price_history'] == []
    assert client.get('/components').json()[0]['prices'] == []
    assert client.get('/components/gpu/prices').json()['prices'] == []
    assert client.get('/components/gpu/price-history').json()['history'] == []
    assert client.get('/components/gpu/price-summary').json()['offers_count'] == 0
    assert client.get('/components/gpu/best-price').status_code == 404
    assert client.get('/commerce/catalog').json()['items'][0]['best_general_offer'] is None
    assert client.get('/components/gpu/offers').json()['best_offer'] is None


def test_legacy_seed_entries_in_the_database_are_never_shown_as_current(api):
    client, db = api
    db.components.update_one({'id': 'gpu'}, {'$set': {
        'prices': [{'store': 'Kabum', 'price': 1.0, 'url': 'https://www.kabum.com.br/busca/x', 'last_update': '2026-05-11', 'source': 'seed'}],
        'price_history': [{'date': '2026-02-01', 'min_price': 1, 'max_price': 2, 'average_price': 1.5, 'source': 'seed'}]}})
    component = client.get('/components/gpu').json()
    assert component['prices'] == [] and component['price_history'] == []
    assert client.get('/components/gpu/best-price').status_code == 404
    assert client.get('/components/gpu/offers').json()['best_offer'] is None
    assert client.get('/commerce/catalog').json()['items'][0]['best_current_offer'] is None
    assert db.components.find_one({'id': 'gpu'})['prices']          # the database itself is untouched


def test_seed_never_becomes_best_offer_even_beside_real_offers():
    db = database()
    db.components.update_one({'id': 'gpu'}, {'$set': {'prices': [{'source': 'seed', 'price': 1, 'store': 'Seed', 'url': KABUM, 'last_update': NOW.isoformat()}]}})
    db.telegram_promotions.insert_one(promo(2000, url=KABUM))
    result = commerce.build_snapshot(db, NOW)
    assert result['best']['gpu']['price'] == 2000 and result['best']['gpu']['source'] == 'telegram'
    assert all(o['source'] != 'seed' for rows in result['offers'].values() for o in rows)


# --- Telegram feeds the current price ---------------------------------------------------------------------

def test_telegram_promotion_becomes_the_current_price_of_the_component(api):
    client, db = api
    db.telegram_promotions.insert_one(promo(2000, url=KABUM))
    component = client.get('/components/gpu').json()
    assert [(p['source'], p['price']) for p in component['prices']] == [('telegram', 2000.0)]
    assert component['prices'][0]['conditional'] is False and component['prices'][0]['status'] == 'announced'
    assert client.get('/components/gpu/best-price').json()['best_price']['price'] == 2000
    assert client.get('/components/gpu/price-summary').json()['best_offer']['price'] == 2000


def test_real_history_comes_from_observations_not_from_curves(api):
    client, db = api
    db.product_price_history.insert_many([
        {'component_id': 'gpu', 'verified': True, 'price': 2000, 'date': '2026-11-02T10:00:00.000+00:00'},
        {'component_id': 'gpu', 'verified': True, 'price': 2200, 'date': '2026-11-02T18:00:00.000+00:00'},
        {'component_id': 'gpu', 'verified': False, 'price': 1, 'date': '2026-11-02T18:00:00.000+00:00'},
        {'component_id': 'other', 'verified': True, 'price': 5, 'date': '2026-11-02T18:00:00.000+00:00'}])
    history = client.get('/components/gpu/price-history').json()['history']
    assert history == [{'date': '2026-11-02', 'min_price': 2000.0, 'max_price': 2200.0, 'average_price': 2100.0, 'source': 'telegram', 'observations': 2}]


# --- conditions on the projected offer -------------------------------------------------------------------

@pytest.mark.parametrize('text,label', [
    ('com cupom ABC123 primeira compra', 'Somente primeira compra'),
    ('somente pelo app', 'Somente pelo app'),
    ('R$ 2.000 no PIX', 'Pagamento via PIX'),
    ('pedido mínimo de R$ 500', 'Pedido mínimo R$ 500,00'),
    ('frete Prime', 'Exclusivo para assinantes Prime'),
])
def test_announced_conditions_make_the_offer_conditional(text, label):
    row = only(snapshot(text_promo(text, url=KABUM))[0])
    assert row['is_conditional'] is True and row['status'] == 'conditional' and label in row['condition_labels']
    assert row['conditional_price'] == 2000 and row['advertised_price'] == 2000


def test_offer_without_conditions_is_just_announced():
    row = only(snapshot(promo(2000, url=KABUM))[0])
    assert row['status'] == 'announced' and row['is_conditional'] is False and row['conditional_price'] is None
    assert row['conditions']['first_purchase_only'] is None


def test_coupon_price_is_conditional_never_the_general_price():
    result, _ = snapshot(promo(1683.49, url=KABUM, coupon='AURAGAMER'))
    row = only(result)
    assert row['requires_coupon'] and row['coupon_code'] == 'AURAGAMER' and row['conditional_price'] == 1683.49
    assert result['best_general']['gpu'] is None and result['best_conditional']['gpu']['price'] == 1683.49


def test_regular_price_is_separate_from_the_conditional_price():
    row = only(snapshot(promo(1683.49, url=KABUM, coupon='AURAGAMER', original_price=1999.9))[0])
    assert row['regular_price'] == 1999.9 and row['conditional_price'] == 1683.49


def test_best_general_and_best_conditional_are_independent():
    result, _ = snapshot(promo(1839, url=KABUM), promo(1683, url=PICHAU, store='Pichau', coupon='AURAGAMER'))
    assert result['best_general']['gpu']['price'] == 1839 and result['best_conditional']['gpu']['price'] == 1683
    assert result['best']['gpu']['price'] == 1683        # overall cheapest, kept for compatibility


# --- explicit validity, stale, expired ------------------------------------------------------------------

def test_explicit_validity_from_the_text_expires_the_offer():
    gone = (NOW - timedelta(days=1)).astimezone().strftime('%d/%m')
    result, _ = snapshot(text_promo(f'válido até {gone}', url=KABUM))
    assert only(result)['status'] == 'expired' and not result['offers'] and only(result)['state'] == 'expired'


def test_explicit_validity_in_the_future_keeps_an_older_offer_current():
    later = (NOW + timedelta(days=2)).strftime('%d/%m/%Y')
    result, _ = snapshot(text_promo(f'válido até {later}', days=4, url=KABUM))
    assert only(result)['eligible'] and result['best']['gpu']['price'] == 2000


def test_stale_offer_is_flagged_but_still_listed_inside_the_limit():
    result, _ = snapshot(promo(2000, days=1.5, url=KABUM))
    row = only(result)
    assert row['status'] == 'stale' and row['freshness'] == 'aging' and row['eligible'] and result['best']['gpu']['price'] == 2000


def test_offer_beyond_the_freshness_limit_is_history_not_best_price():
    result, _ = snapshot(promo(1500, days=4, url=KABUM), promo(2000, url=PICHAU, store='Pichau'))
    assert result['best']['gpu']['price'] == 2000 and result['history']['gpu'][0]['price'] == 1500


def test_ineligible_offers_never_compete_for_best_price():
    result, _ = snapshot(promo(1000, url=None, store='NoLink'), promo(0.0 + 3000, url=KABUM))
    assert result['best']['gpu']['price'] == 3000              # no usable link -> not a best-price candidate
    assert {r['price'] for r in result['offers']['gpu']} == {1000, 3000}      # still listed


def test_current_is_never_labelled_confirmed_on_telegram_alone():
    result, _ = snapshot(promo(2789, url=KABUM, coupon='ZAFADINHO10'))
    assert only(result)['status'] != 'confirmed' and only(result)['verification']['source'] is None


# --- manual validation ------------------------------------------------------------------------------------

def test_manual_not_working_marks_invalid_removes_from_current_and_keeps_the_document(api):
    client, db = api
    db.telegram_promotions.insert_many([promo(747, url=KABUM, coupon='FARMOU'), promo(1000, url=PICHAU, store='Pichau')])
    first = next(r for r in client.get('/promotions').json()['items'] if r['price'] == 747)
    assert client.get('/components/gpu/offers').json()['best_offer']['price'] == 747
    reply = client.post(f"/promotions/{first['id']}/validation", json={'status': 'invalid'})
    assert reply.status_code == 200 and reply.json()['status'] == 'invalid' and reply.json()['state'] == 'invalid'
    offers = client.get('/components/gpu/offers').json()
    assert offers['best_offer']['price'] == 1000 and [o['price'] for o in offers['offers']] == [1000]
    assert [h['price'] for h in offers['history']] == [747] and offers['history'][0]['status'] == 'invalid'
    assert db.telegram_promotions.count_documents({}) == 2                       # nothing deleted
    stored = db.telegram_promotions.find_one({'offer.price': 747})
    assert stored['offer']['manual_validation_status'] == 'invalid' and stored['offer']['manual_validated_at']


def test_manual_working_confirms_and_unknown_clears_it(api):
    client, db = api
    db.telegram_promotions.insert_one(promo(2000, url=KABUM))
    offer_id = client.get('/promotions').json()['items'][0]['id']
    client.post(f'/promotions/{offer_id}/validation', json={'status': 'valid'})
    assert client.get('/promotions').json()['items'][0]['status'] == 'confirmed'
    assert client.get('/components/gpu').json()['prices'][0]['status'] == 'confirmed'
    client.post(f'/promotions/{offer_id}/validation', json={'status': 'unknown'})
    assert client.get('/promotions').json()['items'][0]['status'] == 'announced'


def test_observed_store_price_that_differs_invalidates_the_announced_price(api):
    client, db = api
    db.telegram_promotions.insert_one(promo(2789, url=KABUM, coupon='ZAFADINHO10'))
    offer_id = client.get('/promotions').json()['items'][0]['id']
    reply = client.post(f'/promotions/{offer_id}/validation', json={'status': 'valid', 'observed_price': 3059.99})
    assert reply.json()['status'] == 'invalid'
    assert client.get('/components/gpu/offers').json()['best_offer'] is None


def test_validation_marks_every_merged_duplicate_and_the_history_observation(api):
    client, db = api
    db.telegram_promotions.insert_many([promo(2000, url=KABUM), promo(2000, url=KABUM + '?a=1')])
    for doc in db.telegram_promotions.find():
        db.telegram_promotions.update_one({'_id': doc['_id']}, {'$set': {'telegram': {'chat_id': -1001, 'message_id': int(str(doc['_id'])[-3:], 16)}}})
        db.product_price_history.insert_one({'telegram': {'chat_id': -1001, 'message_id': int(str(doc['_id'])[-3:], 16)}, 'verified': True, 'component_id': 'gpu', 'price': 2000})
    offer_id = client.get('/promotions').json()['items'][0]['id']
    assert client.post(f'/promotions/{offer_id}/validation', json={'status': 'invalid'}).json()['updated_documents'] == 2
    assert db.telegram_promotions.count_documents({'offer.manual_validation_status': 'invalid'}) == 2
    assert db.product_price_history.count_documents({'verified': False, 'invalidated_by': 'manual_validation'}) == 2


def test_validation_needs_login_and_a_known_promotion(api):
    client, db = api
    assert client.post('/promotions/000000000000000000000000/validation', json={'status': 'valid'}).status_code == 404
    assert client.post('/promotions/not-an-id/validation', json={'status': 'bad'}).status_code == 422
    main.app.dependency_overrides.pop(get_current_user)
    assert client.post('/promotions/000000000000000000000000/validation', json={'status': 'valid'}).status_code == 401


# --- the three real cases -----------------------------------------------------------------------------------

def cpu_database():
    db = mongomock.MongoClient(tz_aware=True).db
    db.components.insert_many([
        {'id': 'ryzen-7-7800x3d', 'name': 'AMD Ryzen 7 7800X3D', 'category': 'cpu', 'brand': 'AMD', 'technical_specs': {}, 'compatibility': {}, 'prices': []},
        {'id': 'ryzen-7-5700', 'name': 'AMD Ryzen 7 5700', 'category': 'cpu', 'brand': 'AMD', 'technical_specs': {}, 'compatibility': {}, 'prices': []},
        {'id': 'rtx-5060-ti-8gb', 'name': 'NVIDIA GeForce RTX 5060 Ti 8GB', 'category': 'gpu', 'brand': 'NVIDIA', 'technical_specs': {'memory': '8GB'}, 'compatibility': {}, 'prices': []}])
    return db


def real(text, price, **offer):
    row = promo(price, **offer)
    row['raw_text'] = text
    row['product'] = {}
    return row


def test_real_case_7800x3d_with_coupon_is_a_recent_conditional_offer_and_a_general_one_stays_separate():
    db = cpu_database()
    db.telegram_promotions.insert_many([
        real('AMD Ryzen 7 7800X3D por R$ 1.683,49 com cupom AURAGAMER primeira compra', 1683.49, coupon='AURAGAMER', url=KABUM),
        real('AMD Ryzen 7 7800X3D R$ 1.839', 1839, store='Pichau', url='https://www.pichau.com.br/processador-amd-ryzen-7-7800x3d-am5')])
    result = commerce.build_snapshot(db, NOW)
    best_conditional, best_general = result['best_conditional']['ryzen-7-7800x3d'], result['best_general']['ryzen-7-7800x3d']
    assert best_conditional['price'] == 1683.49 and best_conditional['coupon_code'] == 'AURAGAMER' and best_conditional['status'] == 'conditional'
    assert 'Somente primeira compra' in best_conditional['condition_labels'] and best_conditional['store'] == 'Kabum'
    assert best_general['price'] == 1839


def test_real_case_5700_marked_invalid_leaves_the_best_offer(api):
    client, db = api
    cpu = cpu_database()
    db.components.delete_many({})
    db.components.insert_many(list(cpu.components.find({}, {'_id': 0})))
    db.telegram_promotions.insert_many([real('AMD Ryzen 7 5700 R$ 747 cupom FARMOU', 747, coupon='FARMOU', url=KABUM),
                                        real('AMD Ryzen 7 5700 R$ 899', 899, store='Pichau', url='https://www.pichau.com.br/processador-amd-ryzen-7-5700-am4')])
    assert client.get('/components/ryzen-7-5700/offers').json()['best_offer']['price'] == 747
    bad = next(r for r in client.get('/promotions').json()['items'] if r['price'] == 747)
    client.post(f"/promotions/{bad['id']}/validation", json={'status': 'invalid'})
    body = client.get('/components/ryzen-7-5700/offers').json()
    assert body['best_offer']['price'] == 899 and body['best_conditional_offer'] is None


def test_real_case_5060_ti_price_changed_is_never_shown_as_confirmed():
    db = cpu_database()
    db.telegram_promotions.insert_one(real('NVIDIA GeForce RTX 5060 Ti 8GB R$ 2.789 cupom ZAFADINHO10', 2789, coupon='ZAFADINHO10', url=KABUM,
                                           verified_price=3059.99, verification_source='manual', verified_at=(NOW + timedelta(seconds=5)).isoformat()))
    result = commerce.build_snapshot(db, NOW + timedelta(minutes=1))
    row = only(result)
    assert row['status'] == 'invalid' and row['status_reason'] == 'price_changed' and row['state'] == 'invalid'
    assert not result['offers'] and row['verification']['verified_price'] == 3059.99


def test_public_component_helper_ignores_seed_without_a_database():
    document = {'id': 'x', 'name': 'X', 'category': 'gpu', 'prices': [{'source': 'seed', 'price': 1, 'store': 'Seed'}],
                'price_history': [{'source': 'seed', 'date': '2026-01-01'}]}
    public = services._public_component(document)
    assert public['prices'] == [] and public['price_history'] == []


def test_equal_price_prefers_a_recent_or_confirmed_offer_over_a_stale_one():
    result, _ = snapshot(promo(1683, days=1.5, url=KABUM, coupon='OLD'), promo(1683, url=KABUM + '?x=2', coupon='NEW'))
    assert result['best']['gpu']['coupon'] == 'NEW'


def test_api_exposes_commercial_status_conditions_and_manual_validation_compatibly():
    row = only(snapshot(promo(1683.49, url=KABUM, coupon='AURAGAMER'))[0])
    assert row['commercial_status'] == row['status'] == 'conditional' and row['freshness'] == 'very_recent'
    assert row['manual_validation'] == {'status': None, 'validated_at': None}
    assert row['conditions']['requires_coupon'] is True and row['conditions']['payment_methods'] == []
    assert row['conditions']['first_purchase_only'] is None and 'raw_text' not in str(row)


def test_coupon_without_known_conditions_is_only_a_coupon_and_not_first_purchase():
    row = only(snapshot(text_promo('cupom ABC123', url=KABUM, coupon='ABC123'))[0])
    assert row['condition_labels'] == ['Exige cupom'] and row['conditions']['first_purchase_only'] is None


def test_first_purchase_offer_is_never_the_best_general_offer():
    result, _ = snapshot(text_promo('R$ 1.699 cupom XYZ somente primeira compra', 1699, url=KABUM, coupon='XYZ'),
                         promo(1839, url=PICHAU, store='Pichau'))
    assert result['best_general']['gpu']['price'] == 1839
    assert result['best_conditional']['gpu']['price'] == 1699 and result['best_conditional']['gpu']['conditions']['first_purchase_only']


def test_legacy_validation_spellings_are_still_accepted(api):
    client, db = api
    db.telegram_promotions.insert_one(promo(2000, url=KABUM))
    offer_id = client.get('/promotions').json()['items'][0]['id']
    assert client.post(f'/promotions/{offer_id}/validation', json={'status': 'working'}).json()['manual_validation_status'] == 'valid'
    assert db.telegram_promotions.find_one()['offer']['manual_validation_status'] == 'valid'
    assert client.get('/promotions').json()['items'][0]['manual_validation']['status'] == 'valid'
