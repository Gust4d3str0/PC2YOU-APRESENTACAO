from copy import deepcopy
from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from services.product_matching import match_product, compare_product, normalize_brand, normalize_store
from services.product_matching.normalization import capacity_values, capacity_label, normalize_text
from services.product_matching.promotions import enrich_promotion
from services.product_matching.quality import (best_known_price, catalog_offers, equivalence_key,
                                             history_observation, money, offer_url, price_quality)
from services.product_matching.reporting import quality_report
from services.telegram_collector.repository import PromotionRepository
from scripts.reprocess_product_matches import reprocess


NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def piece(name, category, brand='', specs=None):
    return {'id': name.lower().replace(' ', '-'), 'name': name, 'category': category,
            'brand': brand, 'technical_specs': specs or {}, 'compatibility': {}}


GPUS = [piece(name, 'gpu') for name in ('RTX 5070', 'RTX 5070 Ti', 'RTX 5070 SUPER', 'RX 9070', 'RX 9070 XT', 'RX 9070 XTX', 'RTX 4060', 'RTX 4060 Ti')]
CPUS = [piece(name, 'cpu', 'AMD') for name in ('Ryzen 5 5600', 'Ryzen 5 5600G', 'Ryzen 5 5600X', 'Ryzen 7 7800X3D', 'Ryzen 9 7900X3D', 'Ryzen 7 9800X3D')]
RAMS = [piece(name, 'ram') for name in ('16GB DDR4', '16GB DDR5', '32GB DDR5')]
DISKS = [piece(name, 'storage') for name in ('SSD NVMe 1TB', 'SSD NVMe 2TB', 'SATA SSD 1TB')]
PSUS = [piece(name, 'psu') for name in ('Fonte 650W', 'Fonte 750W', 'Fonte 850W')]


@pytest.mark.parametrize('item', GPUS + CPUS + RAMS + DISKS + PSUS)
def test_exact_identity_is_high_among_different_variants(item):
    catalog = {'gpu': GPUS, 'cpu': CPUS, 'ram': RAMS, 'storage': DISKS, 'psu': PSUS}[item['category']]
    result = match_product({'title': item['name'], 'category': item['category']}, catalog)
    assert result.component_id == item['id'], result
    assert result.confidence_level == 'high' and not result.conflicts


@pytest.mark.parametrize('item', GPUS + CPUS + RAMS + DISKS + PSUS)
def test_conflicting_variant_never_selected(item):
    catalog = {'gpu': GPUS, 'cpu': CPUS, 'ram': RAMS, 'storage': DISKS, 'psu': PSUS}[item['category']]
    other = next(c for c in catalog if c['id'] != item['id'])
    result = compare_product({'title': item['name'], 'category': item['category']}, other)
    assert not result.matched and result.component_id is None and result.conflicts


@pytest.mark.parametrize('title', ['rtx-5070 ti', 'GeForce RTX 5070 TI', 'Placa de Vídeo RTX 5070 Ti'])
def test_case_accents_hyphens_keep_suffix(title):
    assert match_product({'title': title, 'category': 'gpu'}, GPUS).component_id == 'rtx-5070-ti'


@pytest.mark.parametrize('brand', ['ASUS', 'Asus', 'asustek'])
def test_brand_aliases(brand):
    assert normalize_brand(brand) == 'asus'


@pytest.mark.parametrize('store', ['KaBuM', 'Kabum', 'KABUM', 'KaBuM!'])
def test_store_aliases(store):
    assert normalize_store(store) == 'kabum'


def test_brand_vram_ambiguity_missing_brand_and_explicit_conflict():
    galax = piece('GALAX RTX 5070 12GB', 'gpu', 'GALAX', {'memory': '12GB'})
    asus = piece('ASUS RTX 5070 12GB', 'gpu', 'ASUS', {'memory': '12GB'})
    match = match_product({'title': 'GALAX GeForce RTX 5070 12GB 1-Click OC', 'category': 'gpu'}, [galax, asus])
    assert match.confidence_level == 'high' and {'model', 'brand', 'vram'} <= set(match.matched_by)
    assert match_product({'title': 'RTX 5070 12GB', 'category': 'gpu'}, [galax, asus]).conflicts == ['variant_ambiguous']
    assert match_product({'title': 'RTX 5070 12GB', 'category': 'gpu'}, [galax]).confidence_level == 'medium'
    assert 'brand_conflict' in compare_product({'title': 'ASUS RTX 5070 12GB', 'category': 'gpu'}, galax).conflicts
    assert 'capacity_conflict' in compare_product({'title': 'GALAX RTX 5070 16GB', 'category': 'gpu'}, galax).conflicts


@pytest.mark.parametrize('title', ['Oferta placa de vídeo', 'GPU em promoção', 'RTX', '', 'RTX 5700'])
def test_generic_incomplete_or_numeric_typo_never_resolves(title):
    result = match_product({'title': title, 'category': 'gpu'}, GPUS)
    assert not result.matched and result.component_id is None


