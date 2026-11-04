"""Mercado Livre Product API enrichment + price capability. No real API: scripted fake HTTP session."""
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
import requests
from fastapi.testclient import TestClient

import commerce
import main
import ml_products as ml
from database import get_components_collection
from product_matching.offers import evaluate_offer
from test_commerce import NOW, promo

SECRET_ACCESS, SECRET_REFRESH, SECRET_CLIENT = 'APP_USR-secret-access-123', 'TG-secret-refresh-456', 'client-secret-789'


class Resp:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = text if text is not None else json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


class FakeSession:
    """Answers in order; an Exception instance is raised instead of returned. Records every call."""

    def __init__(self, *responses):
        self.responses, self.calls, self.posts = list(responses), [], []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        item = self.responses.pop(0) if self.responses else Resp(200, {})
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


ENV = {'MERCADO_LIVRE_ACCESS_TOKEN': SECRET_ACCESS, 'MERCADO_LIVRE_REFRESH_TOKEN': SECRET_REFRESH,
       'MERCADO_LIVRE_CLIENT_ID': 'cid', 'MERCADO_LIVRE_CLIENT_SECRET': SECRET_CLIENT}


def manager(tmp_path, env=None, session=None, clock=None):
    env = {**ENV, 'MERCADO_LIVRE_TOKEN_FILE': str(tmp_path / 'tokens.json'), **(env or {})}
    return ml.MercadoLivreTokenManager(session=session or FakeSession(), env=env, clock=clock or (lambda: 1000.0))


def client(tmp_path, *responses, **kw):
    session = FakeSession(*responses)
    tokens = manager(tmp_path, session=session)
    return ml.MercadoLivreApi(tokens, session=session, **kw), session, tokens


GPU_RAW = {'id': 'MLB78085963', 'catalog_product_id': 'MLB78085963', 'status': 'active', 'domain_id': 'MLB-GRAPHICS_CARDS',
           'name': 'Placa de vídeo Gigabyte GeForce RTX 5060 Ti GDDR7 Windforce Max OC de 8 GB', 'family_name': 'Placa de vídeo Nvidia Gigabyte GeForce RTX 5060 Ti',
           'last_updated': '2026-08-22T15:49:52Z', 'short_description': {'type': 'plaintext', 'content': 'Placa compacta para jogos.'},
           'pictures': [{'id': 'a', 'url': 'https://http2.mlstatic.com/D_NQ_NP_a.jpg'}, {'id': 'b', 'url': 'https://http2.mlstatic.com/D_NQ_NP_b.jpg'},
                        {'id': 'x', 'url': 'http://insecure.example/x.jpg'}, {'id': 'y', 'url': 'https://evil.example/y.jpg'}],
           'attributes': [{'id': i, 'name': i.title(), 'value_name': v} for i, v in [
               ('BRAND', 'Gigabyte'), ('MANUFACTURER', 'Nvidia'), ('MODEL', 'WINDFORCE MAX OC'), ('DETAILED_MODEL', 'GV-N506TWF2MAX OC-8GD'),
               ('MEMORY_SIZE', '8 GB'), ('GRAPHICS_MEMORY_TYPE', 'GDDR7'), ('MOTHERBOARD_INTERFACE', 'PCI-E 5.0'), ('MEMORY_BUS', '128 bit'),
               ('POWER_INPUT_TYPE', '8 pin'), ('CONNECTIVITY', '1 HDMI 2.1b, 3 × DisplayPort 2.1b'), ('TOTAL_GRAPHICS_POWER', '180 W'),
               ('POWER_REQUIREMENT', '650 W'), ('LENGTH', '208 mm'), ('WIDTH', '120 mm'), ('HEIGHT', '40 mm'), ('RELEASE_YEAR', '2025'),
               ('GRAPHICS_CARDS_SLOT_SIZE', '2'), ('EMPTY', '')]]}
CPU_RAW = {'id': 'MLB22826887', 'name': 'Processador AMD Ryzen 7 7800X3D', 'domain_id': 'MLB-COMPUTER_PROCESSORS', 'status': 'active',
           'pictures': [{'url': 'https://http2.mlstatic.com/cpu.jpg'}],
           'attributes': [{'id': 'BRAND', 'value_name': 'AMD'}, {'id': 'MODEL', 'value_name': 'Ryzen 7 7800X3D'}, {'id': 'SOCKET', 'value_name': 'AM5'},
                          {'id': 'CORES_NUMBER', 'value_name': '8'}, {'id': 'CORE_BOOST_FREQUENCY', 'value_name': '5 GHz'}]}
