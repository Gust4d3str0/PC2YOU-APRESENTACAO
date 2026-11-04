from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.audit_post_backfill_quality import (audit_snapshot, identity_tokens, internal_id,
                                                main, price_review, review_identity)
from product_matching import CatalogMatcher
from product_matching.promotions import enrich_promotion

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def component(cid='rtx-5060-ti-8gb', name='GeForce RTX 5060 Ti 8GB', category='gpu'):
    return {'id': cid, 'name': name, 'category': category, 'brand': 'NVIDIA',
            'technical_specs': {'memory': '8GB'}, 'compatibility': {}}


def promotion(title='INNO3D RTX 5060 Ti 8GB', **offer):
    return {'_id': '0123456789abcdef01234567', 'raw_text': title, 'product': {'name': title},
            'offer': {'price': 1000, **offer}, 'status': 'parsed', 'created_at': NOW,
            'telegram': {'chat_id': 99999, 'message_id': 77777, 'sent_at': NOW}}


@pytest.mark.parametrize('left,right', [
    ('RTX 5060', 'RTX 5060 Ti'), ('RTX 5060 Ti 8GB', 'RTX 5060 Ti 16GB'),
    ('RTX 5070', 'RTX 5070 Ti'), ('RX 9060 XT', 'RX 9070 XT'),
    ('AMD Ryzen 5 5600', 'AMD Ryzen 5 5600G'), ('AMD Ryzen 5 5600G', 'AMD Ryzen 5 5600X'),
    ('AMD Ryzen 7 5700X', 'AMD Ryzen 7 5700X3D'), ('AMD Ryzen 7 9700X', 'AMD Ryzen 7 9800X3D'),
    ('Intel Core i5-14600K', 'Intel Core i5-14600KF'), ('Placa mae B650M', 'Placa mae B850M'),
])
def test_literal_audit_rejects_critical_variants_even_with_high_score(left, right):
    c = component(name=right, category='motherboard' if 'Placa' in right else 'cpu' if 'Ryzen' in right or 'Intel' in right else 'gpu')
    row = promotion(left)
    row['product'].update(match_level='high', match_confidence=.99, component_id=c['id'])
    result = review_identity(row, c, {'component_id': c['id']})
    assert result['assessment'] == 'suspected_false_positive'


def test_high_score_without_vram_is_probable_not_confirmed():
    c = component()
    row = promotion('RTX 5060 Ti')
    row['product'].update(component_id=c['id'], match_confidence=.99)
    assert review_identity(row, c, {'component_id': c['id']})['assessment'] == 'probable_match'


def test_class_requires_explicit_ddr_socket_and_format_and_remains_class_only():
    c = {'id': 'b850m', 'name': 'Placa mae B850M AM5 DDR5 classe', 'category': 'motherboard',
         'identity_scope': 'chipset-memory-form-factor-class', 'technical_specs': {'socket': 'AM5', 'memory_type': 'DDR5'}}
    row = promotion('Placa mae B850M')
    row['product']['component_id'] = 'b850m'
    assert review_identity(row, c, {'component_id': 'b850m'})['assessment'] == 'probable_match'
    row['product']['name'] = 'Placa mae B850M AM5 DDR5 mATX'
    result = review_identity(row, c, {'component_id': 'b850m'})
    assert result['assessment'] == 'confirmed_match'
    assert 'association_is_class_only_not_commercial_sku' in result['evidence']


def test_ram_total_capacity_does_not_hide_single_vs_kit_and_family_conflicts():
    c = {'id': 'kit', 'name': 'Corsair Vengeance LPX 16GB 2x8GB DDR4', 'category': 'kit-ram',
         'technical_specs': {'capacity': '16GB', 'modules': '2x8GB'}}
    row = promotion('Corsair Vengeance RGB RS 16GB 1x16GB DDR4')
    row['product']['component_id'] = 'kit'
    result = review_identity(row, c, {'component_id': 'kit'})
    assert 'single_module_vs_kit' in result['conflicts']
    assert 'ram_commercial_family_mismatch' in result['conflicts']


def test_nonexistent_catalog_reference_is_not_confirmed():
    assert review_identity(promotion(), None, {'component_id': None})['assessment'] == 'suspected_false_positive'


