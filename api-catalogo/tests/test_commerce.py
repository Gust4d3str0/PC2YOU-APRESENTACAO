from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import mongomock
import pytest
import commerce
from ml_commerce import MercadoLivreClient, MercadoLivrePriceService, MLUnavailable
from fastapi.testclient import TestClient
import main
from database import get_components_collection

NOW = datetime.now(timezone.utc)


def database():
    db = mongomock.MongoClient(tz_aware=True).db
    db.components.insert_one({'id': 'gpu', 'name': 'RTX 5060 Ti 8GB', 'category': 'gpu', 'brand': 'NVIDIA',
                              'technical_specs': {'memory': '8GB'}, 'compatibility': {}, 'prices': []})
    return db


def promo(price=2000, days=0, **offer):
    return {'raw_text': 'INNO3D RTX 5060 Ti 8GB', 'product': {'component_type':'gpu'}, 'status':'parsed',
            'telegram':{'sent_at': NOW-timedelta(days=days)}, 'created_at': NOW-timedelta(days=days),
            'offer':{'price':price, 'url':'https://www.kabum.com.br/produto/123', 'store':'KaBuM', **offer}}


def test_real_telegram_read_projection_and_multiple_store_best_without_writes():
    db = database()
    db.telegram_promotions.insert_many([promo(2000), promo(2100,store='Pichau'), promo(1900,5)])
    before = deepcopy(list(db.telegram_promotions.find()))
    result = commerce.build_snapshot(db,NOW)
    assert len(result['offers']['gpu']) == 2 and result['offers']['gpu'][0]['price'] == 2000
    assert result['history']['gpu'][0]['state'] == 'expired'
    assert list(db.telegram_promotions.find()) == before
    assert not any(k in str(result['promotions']) for k in ('raw_text', 'chat_id', 'message_id'))
    assert result['promotions'][0]['valid_until'] is None
    assert result['promotions'][0]['fresh_until'] is not None


def test_expired_coupon_excluded_and_wrong_vram_never_linked():
    db = database()
    db.telegram_promotions.insert_one(promo(coupon='OLD',coupon_valid_until=(NOW-timedelta(seconds=1)).isoformat()))
    bad = promo();bad['raw_text']='INNO3D RTX 5060 Ti 16GB';db.telegram_promotions.insert_one(bad)
    result=commerce.build_snapshot(db,NOW)
    assert not result['offers'] and len(result['promotions'])==1
    assert result['promotions'][0]['state']=='expired'


def test_demo_seed_and_low_match_do_not_become_public_promotions():
    db=database();p=promo();p['is_demo']=True;db.telegram_promotions.insert_one(p)
    assert not commerce.build_snapshot(db,NOW)['promotions']


@pytest.fixture
def commerce_api():
    db = database()
    db.components.update_one({'id':'gpu'}, {'$set':{'prices':[{'source':'seed','price':1,'store':'Seed'}]}})
    db.telegram_promotions.insert_many([promo(2200), promo(1900,store='Pichau'), promo(1800,5)])
    commerce._cache.clear()
    main.app.dependency_overrides[get_components_collection] = lambda: db.components
    try:
        yield TestClient(main.app), db
    finally:
        main.app.dependency_overrides.clear()
        commerce._cache.clear()


def test_promotions_api_filters_history_paginates_and_hides_internal_fields(commerce_api):
    api, db = commerce_api
    active = api.get('/promotions', params={'status':'active','source':'telegram','category':'gpu','limit':1})
    assert active.status_code == 200 and active.json()['total'] == 2
    assert len(active.json()['items']) == 1
    assert api.get('/promotions?status=recent').json()['items'][0]['state'] == 'expired'
    assert api.get('/promotions?component_id=unrelated').json()['total'] == 0
    assert api.get('/promotions?status=invalid').status_code == 422
    assert api.get('/promotions?limit=101').status_code == 422
    assert not any(key in active.text for key in ('raw_text','chat_id','message_id'))
    assert db.telegram_promotions.count_documents({}) == 3