RAM_RAW = {'id': 'MLB11111111', 'name': 'Memória RAM Kingston Fury 16GB DDR5', 'domain_id': 'MLB-RAM_MEMORY_MODULES',
           'attributes': [{'id': 'BRAND', 'value_name': 'Kingston'}, {'id': 'MEMORY_SIZE', 'value_name': '16 GB'},
                          {'id': 'MEMORY_TYPE', 'value_name': 'DDR5'}, {'id': 'SPEED', 'value_name': '5600 MHz'}]}


def database(**component):
    db = mongomock.MongoClient(tz_aware=True).db
    db.components.insert_one({'id': 'rtx-5060-ti-8gb', 'name': 'GeForce RTX 5060 Ti 8GB', 'category': 'gpu', 'brand': 'NVIDIA', 'image': '/components/default-gpu.svg',
                              'description': 'd', 'technical_specs': {'memory': '8GB GDDR7'}, 'compatibility': {}, 'benchmark': {}, 'prices': [], **component})
    db.components.insert_one({'id': 'rtx-5060-ti-16gb', 'name': 'GeForce RTX 5060 Ti 16GB', 'category': 'gpu', 'brand': 'NVIDIA', 'image': '/components/default-gpu.svg',
                              'description': 'd', 'technical_specs': {}, 'compatibility': {}, 'benchmark': {}, 'prices': []})
    return db


# --- normalizer ---------------------------------------------------------------------------------------

def test_normalizer_maps_the_gpu_product_to_the_standard_shape():
    n = ml.MercadoLivreProductNormalizer.normalize(GPU_RAW)
    assert (n['product_id'], n['brand'], n['manufacturer'], n['model'], n['detailed_model'], n['source']) == (
        'MLB78085963', 'Gigabyte', 'Nvidia', 'WINDFORCE MAX OC', 'GV-N506TWF2MAX OC-8GD', 'mercado_livre_product_api')
    specs = n['specs']
    assert specs['memory_size'] == '8 GB' and specs['memory_type'] == 'GDDR7' and specs['motherboard_interface'] == 'PCI-E 5.0'
    assert specs['memory_bus'] == '128 bit' and specs['power_input'] == '8 pin' and specs['total_graphics_power'] == '180 W'
    assert specs['power_requirement'] == '650 W' and (specs['length'], specs['width'], specs['height']) == ('208 mm', '120 mm', '40 mm')
    assert 'HDMI' in specs['connectivity'] and 'EMPTY' not in n['attributes'] and n['short_description'] == 'Placa compacta para jogos.'


def test_normalizer_keeps_only_official_https_pictures():
    assert ml.MercadoLivreProductNormalizer.normalize(GPU_RAW)['images'] == ['https://http2.mlstatic.com/D_NQ_NP_a.jpg', 'https://http2.mlstatic.com/D_NQ_NP_b.jpg']


def test_normalizer_cpu_and_ram_use_their_own_attributes_and_absent_is_null():
    cpu = ml.MercadoLivreProductNormalizer.normalize(CPU_RAW)
    assert cpu['specs'] == {'socket': 'AM5', 'core_count': '8', 'boost_clock': '5 GHz'} and cpu['manufacturer'] is None and cpu['detailed_model'] is None
    ram = ml.MercadoLivreProductNormalizer.normalize(RAM_RAW)
    assert ram['specs'] == {'memory_size': '16 GB', 'memory_type': 'DDR5', 'memory_speed': '5600 MHz'} and ram['images'] == []


def test_normalizer_rejects_garbage():
    assert ml.MercadoLivreProductNormalizer.normalize(None) is None and ml.MercadoLivreProductNormalizer.normalize({'name': 'x'}) is None


# --- HTTP client: every status is a result, nothing raises --------------------------------------------

def test_product_ok_not_found_invalid_id(tmp_path):
    api, session, _ = client(tmp_path, Resp(200, GPU_RAW), Resp(404, {'message': 'x'}))
    assert api.get_product('MLB78085963').ok and session.calls[0][0].endswith('/products/MLB78085963')
    assert session.calls[0][2]['Authorization'] == 'Bearer ' + SECRET_ACCESS
    assert api.get_product('MLB1').kind == 'invalid' and api.get_product('../x').kind == 'invalid' and api.get_product('MLB99999999').kind == 'not_found'
    assert len(session.calls) == 2                       # invalid ids never reach the network


