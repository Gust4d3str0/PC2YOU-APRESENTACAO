from datetime import datetime, timedelta, timezone

import mongomock

from scripts.backfill_promotion_conditions import analyse, apply_updates

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
CATALOG = [{'id': 'cpu7800', 'name': 'AMD Ryzen 7 7800X3D', 'category': 'cpu', 'brand': 'AMD', 'technical_specs': {}, 'compatibility': {}}]


def doc(text, hours=1, **offer):
    sent = NOW - timedelta(hours=hours)
    return {'raw_text': text, 'product': {'component_type': 'cpu'}, 'status': 'parsed', 'telegram': {'sent_at': sent}, 'created_at': sent,
            'offer': {'price': 1683.49, 'url': 'https://www.kabum.com.br/produto/1', 'store': 'KaBuM', **offer}}


def collection():
    c = mongomock.MongoClient(tz_aware=True).db.telegram_promotions
    c.insert_many([doc('AMD Ryzen 7 7800X3D', coupon=None),
                   doc('AMD Ryzen 7 7800X3D cupom AURAGAMER somente primeira compra pelo app', coupon='AURAGAMER'),
                   doc('AMD Ryzen 7 7800X3D no PIX ou NuPay válido até 02/11', hours=30),
                   doc('AMD Ryzen 7 7800X3D assinante Prime mínimo de R$ 500 1 uso por CPF', hours=30)])
    return c


def test_dry_run_statistics_do_not_touch_the_database():
    c = collection()
    before = list(c.find({}))
    stats, updates = analyse(c.find({}), CATALOG, NOW)
    assert list(c.find({})) == before
    assert stats['promotions'] == 4 and stats['with_coupon'] == 1 and stats['first_purchase'] == 1 and stats['app_only'] == 1
    assert stats['pix'] == 1 and stats['nupay'] == 1 and stats['membership'] == 1 and stats['minimum_order'] == 1 and stats['max_uses_per_customer'] == 1
    assert stats['explicit_validity'] == 1 and stats['status_expired'] == 1 and stats['status_stale'] == 1
    assert stats['without_known_condition'] == 1 and stats['conditional'] == 3 and stats['to_update'] == 4


def test_apply_is_additive_idempotent_and_preserves_original_fields():
    c = collection()
    originals = {d['_id']: {k: v for k, v in d.items() if k != 'offer'} for d in c.find({})}
    _, updates = analyse(c.find({}), CATALOG, NOW)
    assert apply_updates(c, updates) == 4
    for d in c.find({}):
        assert {k: v for k, v in d.items() if k != 'offer'} == originals[d['_id']]
        assert d['offer']['price'] == 1683.49 and d['offer']['conditions']['conditions_version'] == 2
    dated = c.find_one({'raw_text': {'$regex': 'válido até'}})
    assert dated['offer']['valid_until'].startswith('2026-11-02')
    stats, updates = analyse(c.find({}), CATALOG, NOW)
    assert updates == [] and stats['already_up_to_date'] == 4
    assert apply_updates(c, updates) == 0 and c.count_documents({}) == 4
