import pytest
from fastapi.testclient import TestClient
import commerce
import main
from database import get_components_collection
from test_commerce import database, promo, NOW

PRODUCT = 'https://www.kabum.com.br/produto/123/placa'
SEARCH = 'https://www.kabum.com.br/busca/rtx-5060-ti'


def snap(*promos, **component):
    db = database()
    if component:
        db.components.update_one({'id': 'gpu'}, {'$set': component})
    db.telegram_promotions.insert_many(promos)
    return commerce.build_snapshot(db, NOW), db


def test_original_url_is_preserved_and_resolved_product_url_is_used():
    result, _ = snap(promo(2000, url='https://pruuu.me/a', store=None, resolved_url=PRODUCT))
    row = result['promotions'][0]
    assert row['original_url'] == 'https://pruuu.me/a' and row['resolved_url'] == PRODUCT
    assert row['url'] == PRODUCT and row['url_kind'] == 'product' and row['store'] == 'Kabum'


def test_failed_resolution_keeps_original_and_does_not_break_the_promotion():
    result, _ = snap(promo(2000, url='https://pruuu.me/a', store=None, link_status='error', resolved_url=None))
    row = result['promotions'][0]
    assert row['url'] == row['original_url'] == 'https://pruuu.me/a' and row['url_kind'] == 'unknown' and row['store'] is None
    assert row['state'] == 'active'


def test_original_product_deep_link_is_not_replaced_by_worse_resolution():
    result, _ = snap(promo(2000, url=PRODUCT, resolved_url='https://www.kabum.com.br/'))
    assert result['promotions'][0]['url'] == PRODUCT


def test_search_and_homepage_links_are_classified_not_treated_as_product():
    result, _ = snap(promo(2000, url=SEARCH), promo(2100, url='https://www.pichau.com.br/', store='Pichau'))
    kinds = {r['price']: r['url_kind'] for r in result['promotions']}
    assert kinds == {2000: 'search', 2100: 'homepage'}


def test_best_offer_prefers_direct_product_unless_search_is_much_cheaper():
    close, _ = snap(promo(2700, url=SEARCH), promo(2750, url=PRODUCT, store='Pichau'))
    assert close['best']['gpu']['url'] == PRODUCT and close['best']['gpu']['price'] == 2750
    assert close['offers']['gpu'][0]['price'] == 2700            # table stays ordered by lowest price
    far, _ = snap(promo(2300, url=SEARCH), promo(2750, url=PRODUCT, store='Pichau'))
    assert far['best']['gpu']['price'] == 2300
    only_search, _ = snap(promo(2300, url=SEARCH))
    assert only_search['best']['gpu']['url_kind'] == 'search'


def test_home_order_is_active_first_then_useful_url_then_price():
    result, _ = snap(promo(1500, url=SEARCH), promo(2900, url=PRODUCT, store='Pichau'), promo(2800, 5, url=PRODUCT, store='Amazon'))
    assert [(r['price'], r['state']) for r in result['promotions']][:2] == [(2900, 'active'), (1500, 'active')]
    assert result['promotions'][-1]['state'] != 'active'


def test_equivalent_promotions_are_projected_once_but_source_documents_are_kept():
    docs = [promo(2000, url=PRODUCT, coupon='ZAFA'), promo(2000, url=PRODUCT + '?aff=2', coupon='zafa'), promo(2000, url=PRODUCT + '?aff=3', coupon='ZAFA')]
    result, db = snap(*docs)
    assert len(result['promotions']) == 1 and result['promotions'][0]['also_seen'] == 2
    assert len(result['offers']['gpu']) == 1 and result['counts']['raw_published'] == 3
    assert db.telegram_promotions.count_documents({}) == 3
    different, _ = snap(promo(2000, url=PRODUCT), promo(2100, url=PRODUCT), promo(2000, url='https://www.pichau.com.br/placa-de-video-asus-dual-geforce-rtx-5060-ti', store='Pichau'))
    assert len(different['promotions']) == 3 and different['promotions'][0]['offers_count'] == 3


def test_expired_promotion_is_history_only_and_never_best():
    result, _ = snap(promo(1000, 10, url=PRODUCT), promo(2000, url='https://www.pichau.com.br/placa-de-video-asus-dual-geforce-rtx-5060-ti', store='Pichau'))
    assert result['best']['gpu']['price'] == 2000 and len(result['offers']['gpu']) == 1
    assert result['history']['gpu'][0]['price'] == 1000 and result['history']['gpu'][0]['state'] == 'expired'
    assert [r['offers_count'] for r in result['promotions'] if r['state'] != 'active'] == [0]


def test_price_and_coupon_come_from_the_promotion_not_the_seed_or_catalog():
    result, _ = snap(promo(2789, url=PRODUCT, coupon='ZAFADINHO10'), prices=[{'source': 'seed', 'price': 1500, 'store': 'Seed'}])
    row = result['promotions'][0]
    assert row['price'] == 2789 and row['coupon'] == 'ZAFADINHO10' and row['price_condition'] == 'coupon' and row['checkout_verified'] is False


@pytest.mark.parametrize('offer,component,expected', [
    ({'image': 'https://img.example/p.jpg'}, {'real_image': 'https://img.example/c.jpg'}, ('https://img.example/p.jpg', 'promotion')),
    ({}, {'real_image': 'https://img.example/c.jpg', 'images': ['https://img.example/i.jpg']}, ('https://img.example/c.jpg', 'component_real')),
    ({}, {'images': ['https://img.example/i.jpg']}, ('https://img.example/i.jpg', 'component')),
    ({'image': '/components/default-gpu.png'}, {'id': 'rtx-5060-8gb'}, ('/images/rtx-5060-8gb.png', 'local')),
    ({'image': 'javascript:x'}, {'id': 'other', 'image': 'https://placehold.co/1.png'}, (None, 'fallback')),
])
def test_image_resolution_order(offer, component, expected):
    assert commerce.resolve_image(offer, component) == expected


def test_new_promotion_appears_without_restart_after_cache_ttl():
    db = database()
    db.telegram_promotions.insert_one(promo(2000, url=PRODUCT))
    commerce._cache.clear()
    main.app.dependency_overrides[get_components_collection] = lambda: db.components
    try:
        api = TestClient(main.app)
        assert api.get('/promotions').json()['total'] == 1
        db.telegram_promotions.insert_one(promo(1900, url=PRODUCT + '?x=1', store='Pichau'))
        key = next(iter(commerce._cache))
        commerce._cache[key] = (-100, commerce._cache[key][1])
        body = api.get('/promotions').json()
        assert body['total'] == 2 and 'chat_id' not in str(body) and 'raw_text' not in str(body)
        offers = api.get('/components/gpu/offers').json()
        assert offers['best_offer']['price'] == 1900 and len(offers['offers']) == 2
    finally:
        main.app.dependency_overrides.clear()
        commerce._cache.clear()


def test_projection_does_not_write_to_mongo():
    result, db = snap(promo(2000, url=PRODUCT))
    stored = list(db.telegram_promotions.find({}, {'_id': 0}))
    assert 'resolved_url' not in stored[0]['offer'] and result['promotions']