@pytest.mark.parametrize('response,kind,reason', [
    (Resp(403, {'message': 'Access to the requested resource is forbidden', 'error': 'access_denied'}), 'forbidden', 'policy_denied'),
    (Resp(403, text='PA_UNAUTHORIZED_RESULT_FROM_POLICIES'), 'forbidden', 'policy_denied'),
    (Resp(500, {}), 'server_error', None), (Resp(503, {}), 'server_error', None),
    (Resp(200, None), 'invalid', 'bad_json'), (Resp(418, {}), 'error', None),
    (requests.Timeout(), 'timeout', 'timeout'), (requests.ConnectionError(), 'error', 'network'),
])
def test_failures_become_results(tmp_path, response, kind, reason):
    api, _, _ = client(tmp_path, response)
    result = api.get_item('MLB7833387058')
    assert (result.kind, result.reason) == (kind, reason)


def test_403_never_triggers_a_token_refresh(tmp_path):
    api, session, _ = client(tmp_path, Resp(403, {'error': 'access_denied'}))
    api.get_item('MLB7833387058')
    assert session.posts == [] and len(session.calls) == 1


def test_401_refreshes_once_and_retries_once(tmp_path):
    fresh = {'access_token': 'NEW-ACCESS', 'refresh_token': 'NEW-REFRESH', 'expires_in': 21600}
    session = FakeSession(Resp(401, {}), Resp(200, fresh), Resp(200, GPU_RAW))
    tokens = manager(tmp_path, session=session)
    api = ml.MercadoLivreApi(tokens, session=session)
    assert api.get_product('MLB78085963').ok
    assert len(session.posts) == 1 and len(session.calls) == 2
    assert session.calls[1][2]['Authorization'] == 'Bearer NEW-ACCESS'


def test_401_twice_does_not_loop(tmp_path):
    fresh = {'access_token': 'NEW-ACCESS', 'refresh_token': 'NEW-REFRESH', 'expires_in': 21600}
    session = FakeSession(Resp(401, {}), Resp(200, fresh), Resp(401, {}))
    api = ml.MercadoLivreApi(manager(tmp_path, session=session), session=session)
    assert api.get_product('MLB78085963').kind == 'unauthorized'
    assert len(session.posts) == 1 and len(session.calls) == 2


def test_401_without_client_credentials_is_reported_not_retried(tmp_path):
    session = FakeSession(Resp(401, {}))
    tokens = manager(tmp_path, env={'MERCADO_LIVRE_CLIENT_ID': '', 'MERCADO_LIVRE_CLIENT_SECRET': ''}, session=session)
    result = ml.MercadoLivreApi(tokens, session=session).get_product('MLB78085963')
    assert result.kind == 'unauthorized' and session.posts == [] and tokens.last_error == 'refresh_unavailable'


def test_429_backs_off_without_hammering(tmp_path):
    now = [0.0]
    api, session, _ = client(tmp_path, Resp(429, {}, headers={'Retry-After': '10'}), Resp(200, GPU_RAW), clock=lambda: now[0])
    assert api.get_product('MLB78085963').kind == 'rate_limited'
    assert api.get_product('MLB78085963').kind == 'rate_limited' and len(session.calls) == 1      # still backing off
    now[0] = 11.0
    assert api.get_product('MLB78085963').ok and len(session.calls) == 2


def test_no_token_means_auth_unavailable_without_a_request(tmp_path):
    session = FakeSession()
    tokens = manager(tmp_path, env={'MERCADO_LIVRE_ACCESS_TOKEN': '', 'MERCADO_LIVRE_REFRESH_TOKEN': ''}, session=session)
    assert ml.MercadoLivreApi(tokens, session=session).get_product('MLB78085963').kind == 'auth_unavailable' and session.calls == []


# --- token manager --------------------------------------------------------------------------------------

def test_refresh_rotates_the_token_and_persists_it_with_no_secrets_in_state(tmp_path):
    session = FakeSession(Resp(200, {'access_token': 'NEW-A', 'refresh_token': 'NEW-R', 'expires_in': 100}))
    tokens = manager(tmp_path, session=session)
    assert tokens.refresh() and tokens.access_token() == 'NEW-A'
    assert session.posts[0][1]['refresh_token'] == SECRET_REFRESH                # the old one is used once...
    saved = json.loads((tmp_path / 'tokens.json').read_text())
    assert saved['refresh_token'] == 'NEW-R' and saved['access_token'] == 'NEW-A'
    reloaded = manager(tmp_path)                                                   # ...and a restart uses the rotated one
    assert reloaded.access_token() == 'NEW-A' and reloaded._refresh == 'NEW-R'
    rendered = json.dumps(tokens.state())
    assert not any(s in rendered for s in (SECRET_ACCESS, SECRET_REFRESH, SECRET_CLIENT, 'NEW-A', 'NEW-R'))


