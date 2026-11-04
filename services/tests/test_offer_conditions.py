"""Deterministic condition extraction, the offer status model and the validator architecture."""
from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from services.product_matching.offers import (MercadoLivreOfferValidator, OfferValidator, TelegramOfferValidator,
                                              condition_labels, evaluate_offer, extract_conditions, freshness_of, is_conditional)
from services.product_matching.promotions import enrich_promotion
from services.telegram_collector.parser import parse_message
from services.telegram_collector.repository import PromotionRepository

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)          # 12:00 in Sao Paulo
CATALOG = [{'id': 'cpu7800', 'name': 'AMD Ryzen 7 7800X3D', 'category': 'cpu', 'brand': 'AMD',
            'technical_specs': {}, 'compatibility': {}}]


def cond(text, coupon=None, sent=NOW):
    return extract_conditions(text, coupon, sent)


# --- extraction ------------------------------------------------------------------------------------------

@pytest.mark.parametrize('text,field,value', [
    ('Cupom só para primeira compra', 'first_purchase_only', True),
    ('válido no primeiro pedido', 'first_purchase_only', True),
    ('Novos clientes ganham', 'new_customer_only', True),
    ('para novo usuário', 'new_customer_only', True),
    ('Somente pelo app', 'app_only', True),
    ('exclusivo app Kabum', 'app_only', True),
    ('R$ 1.683 no PIX', 'payment_methods', ['PIX']),
    ('via PIX', 'payment_methods', ['PIX']),
    ('pagando no PIX', 'payment_methods', ['PIX']),
    ('pagando com NuPay', 'payment_methods', ['NuPay']),
    ('cartão Nubank', 'payment_methods', ['Nubank']),
    ('com o cartão da loja', 'payment_methods', ['Cartão da loja']),
    ('PIX ou NuPay', 'payment_methods', ['PIX', 'NuPay']),
    ('primeira compra no app', 'first_purchase_only', True),
    ('primeira compra no app', 'app_only', True),
    ('exclusivo pelo app', 'app_only', True),
    ('para assinante Prime', 'membership_required', 'Prime'),
    ('frete grátis Prime', 'membership_required', 'Prime'),
    ('mínimo de R$ 500,00 no carrinho', 'minimum_order', 500.0),
    ('compras acima de R$ 1.200', 'minimum_order', 1200.0),
    ('1 uso por CPF', 'max_uses_per_customer', 1),
    ('1 utilização por cliente', 'max_uses_per_customer', 1),
])
def test_common_conditions_are_recognised(text, field, value):
    assert cond(text)[field] == value


def test_unknown_conditions_stay_null_never_false():
    result = cond('Ryzen 7 7800X3D por R$ 1.683,49 na Kabum')
    assert all(result[k] is None for k in ('requires_coupon', 'first_purchase_only', 'new_customer_only', 'app_only',
                                          'membership_required', 'minimum_order', 'max_uses_per_customer', 'valid_until', 'conditions_text'))
    assert result['payment_methods'] == [] and result['conditions_version'] == 2
    assert not is_conditional(result) and condition_labels(result) == []


def test_coupon_makes_the_price_conditional_without_inventing_other_conditions():
    result = cond('R$ 1.683 com cupom AURAGAMER', coupon='AURAGAMER')
    assert result['requires_coupon'] is True and result['coupon_code'] == 'AURAGAMER' and is_conditional(result)
    assert result['first_purchase_only'] is None and result['app_only'] is None


def test_conditions_text_keeps_the_original_fragment_without_urls():
    text = 'Ryzen 7 7800X3D\nCupom AURAGAMER válido só na primeira compra https://pruuu.me/x\nFrete grátis'
    fragment = cond(text, 'AURAGAMER')['conditions_text']
    assert 'primeira compra' in fragment and 'https' not in fragment and 'Frete' not in fragment


# --- explicit validity ----------------------------------------------------------------------------------

def test_validity_with_day_and_month_uses_the_year_of_the_announcement():
    assert cond('válido até 05/11')['valid_until'] == '2026-11-05T23:59:00-03:00'
    assert cond('válido até 05/11 às 10:30')['valid_until'] == '2026-11-05T10:30:00-03:00'
    assert cond('oferta até 03/11/2026')['valid_until'] == '2026-11-03T23:59:00-03:00'


def test_validity_wraps_to_next_year_when_the_date_already_passed():
    december = datetime(2026, 12, 30, 15, 0, tzinfo=timezone.utc)
    assert cond('válido até 02/01', sent=december)['valid_until'].startswith('2027-01-02')


def test_until_a_clock_time_and_today_only():
    assert cond('até 23:59')['valid_until'] == '2026-11-03T23:59:00-03:00'
    assert cond('Somente hoje!')['valid_until'] == '2026-11-03T23:59:00-03:00'
    assert cond('até 09:00')['valid_until'] is None       # earlier than the message: ambiguous, not guessed


def test_relative_validity_needs_the_announcement_time():
    assert extract_conditions('até 23:59', None, None)['valid_until'] is None
    assert extract_conditions('válido até 05/11/2026', None, None)['valid_until'] == '2026-11-05T23:59:00-03:00'