def test_wrong_category_even_explicit_component_id_cannot_bypass_conflicts():
    p = {'title': 'RTX 5070 Ti', 'category': 'cpu', 'component_id': GPUS[0]['id']}
    r = match_product(p, GPUS)
    assert {'category_conflict', 'variant_conflict'} <= set(r.conflicts)


@pytest.mark.parametrize('title', ['RTX 5070 ou RTX 5070 Ti', 'RTX 5070 + RX 9070', 'Ryzen 5 5600 + Ryzen 5 5600G'])
def test_multiple_product_message_rejected(title):
    result = match_product({'title': title}, GPUS + CPUS)
    assert not result.matched and 'multiple_products' in result.conflicts


def test_simple_typo_only_probable_with_sufficient_specs():
    target = piece('Memoria RAM 16GB DDR4', 'ram')
    result = compare_product({'title': 'Memori RAM 16GB DDR4', 'category': 'ram'}, target)
    assert result.confidence_level == 'medium' and result.matched


def test_unit_normalization_preserves_decimal_vs_binary():
    assert capacity_values('1024 GB') == capacity_values('1 TB')
    assert capacity_values('1000GB') != capacity_values('1TB')
    assert capacity_label(1024) == '1TB'
    assert normalize_text('16 GB 6000 MHz 750 W') == '16gb 6000mhz 750w'
    assert normalize_text('Ryzen 7 7800 X3D').endswith('7800x3d')


def test_ram_kit_total_and_frequency_socket_format_conflicts():
    target = piece('Corsair 32GB DDR5 6000MHz', 'ram', 'Corsair', {'capacity': '32GB'})
    assert compare_product({'title': 'Corsair 2x16GB DDR5 6000MHz', 'category': 'ram'}, target).matched
    assert 'frequency_conflict' in compare_product({'title': 'Corsair 32GB DDR5 5600MHz', 'category': 'ram'}, target).conflicts
    target = piece('Ryzen 5 5600', 'cpu', 'AMD', {'socket': 'AM4'})
    assert 'socket_conflict' in compare_product({'title': 'Ryzen 5 5600 AM5', 'category': 'cpu'}, target).conflicts


@pytest.mark.parametrize('value', [None, 0, -1, True, 'NaN', float('inf'), '.001', 'invalid'])
def test_invalid_money(value):
    assert money(value) is None


@pytest.mark.parametrize('url', [None, '', 'javascript:x', 'https://user:pass@shop.test/p', 'https://t.me/channel', 'https://shop.test/banner.jpg'])
def test_url_rejections(url):
    assert offer_url(url) is None


@pytest.mark.parametrize('url', ['https://amzn.to/real', 'https://mercadolivre.com/sec/real', 'https://shop.test/p?affiliate=1'])
def test_short_urls_preserved_without_network(url):
    assert offer_url(url) == url


def test_price_verification_high_medium_seed_and_old():
    target = piece('GALAX RTX 5070 12GB', 'gpu', 'GALAX')
    high = compare_product({'title': target['name'], 'category': 'gpu'}, target)
    medium = compare_product({'title': 'RTX 5070 12GB', 'category': 'gpu'}, target)
    offer = {'price': 3500, 'last_update': NOW.isoformat(), 'url': None}
    q = price_quality(offer, high, now=NOW, source='telegram')
    assert q['verified'] and not q['url_valid']
    assert not price_quality(offer, medium, now=NOW, source='telegram')['verified']
    assert not price_quality(offer, high, now=NOW, source='seed')['verified']
    assert not price_quality({**offer, 'last_update': (NOW-timedelta(days=8)).isoformat()}, high, now=NOW, source='mercado_livre')['verified']
    assert history_observation(target['id'], offer, q)['source'] == 'telegram'
    assert history_observation(target['id'], offer, price_quality(offer, medium, now=NOW, source='telegram')) is None


def test_best_price_real_before_seed_medium_opt_in_and_unidentified_legacy():
    def priced(value, source, level, verified=False):
        return {'price': value, 'quality': {'source': source, 'product_match_level': level, 'verified': verified}}
    seed, high, medium = priced(100, 'seed', 'low'), priced(3500, 'telegram', 'high', True), priced(3000, 'mercado_livre', 'medium')
    assert best_known_price([seed, high, medium]) == high
    assert best_known_price([seed, medium]) == seed
    assert best_known_price([seed, medium], allow_medium=True) == medium
    assert not catalog_offers({**GPUS[0], 'prices': [{'price': 1, 'source': 'mercado_livre', 'last_update': NOW.isoformat()}]}, NOW)[0]['quality']['verified']


def test_equivalence_across_sources_preserves_coupon_and_affiliate_queries():
    a = {'price': '3500.00', 'store': 'KaBuM', 'coupon': 'GPU10', 'url': 'https://shop.test/p?a=1', 'source': 'telegram'}
    b = {**a, 'price': 3500, 'store': 'KABUM', 'source': 'mercado_livre'}
    assert equivalence_key('gpu', a) == equivalence_key('gpu', b)
    assert equivalence_key('gpu', a) != equivalence_key('gpu', {**b, 'coupon': 'OTHER'})
    assert equivalence_key('gpu', a) != equivalence_key('gpu', {**b, 'url': 'https://shop.test/p?a=2'})