def test_a_changed_env_refresh_token_wins_over_an_older_token_file(tmp_path):
    manager(tmp_path, session=FakeSession(Resp(200, {'access_token': 'NEW-A', 'refresh_token': 'NEW-R', 'expires_in': 100}))).refresh()
    reauthorised = manager(tmp_path, env={'MERCADO_LIVRE_ACCESS_TOKEN': 'FRESH-A', 'MERCADO_LIVRE_REFRESH_TOKEN': 'FRESH-R'})
    assert reauthorised.access_token() == 'FRESH-A'


def test_refresh_is_refused_without_a_token_file_so_a_rotated_token_is_never_lost(tmp_path):
    tokens = ml.MercadoLivreTokenManager(session=FakeSession(), env=dict(ENV), clock=lambda: 0.0)
    assert not tokens.can_refresh and tokens.refresh() is False and tokens.last_error == 'refresh_unavailable'


def test_failed_refresh_has_a_cooldown_instead_of_endless_renewing(tmp_path):
    now = [100.0]
    session = FakeSession(Resp(400, {}), Resp(200, {'access_token': 'A', 'refresh_token': 'R'}))
    tokens = manager(tmp_path, session=session, clock=lambda: now[0])
    assert tokens.refresh() is False and tokens.refresh() is False and len(session.posts) == 1
    now[0] += 61
    assert tokens.refresh() is True and len(session.posts) == 2


def test_an_already_refreshed_token_is_not_refreshed_again_by_a_second_caller(tmp_path):
    session = FakeSession(Resp(200, {'access_token': 'NEW-A', 'refresh_token': 'NEW-R', 'expires_in': 100}))
    tokens = manager(tmp_path, session=session)
    assert tokens.refresh(stale_token=SECRET_ACCESS)
    assert tokens.refresh(stale_token=SECRET_ACCESS) is True and len(session.posts) == 1


# --- enrichment: cache, persistence, safety --------------------------------------------------------------

def service(tmp_path, db, *responses, now=None, ttl=24):
    api, session, _ = client(tmp_path, *responses)
    return ml.MercadoLivreProductEnrichment(db, api, ttl_hours=ttl, now=now), session


def test_enrichment_persists_separately_and_never_touches_commercial_or_identity_fields(tmp_path):
    db = database()
    db.telegram_promotions.insert_one(promo(2789, url='https://www.kabum.com.br/produto/1', coupon='ZAFADINHO10'))
    before_promos = list(db.telegram_promotions.find({}))
    before_component = {k: v for k, v in db.components.find_one({'id': 'rtx-5060-ti-8gb'}).items() if k != 'external_enrichment'}
    rows_before = [{k: r[k] for k in ('price', 'coupon', 'status', 'commercial_status', 'component_id')} for r in commerce.build_snapshot(db, NOW)['promotions']]
    svc, _ = service(tmp_path, db, Resp(200, GPU_RAW))
    result = svc.enrich('MLB78085963', db.components.find_one({'id': 'rtx-5060-ti-8gb'}), basis='manual_mapping')
    assert result['applied'] and result['match']['status'] == 'matched'
    component = db.components.find_one({'id': 'rtx-5060-ti-8gb'})
    stored = component['external_enrichment']['mercado_livre']
    assert stored['product_id'] == 'MLB78085963' and stored['brand'] == 'Gigabyte' and len(stored['images']) == 2 and stored['source'] == 'mercado_livre_product_api'
    assert stored['match_status'] == 'matched' and stored['external_conflict'] is False and stored['specs']['memory_size'] == '8 GB'
    assert {k: v for k, v in component.items() if k not in {'external_enrichment', '_id'}} == {k: v for k, v in before_component.items() if k != '_id'}
    assert list(db.telegram_promotions.find({})) == before_promos
    rows_after = [{k: r[k] for k in ('price', 'coupon', 'status', 'commercial_status', 'component_id')} for r in commerce.build_snapshot(db, NOW)['promotions']]
    assert rows_after == rows_before
    assert json.dumps(stored).count(SECRET_ACCESS) == 0


def test_product_is_fetched_once_within_the_cache_ttl_and_again_after(tmp_path):
    db, clock = database(), [datetime(2026, 11, 3, 12, tzinfo=timezone.utc)]
    svc, session = service(tmp_path, db, Resp(200, GPU_RAW), Resp(200, GPU_RAW), now=lambda: clock[0])
    component = db.components.find_one({'id': 'rtx-5060-ti-8gb'})
    svc.enrich('MLB78085963', component, basis='manual_mapping')
    svc.enrich('MLB78085963', component, basis='manual_mapping')
    assert len(session.calls) == 1
    clock[0] += timedelta(hours=25)
    svc.enrich('MLB78085963', component, basis='manual_mapping')
    assert len(session.calls) == 2