# --- status model ---------------------------------------------------------------------------------------

def offer(hours=1, **fields):
    return {'price': 1683.49, 'captured_at': (NOW - timedelta(hours=hours)).isoformat(), **fields}


def status(o, **kw):
    return evaluate_offer(o, NOW, conditions=o.get('conditions'), **kw)


def test_recent_unconditional_offer_is_announced_and_eligible_but_never_confirmed():
    result = status(offer())
    assert result['status'] == 'announced' and result['eligible'] and result['freshness'] == 'very_recent'


def test_conditions_make_it_conditional():
    result = status(offer(conditions={'first_purchase_only': True}))
    assert result['status'] == 'conditional' and result['is_conditional'] and result['eligible']


def test_freshness_buckets():
    assert [freshness_of(h) for h in (1, 6, 7, 24, 25, 72, 73)] == ['very_recent', 'very_recent', 'recent', 'recent', 'aging', 'aging', 'stale']


def test_stale_between_24_and_72h_is_eligible_but_flagged_beyond_it_is_not():
    old = status(offer(hours=30))
    assert old['status'] == 'stale' and old['eligible'] and old['reason'] == 'needs_confirmation'
    ancient = status(offer(hours=80))
    assert ancient['status'] == 'stale' and not ancient['eligible']


def test_explicit_validity_in_the_future_beats_generic_freshness():
    result = status(offer(hours=100, valid_until=(NOW + timedelta(hours=5)).isoformat()))
    assert result['status'] == 'announced' and result['eligible'] and result['reason'] == 'explicit_validity'


def test_passed_validity_is_expired_even_if_the_announcement_is_fresh():
    result = status(offer(hours=1, valid_until=(NOW - timedelta(minutes=1)).isoformat()))
    assert result['status'] == 'expired' and not result['eligible']


def test_validity_found_in_the_text_conditions_also_expires():
    assert status(offer(conditions={'valid_until': (NOW - timedelta(hours=1)).isoformat()}))['status'] == 'expired'


def test_manual_not_working_is_invalid_and_never_eligible():
    result = status(offer(manual_validation_status='not_working', manual_validated_at=NOW.isoformat()))
    assert result['status'] == 'invalid' and result['reason'] == 'manual' and not result['eligible']


def test_manual_working_confirms_only_for_a_while_and_after_the_announcement():
    fresh = status(offer(hours=2, manual_validation_status='working', manual_validated_at=(NOW - timedelta(hours=1)).isoformat()))
    assert fresh['status'] == 'confirmed' and fresh['eligible']
    lapsed = status(offer(hours=40, manual_validation_status='working', manual_validated_at=(NOW - timedelta(hours=30)).isoformat()))
    assert lapsed['status'] == 'stale'
    before = status(offer(hours=1, manual_validation_status='working', manual_validated_at=(NOW - timedelta(hours=3)).isoformat()))
    assert before['status'] == 'announced'      # a check older than the announcement says nothing about it


def test_a_later_check_wins_over_an_earlier_one():
    result = status(offer(hours=5, manual_validation_status='working', manual_validated_at=(NOW - timedelta(hours=3)).isoformat(),
                          verified_price=2000, verification_source='manual', verified_at=(NOW - timedelta(hours=1)).isoformat()))
    assert result['status'] == 'invalid' and result['reason'] == 'price_changed'


def test_verified_price_that_differs_makes_the_offer_invalid_but_one_that_matches_confirms():
    different = status(offer(price=2789, verified_price=3059.99, verification_source='mercado_livre_api', verified_at=NOW.isoformat()))
    assert different['status'] == 'invalid' and different['reason'] == 'price_changed'
    same = status(offer(price=2789, verified_price=2790, verification_source='mercado_livre_api', verified_at=NOW.isoformat()))
    assert same['status'] == 'confirmed'


def test_no_price_is_never_eligible():
    assert not status({'price': 0, 'captured_at': NOW.isoformat()})['eligible']
    assert not status({'price': None, 'captured_at': NOW.isoformat()})['eligible']


# --- enrichment / parser / persistence -----------------------------------------------------------------

def promotion(text, **offer_fields):
    return {'raw_text': text, 'product': {'component_type': 'cpu'}, 'status': 'parsed', 'telegram': {'sent_at': NOW - timedelta(hours=1), 'chat_id': -1001000000001, 'message_id': 9},
            'created_at': NOW - timedelta(hours=1), 'offer': {'price': 1683.49, 'store': 'KaBuM', 'coupon': 'AURAGAMER', 'url': 'https://www.kabum.com.br/produto/1', **offer_fields}}


def test_enrich_derives_conditions_for_documents_stored_before_this_feature():
    enriched = enrich_promotion(promotion('AMD Ryzen 7 7800X3D com cupom AURAGAMER na primeira compra'), CATALOG, NOW)
    assert enriched['offer']['conditions']['first_purchase_only'] is True
    assert enriched['evaluation']['status'] == 'conditional' and enriched['evaluation']['eligible']