def test_empty_identity_is_unverifiable_despite_high_score():
    row = promotion('Oferta especial')
    row['product'].update(component_id='gpu', match_confidence=.99)
    assert review_identity(row, component(cid='gpu'), {'component_id': 'gpu'})['assessment'] == 'unverifiable'


def test_verified_flag_can_pass_implementation_without_currency_url_store_but_audit_records_gaps():
    c = component()
    row = promotion('INNO3D RTX 5060 Ti 8GB por R$ 1.000,00')
    matcher = CatalogMatcher([c])
    enriched = enrich_promotion(row, matcher, NOW)
    identity = review_identity(enriched, c, {'component_id': c['id']})
    result = price_review(enriched, identity, enriched, matcher, NOW)
    assert enriched['offer']['verified'] is True
    assert result['implementation_rules_pass_now'] is True
    assert result['currency_field'] is None
    assert result['currency_evidence'] == 'inferred_from_R$_text'
    assert result['advertised_price_evidence'] == 'inconclusive'
    assert 'offer_url_missing_or_invalid' in result['issues']


def test_expiry_does_not_imply_identity_drift_and_capture_replay_is_labeled_hypothetical():
    c = component()
    row = enrich_promotion(promotion(), CatalogMatcher([c]), NOW)
    result = audit_snapshot([row], [c], now=NOW + timedelta(days=4))
    assert result['persisted_vs_recalculated']['identity_differences'] == []
    price = result['verified_price_audit']['cases'][0]
    assert price['implementation_rules_pass_now'] is False
    assert price['implementation_rules_pass_if_evaluated_at_capture'] is True
    assert 'Hypothetical' in price['historical_evaluation_caveat']


def test_store_url_contradiction_and_redirect_unknown_are_reported_without_network():
    c = component()
    row = promotion('INNO3D RTX 5060 Ti 8GB por R$ 1.000,00', store='Amazon', url='https://www.kabum.com.br/produto/123')
    matcher = CatalogMatcher([c])
    enriched = enrich_promotion(row, matcher, NOW)
    identity = review_identity(enriched, c, {'component_id': c['id']})
    assert price_review(enriched, identity, enriched, matcher, NOW)['store_url_mismatch']
    enriched['offer']['url'] = 'https://short.example/x'
    assert 'url_destination_not_proven_offline' in price_review(enriched, identity, enriched, matcher, NOW)['issues']


def test_audit_is_pure_and_never_exports_raw_message_or_telegram_identifiers():
    c = component()
    row = enrich_promotion(promotion('INNO3D RTX 5060 Ti 8GB por R$ 1.000,00 contato pessoa@example.com'), CatalogMatcher([c]), NOW)
    snapshot = deepcopy((row, c))
    result = audit_snapshot([row], [c], now=NOW)
    assert (row, c) == snapshot
    assert result['production_writes_performed'] is False
    assert not any(s in str(result) for s in ('pessoa@example.com', '99999', '77777', 'raw_text'))


def test_non_objectid_internal_identifier_is_hashed_instead_of_exposing_content():
    assert 'phone' not in internal_id({'_id': 'phone-sensitive-data'})


def test_catalog_drift_is_detected_independently_of_the_stored_score():
    c = component()
    row = enrich_promotion(promotion(), CatalogMatcher([c]), NOW)
    c['name'] = 'GeForce RTX 5060 8GB'
    result = audit_snapshot([row], [c], now=NOW)
    assert result['high_review']['counts']['suspected_false_positive'] == 1
    assert len(result['persisted_vs_recalculated']['identity_differences']) == 1


def test_cli_rejects_apply_before_any_database_access():
    with pytest.raises(SystemExit) as exc:
        main(['--apply'])
    assert exc.value.code == 2


def test_history_reference_integrity_reports_orphans_without_exporting_telegram_ids():
    c = component()
    row = enrich_promotion(promotion(), CatalogMatcher([c]), NOW)
    history = [{'telegram': {'chat_id': 123, 'message_id': 456}, 'component_id': 'absent', 'verified': True, 'match_level': 'medium'}]
    result = audit_snapshot([row], [c], history, NOW)
    assert result['history_integrity']['without_parent_promotion'] == 1
    assert result['history_integrity']['dangling_components'] == 1
    assert result['history_integrity']['verified_not_high'] == 1