def test_cache_ttl_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv('PC2YOU_ML_PRODUCT_CACHE_TTL_HOURS', '6')
    assert ml.cache_ttl_hours() == 6.0
    monkeypatch.setenv('PC2YOU_ML_PRODUCT_CACHE_TTL_HOURS', 'bad')
    assert ml.cache_ttl_hours() == 24.0


def test_if_mercado_livre_fails_the_cached_copy_is_used_and_nothing_breaks(tmp_path):
    db, clock = database(), [datetime(2026, 11, 3, 12, tzinfo=timezone.utc)]
    svc, _ = service(tmp_path, db, Resp(200, GPU_RAW), Resp(500, {}), now=lambda: clock[0])
    component = db.components.find_one({'id': 'rtx-5060-ti-8gb'})
    svc.enrich('MLB78085963', component, basis='manual_mapping')
    clock[0] += timedelta(days=2)
    result = svc.enrich('MLB78085963', component, basis='manual_mapping')
    assert result['outcome'] == 'stale_cache' and result['applied']
    down, _ = service(tmp_path, database(), requests.Timeout())
    outcome = down.enrich('MLB99999999', database().components.find_one({'id': 'rtx-5060-ti-8gb'}), basis='x')
    assert outcome['outcome'] == 'timeout' and outcome['applied'] is False


def test_unknown_product_is_reported_not_raised(tmp_path):
    db = database()
    svc, _ = service(tmp_path, db, Resp(404, {}))
    assert svc.enrich('MLB99999999', db.components.find_one({'id': 'rtx-5060-ti-8gb'}), basis='x')['outcome'] == 'not_found'
    assert 'external_enrichment' not in db.components.find_one({'id': 'rtx-5060-ti-8gb'})


def test_the_pc2you_matcher_stays_the_authority(tmp_path):
    db = database()
    svc, _ = service(tmp_path, db, Resp(200, GPU_RAW))
    wrong = svc.enrich('MLB78085963', db.components.find_one({'id': 'rtx-5060-ti-16gb'}), basis='manual_mapping')   # 8 GB product, 16 GB component
    assert wrong['match']['status'] == 'conflict' and not wrong['applied']
    assert 'external_enrichment' not in db.components.find_one({'id': 'rtx-5060-ti-16gb'})


def test_a_notebook_that_says_ryzen_never_enriches_a_processor(tmp_path):
    db = database()
    db.components.insert_one({'id': 'ryzen-7-7800x3d', 'name': 'AMD Ryzen 7 7800X3D', 'category': 'cpu', 'brand': 'AMD', 'technical_specs': {}, 'compatibility': {}, 'prices': []})
    notebook = {**CPU_RAW, 'id': 'MLB46577938', 'name': 'Notebook preto - AMD Ryzen 7 7800X3D', 'domain_id': 'MLB-NOTEBOOKS'}
    svc, _ = service(tmp_path, db, Resp(200, notebook))
    result = svc.enrich('MLB46577938', db.components.find_one({'id': 'ryzen-7-7800x3d'}), basis='manual_mapping')
    assert result['match']['status'] == 'conflict' and 'domain_mismatch' in result['match']['conflicts'] and not result['applied']


def test_unknown_domain_is_ambiguous_not_matched(tmp_path):
    db = database()
    svc, _ = service(tmp_path, db, Resp(200, {**GPU_RAW, 'domain_id': None}))
    assert svc.enrich('MLB78085963', db.components.find_one({'id': 'rtx-5060-ti-8gb'}), basis='x')['match']['status'] == 'ambiguous'


def test_an_earlier_enrichment_is_not_silently_replaced(tmp_path):
    db = database()
    other = {**GPU_RAW, 'id': 'MLB11112222'}
    svc, _ = service(tmp_path, db, Resp(200, GPU_RAW), Resp(200, other), Resp(200, other))
    component = lambda: db.components.find_one({'id': 'rtx-5060-ti-8gb'})   # noqa: E731
    svc.enrich('MLB78085963', component(), basis='manual_mapping')
    second = svc.enrich('MLB11112222', component(), basis='manual_mapping')
    assert not second['applied'] and component()['external_enrichment']['mercado_livre']['product_id'] == 'MLB78085963'
    assert svc.enrich('MLB11112222', component(), basis='manual_mapping', force=True)['applied']


def test_enrichment_counts_are_recorded_without_secrets(tmp_path):
    db = database()
    svc, _ = service(tmp_path, db, Resp(200, GPU_RAW))
    svc.enrich('MLB78085963', db.components.find_one({'id': 'rtx-5060-ti-8gb'}), basis='manual_mapping')
    status = ml.integration_status(manager(tmp_path), db)
    assert status['metrics']['ml_products_enriched'] == 1 and status['metrics']['ml_images_added'] == 1 and status['metrics']['ml_specs_added'] == 1
    assert status['product_api'] == 'available' and status['last_product_success']
    assert not any(s in json.dumps(status) for s in (SECRET_ACCESS, SECRET_REFRESH, SECRET_CLIENT))


