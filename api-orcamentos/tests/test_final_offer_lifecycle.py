from copy import deepcopy
from datetime import timedelta
from ai_upgrade_context import normalized_promotions
from test_ai_upgrades import v2, promotion


def test_v2_ignores_expired_coupon_and_selects_new_offer_without_changing_history(v2):
    old = promotion(v2)
    old['offer']['valid_until'] = (v2.now-timedelta(minutes=1)).isoformat()
    new = deepcopy(old)
    new['_id'] = 'new-offer'
    new['offer'].update(coupon=None, valid_until=(v2.now+timedelta(days=1)).isoformat(), price=3699)
    records = deepcopy([old, new])
    result = normalized_promotions(records, v2.catalog.items, v2.now)
    assert result['rtx-5070'][0]['promotion_id'] == 'new-offer'
    assert records == [old, new]
    assert not normalized_promotions([old], v2.catalog.items, v2.now)
