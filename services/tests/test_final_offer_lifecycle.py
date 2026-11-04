from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from services.product_matching.quality import offer_state, price_quality, best_known_price
from services.product_matching.matcher import compare_product
from services.telegram_collector.parser import parse_message

NOW = datetime.now(timezone.utc)


@pytest.mark.parametrize('minutes,state', [(10, 'active'), (-1, 'expired'), (0, 'active')])
def test_explicit_deadline(minutes, state):
    offer = {'coupon': 'ANNOUNCED', 'valid_until': (NOW + timedelta(minutes=minutes)).isoformat()}
    assert offer_state(offer, now=NOW) == state


def test_unknown_and_invalid_dates_never_claim_checkout():
    assert offer_state({}, now=NOW) == 'unknown'
    assert offer_state({'valid_until': 'invalid'}, now=NOW) == 'unknown'


@pytest.mark.parametrize('advert,expected', [('1x16GB', False), ('2x8GB', True), ('2x16GB', False), ('single module 16GB', False), ('kit 16GB', True)])
def test_single_and_kit_are_distinct(advert, expected):
    c = {'id': 'kit', 'name': 'Corsair DDR4 2x8GB 3200MHz', 'brand': 'Corsair', 'category': 'ram', 'technical_specs': {'capacity': '16GB'}}
    match = compare_product({'title': 'Corsair DDR4 ' + advert + ' 3200MHz'}, c)
    assert (not match.conflicts) == expected


def test_announced_deadline_is_parsed_without_inventing_year():
    assert parse_message('Oferta válida até 20/11/2026 18:00')['offer']['valid_until'] == '2026-11-20T18:00:00-03:00'
    assert not parse_message('Oferta válida até 20/11')['offer'].get('valid_until')


def test_expired_coupon_falls_back_to_independent_current_price_and_preserves_history():
    c = {'id': 'gpu', 'name': 'RTX 5060 8GB', 'category': 'gpu', 'brand': 'NVIDIA'}
    match = compare_product({'title': 'RTX 5060 8GB'}, c)
    old = {'price': 100, 'source': 'telegram', 'coupon': 'OLD', 'captured_at': NOW.isoformat(), 'coupon_valid_until': (NOW-timedelta(days=1)).isoformat()}
    new = {'price': 110, 'source': 'telegram', 'captured_at': NOW.isoformat()}
    history = deepcopy([old, new])
    offers = [{**o, 'quality': price_quality(o, match, now=NOW)} for o in history]
    assert best_known_price(offers)['price'] == 110
    assert history == [old, new]
    assert best_known_price(offers[:1]) is None