# --- images ---------------------------------------------------------------------------------------------

OFFICIAL = 'https://http2.mlstatic.com/D_NQ_NP_a.jpg'


def with_ml(**extra):
    return {'id': 'gpu-without-local-photo', 'image': '/components/default-gpu.svg', 'external_enrichment': {'mercado_livre': {
        'images': [OFFICIAL], 'match_status': 'matched', 'external_conflict': False, **extra}}}


def test_image_priority_promotion_then_official_then_internal():
    assert commerce.resolve_image({'image': 'https://img.example/promo.jpg'}, with_ml()) == ('https://img.example/promo.jpg', 'promotion')
    assert commerce.resolve_image({}, with_ml()) == (OFFICIAL, 'mercado_livre_product_api')
    assert commerce.resolve_image({}, {**with_ml(), 'real_image': 'https://img.example/real.jpg'}) == (OFFICIAL, 'mercado_livre_product_api')
    assert commerce.resolve_image({}, {'id': 'x', 'real_image': 'https://img.example/real.jpg'}) == ('https://img.example/real.jpg', 'component_real')


def test_conflicting_or_unmatched_enrichment_never_supplies_the_image():
    for extra in ({'match_status': 'conflict'}, {'match_status': 'ambiguous'}, {'external_conflict': True}, {'images': ['http://insecure.example/x.jpg']}):
        assert commerce.resolve_image({}, with_ml(**extra))[1] == 'fallback'


def test_snapshot_rows_use_the_official_image_and_expose_the_ml_ids():
    db = database(external_enrichment={'mercado_livre': {'images': [OFFICIAL], 'match_status': 'matched', 'external_conflict': False}})
    pdp = 'https://www.mercadolivre.com.br/placa/p/MLB78085963?wid=MLB7833387058'
    db.telegram_promotions.insert_one(promo(2789, url='https://meli.la/abc', resolved_url=pdp, store='Mercado Livre'))
    row = commerce.build_snapshot(db, NOW)['promotions'][0]
    assert (row['image'], row['image_source']) == (OFFICIAL, 'mercado_livre_product_api')
    assert (row['ml_product_id'], row['ml_item_id']) == ('MLB78085963', 'MLB7833387058')


# --- capability and (future) price validation ----------------------------------------------------------------

def test_item_403_is_a_capability_not_a_verdict_on_the_offer(tmp_path):
    db = database()
    db.telegram_promotions.insert_one(promo(2789, url='https://www.kabum.com.br/produto/1'))
    before = list(db.telegram_promotions.find({}))
    api, _, _ = client(tmp_path, Resp(403, {'message': 'Access to the requested resource is forbidden', 'error': 'access_denied'}))
    report = ml.MercadoLivrePriceCapability(api, db).probe('MLB7833387058')
    assert report['status'] == 'forbidden' and report['reason'] == 'policy_denied'
    state = db['ml_integration_state'].find_one({'_id': 'state'})
    assert state['ml_price_validation_capability'] == 'forbidden' and state['item_api'] == 'restricted' and state['metrics']['ml_item_api_forbidden'] == 1
    assert list(db.telegram_promotions.find({})) == before
    row = commerce.build_snapshot(db, NOW)['promotions'][0]
    assert row['status'] != 'invalid' and row['eligible']


@pytest.mark.parametrize('response,expected', [(Resp(200, {'id': 'MLB7833387058'}), 'available'), (Resp(404, {}), 'not_found'),
                                               (Resp(500, {}), 'error'), (requests.Timeout(), 'error')])
def test_capability_probe_outcomes(tmp_path, response, expected):
    api, _, _ = client(tmp_path, response)
    assert ml.MercadoLivrePriceCapability(api).probe('MLB7833387058')['status'] == expected


def test_capability_probe_rejects_a_product_id_used_as_item(tmp_path):
    api, session, _ = client(tmp_path)
    assert ml.MercadoLivrePriceCapability(api).probe('not-an-item')['status'] == 'error' and session.calls == []


def validator(tmp_path, *responses):
    api, session, _ = client(tmp_path, *responses)
    return ml.MercadoLivrePriceValidator(api, now=lambda: NOW), session


def item(**extra):
    return Resp(200, {'id': 'MLB7833387058', 'status': 'active', 'price': 439.99, **extra})


