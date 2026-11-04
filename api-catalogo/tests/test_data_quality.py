from datetime import datetime, timezone

import mongomock
import pytest

import ml_service
import services
from product_matching import compare_product


def component():
    return {'id': 'galax-5070', 'name': 'GALAX RTX 5070 12GB', 'brand': 'GALAX', 'category': 'gpu',
            'technical_specs': {'memory': '12GB'}, 'compatibility': {}, 'prices': [], 'price_history': []}


def item(**updates):
    return {'id': 'MLB12345', 'title': 'GALAX GeForce RTX 5070 12GB', 'price': 3599.9,
            'condition': 'new', 'status': 'active', 'permalink': 'https://produto.mercadolivre.com.br/MLB-12345', **updates}


@pytest.mark.parametrize('title', ['GALAX RTX 5070 Ti 12GB', 'GALAX RTX 5070 SUPER 12GB',
                                  'GALAX RTX 5070 16GB', 'ASUS RTX 5070 12GB', 'RTX 5070 12GB',
                                  'GALAX RTX 5070 + RTX 5070 Ti'])
def test_ml_rejects_conflicts_and_probable_board_vendor(title):
    assert ml_service._offer_from_item(item(title=title), component()) is None


def test_ml_high_offer_has_persistable_evidence_and_url_origin():
    offer = ml_service._offer_from_item(item(), component())
    assert offer['product_match']['confidence_level'] == 'high'
    assert offer['quality']['verified'] and offer['quality']['url_valid']
    assert offer['quality']['url_source'] == 'marketplace_api' and offer['equivalence_key']


@pytest.mark.parametrize('url', [None, '', 'javascript:bad', 'https://www.mercadolivre.com.br/'])
def test_ml_missing_url_never_fabricated_from_item_id(url):
    offer = ml_service._offer_from_item(item(permalink=url), component())
    assert offer['url'] == '' and not offer['quality']['url_valid']
    assert offer['quality']['url_source'] == 'unknown'


def test_marketplace_brand_attribute_counts_as_evidence():
    offer = ml_service._offer_from_item(item(title='GeForce RTX 5070 12GB', attributes=[{'id': 'BRAND', 'value_name': 'GALAX'}]), component())
    assert offer['quality']['verified']


@pytest.mark.parametrize('attributes', [[{'id': 'MODEL', 'value_name': 'RTX 5070 Ti'}],
                                      [{'id': 'MEMORY_SIZE', 'value_name': '16GB'}]])
def test_marketplace_attributes_can_veto_a_plausible_title(attributes):
    assert ml_service._offer_from_item(item(attributes=attributes), component()) is None


def test_catalog_recomputes_score_and_does_not_trust_stored_high():
    target = component()
    bad = ml_service._offer_from_item(item(), target)
    bad['title'] = 'ASUS RTX 5070 Ti 16GB'
    target['prices'] = [bad]
    assert services.best_price(target) is None
    assert services.price_summary(target)['real_prices_count'] == 0


def test_price_snapshot_contains_separate_high_observations_ignoring_seed():
    target = component()
    offer = ml_service._offer_from_item(item(), target)
    target['prices'] = [{'price': 100, 'store': 'Seed', 'source': 'seed'}, offer]
    assert services.best_price(target)['source'] == 'mercado_livre'
    snapshot = services.build_price_snapshot(target, datetime.now(timezone.utc).isoformat(), 'success')
    assert snapshot['min_price'] == 3599.9  # Seed prices are legacy and no longer enter the real snapshot.
    assert len(snapshot['observations']) == 1
    observed = snapshot['observations'][0]
    assert observed['source'] == 'mercado_livre' and observed['price'] == 3599.9
    assert observed['match_confidence'] >= .85 and observed['component_id'] == target['id']


def test_catalog_create_schema_preserves_quality_fields():
    from schemas import Price
    offer = ml_service._offer_from_item(item(), component())
    saved = Price.model_validate(offer).model_dump()
    assert saved['quality']['verified'] and saved['product_match']['component_id'] == 'galax-5070'


def test_public_catalog_separates_weak_prices_without_changing_stored_data():
    collection = mongomock.MongoClient().db.components
    target = component()
    bad = ml_service._offer_from_item(item(), target)
    bad['title'] = 'ASUS RTX 5070 Ti 16GB'
    target['prices'] = [{'price': 100, 'source': 'seed', 'store': 'Seed'}, bad]
    collection.insert_one(target)
    before = collection.find_one()
    public = services.get_component(collection, target['id'])
    assert public['prices'] == [] and public['price_history'] == []  # Seed is legacy: never a current price.
    assert len(public['unverified_prices']) == 1
    assert not public['unverified_prices'][0]['quality']['verified']
    assert collection.find_one() == before