def test_comparison_and_catalog_api_use_lowest_current_offer_without_seed(commerce_api):
    api, _ = commerce_api
    comparison = api.get('/components/gpu/offers').json()
    assert comparison['best_offer']['price'] == 1900
    assert [o['price'] for o in comparison['offers']] == [1900,2200]
    assert comparison['history'][0]['price'] == 1800
    assert api.get('/components/absent/offers').status_code == 404
    item = api.get('/commerce/catalog?q=5060&category=gpu').json()['items'][0]
    assert item['prices'] == [] and item['offers_count'] == 2
    assert item['best_current_offer']['price'] == 1900
    assert api.get('/commerce/catalog?q=unrelated').json()['total'] == 0


def test_next_snapshot_publishes_newly_collected_promotion_without_build(commerce_api):
    api, db = commerce_api
    assert api.get('/promotions').json()['total'] == 2
    db.telegram_promotions.insert_one(promo(1700,store='Terabyte'))
    key = next(iter(commerce._cache))
    _, cached = commerce._cache[key]
    commerce._cache[key] = (-100, cached)
    assert api.get('/promotions').json()['total'] == 3
    assert api.get('/components/gpu/offers').json()['best_offer']['price'] == 1700


def response(status,data=None):
    r=Mock(status_code=status);r.json.return_value=data;return r


def client(monkeypatch,session):
    monkeypatch.setenv('MERCADO_LIVRE_ACCESS_TOKEN','old-test-only')
    monkeypatch.delenv('MERCADO_LIVRE_TOKEN_FILE',raising=False)
    return MercadoLivreClient(session)


def test_oauth_refresh_rotates_and_retries_once(monkeypatch):
    for k in ['REFRESH_TOKEN','CLIENT_ID','CLIENT_SECRET']:monkeypatch.setenv('MERCADO_LIVRE_'+k,'test-only')
    session=Mock();session.get.side_effect=[response(401),response(200,{'id':'safe'})]
    session.post.return_value=response(200,{'access_token':'new-test-only','refresh_token':'rotated-test-only','expires_in':3600})
    c=client(monkeypatch,session)
    assert c.get('/users/me')[0]==200
    assert session.get.call_count==2 and session.post.call_count==1
    assert session.get.call_args.kwargs['headers']['Authorization']=='Bearer new-test-only'
    assert c.tokens['refresh_token']=='rotated-test-only'


def test_401_does_not_loop_and_missing_client_does_not_expose_secrets(monkeypatch):
    monkeypatch.delenv('MERCADO_LIVRE_CLIENT_ID',raising=False)
    session=Mock();session.get.return_value=response(401)
    with pytest.raises(MLUnavailable,match='autorização'):client(monkeypatch,session).get('/users/me')
    assert session.get.call_count==1


@pytest.mark.parametrize('status',[403,429,503])
def test_api_failure_is_isolated_and_rate_limit_not_retried(monkeypatch,status):
    session=Mock();session.get.return_value=response(status)
    c=client(monkeypatch,session)
    assert c.get('/products/search')[0]==status
    assert session.get.call_count==1
    assert c.public_status()['status'] in {'unavailable','rate_limited'}


def test_product_search_cache_and_price_service_use_official_amount(monkeypatch):
    session=Mock();session.get.side_effect=[response(200,{'results':[]}),response(200,{'amount':1900,'regular_amount':2100,'currency_id':'BRL'})]
    c=client(monkeypatch,session)
    params={'site_id':'MLB','status':'active','q':'RTX 5060 Ti 8GB'}
    c.get('/products/search',params,ttl=3600);c.get('/products/search',params,ttl=3600)
    assert session.get.call_count==1
    price=MercadoLivrePriceService(c).current('MLB123')
    assert price['price']==1900 and price['regular_price']==2100
    assert session.get.call_args.args[0].endswith('/items/MLB123/sale_price')


def test_non_brl_and_missing_official_prices_fail_closed(monkeypatch):
    session=Mock();session.get.return_value=response(200,{'amount':123,'currency_id':'USD'})
    assert MercadoLivrePriceService(client(monkeypatch,session)).current('MLB123') is None