def sale(amount, regular=None, end=None):
    return Resp(200, {'amount': amount, 'regular_amount': regular, 'currency_id': 'BRL', 'conditions': {'end_time': end}})


@pytest.mark.parametrize('official,expected', [(439.99, 'confirmed'), (440.0, 'confirmed'), (438.0, 'confirmed'), (445.0, 'price_changed'), (3059.99, 'price_changed')])
def test_price_validation_standard_price_with_tolerance(tmp_path, official, expected):
    v, _ = validator(tmp_path, item(), sale(official))
    result = v.validate({'price': 439.0}, 'MLB7833387058')
    assert result['verification_status'] == expected


def test_relative_tolerance_applies_to_expensive_items(tmp_path):
    v, _ = validator(tmp_path, item(), sale(2800.0))
    assert v.validate({'price': 2789.0}, 'MLB7833387058')['verification_status'] == 'confirmed'      # 0.4%
    v, _ = validator(tmp_path, item(), sale(2810.0))
    assert v.validate({'price': 2789.0}, 'MLB7833387058')['verification_status'] == 'price_changed'  # 0.75%


def test_coupon_price_that_differs_is_not_verifiable_and_conditions_survive(tmp_path):
    v, _ = validator(tmp_path, item(), sale(3059.99))
    offer = {'price': 2789.0, 'coupon': 'XYZ', 'conditions': {'requires_coupon': True, 'first_purchase_only': True, 'app_only': True}}
    result = v.validate(offer, 'MLB7833387058')
    assert result['verification_status'] == 'coupon_not_verifiable' and result['official_price'] == 3059.99
    assert 'verified_price' not in result['fields'] and result['fields']['official_base_price'] == 3059.99
    assert offer['conditions']['first_purchase_only'] is True and offer['conditions']['app_only'] is True
    status = evaluate_offer({**offer, 'captured_at': (NOW - timedelta(hours=1)).isoformat(), **result['fields']}, NOW)
    assert status['status'] != 'invalid' and status['eligible']


def test_expired_when_the_promotion_ended_or_the_listing_is_gone(tmp_path):
    ended = (NOW - timedelta(hours=1)).isoformat()
    assert validator(tmp_path, item(), sale(439.0, end=ended))[0].validate({'price': 439.0}, 'MLB7833387058')['verification_status'] == 'expired'
    assert validator(tmp_path, item(status='closed'))[0].validate({'price': 439.0}, 'MLB7833387058')['verification_status'] == 'expired'
    assert validator(tmp_path, Resp(404, {}))[0].validate({'price': 439.0}, 'MLB7833387058')['verification_status'] == 'expired'


@pytest.mark.parametrize('response', [Resp(403, {'error': 'access_denied'}), requests.Timeout(), Resp(429, {}), Resp(500, {})])
def test_unavailable_never_invalidates_or_writes(tmp_path, response):
    v, _ = validator(tmp_path, response)
    result = v.validate({'price': 439.0}, 'MLB7833387058')
    assert result['verification_status'] == 'unavailable' and result['fields'] == {}


def test_without_a_reliable_item_id_the_offer_stays_unverified(tmp_path):
    v, session = validator(tmp_path)
    assert v.validate({'price': 439.0}, None)['verification_status'] == 'unverified' and session.calls == []


def test_confirmed_and_price_changed_feed_the_existing_status_model(tmp_path):
    base = {'price': 2789.0, 'captured_at': (NOW - timedelta(hours=1)).isoformat()}
    confirmed = validator(tmp_path, item(), sale(2789.0))[0].validate(base, 'MLB7833387058')['fields']
    assert confirmed['verification_source'] == 'mercado_livre_api'
    assert evaluate_offer({**base, **confirmed}, NOW)['status'] == 'confirmed'
    changed = validator(tmp_path, item(), sale(3059.99))[0].validate(base, 'MLB7833387058')['fields']
    assert evaluate_offer({**base, **changed}, NOW)['status'] == 'invalid'


def test_official_price_history_is_recorded_once_per_day_and_price():
    db = database()
    assert ml.record_official_price(db, 'rtx-5060-ti-8gb', 'MLB7833387058', 2789.0, NOW) is True
    assert ml.record_official_price(db, 'rtx-5060-ti-8gb', 'MLB7833387058', 2789.0, NOW + timedelta(minutes=5)) is False
    assert ml.record_official_price(db, 'rtx-5060-ti-8gb', 'MLB7833387058', 2799.0, NOW) is True
    assert ml.record_official_price(db, 'rtx-5060-ti-8gb', 'MLB7833387058', None, NOW) is False
    rows = list(db.product_price_history.find({'source': 'mercado_livre_api'}))
    assert len(rows) == 2 and rows[0]['item_id'] == 'MLB7833387058' and rows[0]['component_id'] == 'rtx-5060-ti-8gb'