def test_enrich_uses_validity_announced_in_the_text():
    enriched = enrich_promotion(promotion('AMD Ryzen 7 7800X3D válido até 02/11'), CATALOG, NOW)
    assert enriched['offer']['valid_until'].startswith('2026-11-02') and enriched['evaluation']['status'] == 'expired'


def test_parser_stores_conditions_and_validity():
    parsed = parse_message('Ryzen 7 7800X3D R$ 1.683,49 cupom AURAGAMER primeira compra, somente pelo app até 23:59', sent_at=NOW)
    offer_ = parsed['offer']
    assert offer_['coupon'] == 'AURAGAMER' and offer_['conditions']['first_purchase_only'] and offer_['conditions']['app_only']
    assert offer_['valid_until'] == '2026-11-03T23:59:00-03:00'


def test_parser_without_conditions_keeps_the_offer_clean():
    assert 'conditions' not in parse_message('Ryzen 7 7800X3D R$ 1.683,49')['offer']


def test_repository_does_not_freeze_status_in_the_database():
    database = mongomock.MongoClient(tz_aware=True).db
    database.components.insert_many(CATALOG)
    repository = PromotionRepository(database)
    repository.save({**promotion('AMD Ryzen 7 7800X3D'), 'links': []})
    assert 'evaluation' not in database.telegram_promotions.find_one()


def test_history_does_not_duplicate_an_identical_observation_the_same_day():
    database = mongomock.MongoClient(tz_aware=True).db
    database.components.insert_many(CATALOG)
    repository = PromotionRepository(database)
    for message_id in (1, 2, 3):
        doc = promotion('AMD Ryzen 7 7800X3D', coupon=None)
        doc['telegram']['message_id'] = message_id
        repository.save({**doc, 'links': []})
    assert database.telegram_promotions.count_documents({}) == 3
    rows = list(database.product_price_history.find({'verified': True}))
    assert len(rows) == 1 and rows[0]['coupon'] is None and rows[0]['observed_at']


# --- validators -----------------------------------------------------------------------------------------

def test_telegram_validator_only_counts_a_recorded_human_check():
    validator = TelegramOfferValidator()
    assert validator.validate({}).outcome == 'unknown' and validator.fields(validator.validate({})) == {}
    checked = validator.validate({'manual_validation_status': 'not_working', 'manual_validated_at': NOW.isoformat()})
    assert checked.outcome == 'not_working' and checked.source == 'manual'


def test_mercado_livre_validator_is_inert_without_a_lookup_and_compares_prices_with_one():
    inert = MercadoLivreOfferValidator()
    assert inert.validate({'price': 100}).outcome == 'unknown' and inert.validate({'price': 100}).reason == 'mercado_livre_not_configured'
    same = MercadoLivreOfferValidator(lambda o: 100.5).validate({'price': 100}, NOW)
    assert same.outcome == 'working' and same.verified_price == 100.5 and same.source == 'mercado_livre_api'
    changed = MercadoLivreOfferValidator(lambda o: 130).validate({'price': 100}, NOW)
    assert changed.outcome == 'not_working' and changed.reason == 'price_changed'
    broken = MercadoLivreOfferValidator(lambda o: 1 / 0).validate({'price': 100})
    assert broken.outcome == 'unknown' and broken.reason == 'lookup_failed'


def test_validator_result_fields_feed_the_status_model():
    result = MercadoLivreOfferValidator(lambda o: 3059.99).validate({'price': 2789}, NOW)
    fields = MercadoLivreOfferValidator().fields(result)
    assert fields['verification_source'] == 'mercado_livre_api' and fields['verified_price'] == 3059.99
    assert status(offer(price=2789, **fields))['status'] == 'invalid'
    assert issubclass(MercadoLivreOfferValidator, OfferValidator)


def test_manual_confirmation_expires_after_six_hours_by_default():
    inside = status(offer(hours=8, manual_validation_status='valid', manual_validated_at=(NOW - timedelta(hours=5)).isoformat()))
    outside = status(offer(hours=8, manual_validation_status='valid', manual_validated_at=(NOW - timedelta(hours=7)).isoformat()))
    assert inside['status'] == 'confirmed' and outside['status'] == 'announced'


def test_manual_invalid_never_expires_and_both_spellings_are_accepted():
    for spelling in ('invalid', 'not_working'):
        result = status(offer(hours=60, manual_validation_status=spelling, manual_validated_at=(NOW - timedelta(hours=59)).isoformat()))
        assert result['status'] == 'invalid' and not result['eligible']
    assert status(offer(manual_validation_status='working', manual_validated_at=NOW.isoformat()))['status'] == 'confirmed'


def test_first_purchase_coupon_is_conditional_and_labelled_plainly():
    result = cond('R$ 1.699 com cupom XYZ. Somente primeira compra', coupon='XYZ')
    assert is_conditional(result) and result['first_purchase_only'] is True
    assert 'Somente primeira compra' in condition_labels(result)


def test_coupon_without_known_conditions_only_marks_the_coupon():
    result = cond('R$ 1.699 com cupom XYZ', coupon='XYZ')
    assert condition_labels(result) == ['Exige cupom'] and result['first_purchase_only'] is None and result['conditions_text'] is not None