def document():
    return {'telegram': {'chat_id': -100, 'message_id': 10, 'sent_at': NOW}, 'status': 'published',
            'created_at': NOW, 'raw_text': 'RTX 5070 por R$ 3500', 'product': {'name': 'RTX 5070', 'component_type': 'gpu'},
            'offer': {'price': 3500, 'store': 'KaBuM', 'coupon': 'GPU10', 'url': 'https://shop.test/product', 'url_source': 'button'},
            'notifications_processed_at': NOW, 'links': ['https://shop.test/product']}


def test_persistence_reprocess_history_and_dry_run_never_writes():
    db = mongomock.MongoClient(tz_aware=True).db
    db.components.insert_one(deepcopy(GPUS[0]))
    db.telegram_promotions.insert_one(document())
    before = db.telegram_promotions.find_one()
    report = reprocess(db, limit=100, dry_run=True, now=NOW)
    assert report['proposed']['counts']['high'] == 1
    assert db.telegram_promotions.find_one() == before and db.product_price_history.count_documents({}) == 0
    repository = PromotionRepository(db)
    saved = repository.refresh_quality({'_id': before['_id']})
    assert saved['product']['match_level'] == 'high'
    for key in ('raw_text', 'status', 'created_at', 'notifications_processed_at', 'links'):
        assert saved[key] == before[key]
    assert saved['offer']['url'] == before['offer']['url']
    # Original observation is old relative to wall clock, and cannot become fresh merely by reprocessing.
    assert saved['offer']['captured_at'].startswith('2026-10-27T12:00:00')
    repository.refresh_quality({'_id': before['_id']})
    assert db.product_price_history.count_documents({}) <= 1


def test_quality_report_percentages_and_empty():
    enriched = enrich_promotion(document(), GPUS, NOW)
    report = quality_report([enriched, {'product': {'match_level': 'low'}, 'offer': {}}])
    assert report['percentages']['high'] == 50 and report['percentages']['url'] == 50
    assert quality_report([])['percentages']['high'] == 0


@pytest.mark.parametrize('title', ['Placa-mãe HUSKY B550 + Processador AMD Ryzen 7 5700X',
                                  'Kit upgrade Ryzen 7 5700X placa-mãe A520M + cooler'])
def test_real_bundle_regressions(title):
    assert 'multiple_products' in match_product({'title': title}, [piece('AMD Ryzen 7 5700X', 'cpu', 'AMD')]).conflicts


def test_real_chipset_regression_b850m_is_not_b650():
    target = piece('Placa-mãe B650 AM5 DDR5', 'motherboard', 'ASRock', {'chipset': 'B650', 'form_factor': 'ATX'})
    result = compare_product({'title': 'Placa-mãe ASRock B850M Challenger AM5 Micro ATX DDR5', 'category': 'motherboard'}, target)
    assert 'variant_conflict' in result.conflicts and 'format_conflict' in result.conflicts


def test_repository_records_only_high_history_with_original_time():
    from datetime import datetime
    db = mongomock.MongoClient(tz_aware=True).db
    db.components.insert_one(deepcopy(GPUS[0]))
    doc = document()
    doc['telegram']['sent_at'] = datetime.now(timezone.utc)
    repository = PromotionRepository(db)
    assert repository.save(doc)
    obs = db.product_price_history.find_one()
    assert obs['source'] == 'telegram' and obs['match_level'] == 'high'
    assert not repository.save(doc)
    assert db.product_price_history.count_documents({}) == 1
    db.telegram_promotions.update_one({}, {'$set': {'raw_text': 'RTX 5070 Ti', 'product.name': 'RTX 5070 Ti'}})
    refreshed = repository.refresh_quality({})
    assert refreshed['product']['component_id'] is None
    assert refreshed['product']['previous_component_id'] == GPUS[0]['id']
    assert refreshed['offer']['price'] == 3500 and refreshed['price_observation'] is None
    assert db.product_price_history.find_one()['verified'] is False


@pytest.mark.parametrize('flag', ['ignored', 'demo'])
def test_ineligible_promotion_never_verified(flag):
    doc = document()
    if flag == 'ignored':
        doc['status'] = 'ignored'
    else:
        doc['is_demo'] = True
    assert not enrich_promotion(doc, GPUS, NOW)['offer']['verified']


def test_low_quality_key_does_not_suppress_unidentified_alert_products():
    from services.telegram_collector.matcher import product_identity
    doc = {'raw_text': 'Peça desconhecida', 'product': {'matcher_version': 'product-match-v1.0',
           'match_level': 'low', 'normalized_key': 'cpu||||'}}
    assert product_identity(doc) is None


def test_generic_catalog_board_name_does_not_prove_manufacturer():
    target = piece('Placa-mãe B650 AM5 DDR5', 'motherboard', 'ASRock')
    result = compare_product({'title': target['name'], 'category': 'motherboard'}, target)
    assert result.confidence_level == 'medium'