# --- API surface: status endpoint, tokens and an offline Mercado Livre ----------------------------------

@pytest.fixture
def api_client(monkeypatch):
    db = database()
    commerce._cache.clear()
    monkeypatch.setattr(ml, 'tokens', ml.MercadoLivreTokenManager(session=FakeSession(), env=dict(ENV), clock=lambda: 0.0))
    main.app.dependency_overrides[get_components_collection] = lambda: db.components
    try:
        yield TestClient(main.app), db
    finally:
        main.app.dependency_overrides.clear()
        commerce._cache.clear()


def test_status_endpoint_is_safe_and_reports_the_restricted_item_api(api_client):
    client_, db = api_client
    ml.record_state(db, {'ml_item_api_forbidden': 2}, {'item_api': 'restricted', 'price_validation': 'unavailable', 'product_api': 'available',
                                                        'last_product_success': '2026-11-03T12:00:00+00:00', 'last_error': None})
    body = client_.get('/integrations/mercado-livre/status')
    assert body.status_code == 200
    data = body.json()
    assert data['configured'] is True and data['authorized'] is True and data['product_api'] == 'available'
    assert data['item_api'] == 'restricted' and data['price_validation'] == 'unavailable' and data['metrics']['ml_item_api_forbidden'] == 2
    assert not any(s in body.text for s in (SECRET_ACCESS, SECRET_REFRESH, SECRET_CLIENT))
    assert 'PolicyAgent' not in body.text and '403' not in body.text


def test_site_endpoints_work_when_mercado_livre_is_down(api_client, monkeypatch):
    client_, db = api_client
    db.telegram_promotions.insert_one(promo(2789, url='https://www.kabum.com.br/produto/1'))

    def boom(*a, **k):
        raise AssertionError('Mercado Livre must not be called while serving the site')

    monkeypatch.setattr(ml.MercadoLivreApi, 'get', boom)
    for path in ('/promotions', '/components/rtx-5060-ti-8gb/offers', '/commerce/catalog', '/components/rtx-5060-ti-8gb', '/components'):
        assert client_.get(path).status_code == 200, path


def test_the_component_endpoint_exposes_enrichment_without_any_token(api_client):
    client_, db = api_client
    svc = ml.MercadoLivreProductEnrichment(db, ml.MercadoLivreApi(manager(db and __import__('pathlib').Path('.')), session=FakeSession(Resp(200, GPU_RAW))))
    svc.enrich('MLB78085963', db.components.find_one({'id': 'rtx-5060-ti-8gb'}), basis='manual_mapping')
    body = client_.get('/components/rtx-5060-ti-8gb')
    enrichment = body.json()['external_enrichment']['mercado_livre']
    assert enrichment['images'][0] == 'https://http2.mlstatic.com/D_NQ_NP_a.jpg' and enrichment['specs']['power_requirement'] == '650 W'
    assert not any(s in body.text for s in (SECRET_ACCESS, SECRET_REFRESH, SECRET_CLIENT))
    catalog = client_.get('/commerce/catalog').json()['items']
    assert next(i for i in catalog if i['id'] == 'rtx-5060-ti-8gb')['external_enrichment']['mercado_livre']['product_id'] == 'MLB78085963'


# --- opt-in live check (never part of the normal run; needs real credentials in the environment) --------------

@pytest.mark.skipif(not (__import__('os').environ.get('PC2YOU_ML_LIVE_TESTS') == '1' and __import__('os').environ.get('MERCADO_LIVRE_ACCESS_TOKEN')),
                    reason='live Mercado Livre test: set PC2YOU_ML_LIVE_TESTS=1 and MERCADO_LIVRE_ACCESS_TOKEN')
def test_live_product_api_returns_the_expected_gigabyte_rtx_5060_ti():
    live = ml.MercadoLivreApi(ml.MercadoLivreTokenManager())
    result = live.get_product('MLB78085963')
    assert result.ok
    n = ml.MercadoLivreProductNormalizer.normalize(result.data)
    assert n['brand'] == 'Gigabyte' and '5060 Ti' in n['name'] and n['images']
    s = n['specs']
    assert s['memory_size'] == '8 GB' and s['memory_type'] == 'GDDR7' and '5.0' in s['motherboard_interface'] and s['memory_bus'] == '128 bit'
    assert '8' in s['power_input'] and 'HDMI' in s['connectivity'] and 'DisplayPort' in s['connectivity']
    assert s['total_graphics_power'] == '180 W' and s['power_requirement'] == '650 W' and s['length'] and s['width'] and s['height']
