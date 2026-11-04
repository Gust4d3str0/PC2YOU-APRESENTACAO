from copy import deepcopy

from scripts.preview_catalog_enrichment import preview
from catalog_enrichment import discover, baseline_divergences


def promotion(title):
    return {'raw_text': title, 'product': {}, 'telegram': {'message_id': 12345}}


def test_discovery_excludes_non_components_combos_existing_models_and_private_data():
    rows = [promotion('INNO3D RTX 5060 Ti 8GB'), promotion('Asus RTX 5060 Ti 16GB'),
            promotion('Notebook Acer RTX 5060 8GB'), promotion('Samsung A57 8GB 128GB'),
            promotion('Kit upgrade AMD Ryzen 5 5600 + placa mae B550M'),
            promotion('AMD Ryzen 5 5600'), promotion('Fonte liquida10')]
    base = [{'id': 'ryzen-5-5600', 'name': 'AMD Ryzen 5 5600', 'category': 'cpu', 'brand': 'AMD'}]
    snapshot = deepcopy(rows)
    result = discover(rows, base)
    assert rows == snapshot
    assert result['missing_model_candidates'] == 1
    candidate = result['candidates'][0]
    assert candidate['normalized_model'] == 'rtx5060ti' and candidate['occurrences'] == 2
    assert candidate['capacities_seen'] == ['8GB', '16GB']
    assert not any(s in str(result) for s in ('12345', 'raw_text', 'message_id', 'Notebook'))


def test_preview_is_pure_and_accounts_for_new_high_and_high_identity_changes():
    rows = [promotion('AMD Ryzen 5 7500F'), promotion('AMD Ryzen 7 9700X')]
    base = [{'id': 'cpu-original', 'name': 'AMD Ryzen 7 9700X', 'brand': 'AMD', 'category': 'cpu'}]
    additions = [{'id': 'ryzen-5-7500f', 'name': 'AMD Ryzen 5 7500F', 'brand': 'AMD', 'category': 'cpu'}]
    snapshot = deepcopy((rows, base, additions))
    result = preview(rows, base, additions)
    assert (rows, base, additions) == snapshot
    assert result['before'] == {'low': 1, 'high': 1}
    assert result['after'] == {'high': 2}
    assert result['transitions']['low->high'] == 1
    assert result['transitions']['high->high_different'] == 0
    assert result['mongo_written'] is False


def test_live_baseline_check_ignores_prices_and_detects_stale_identity():
    base = [{'id': 'ryzen-5-7600', 'name': 'AMD Ryzen 5 7600', 'brand': 'AMD', 'category': 'cpu',
             'technical_specs': {'socket': 'AM5'}, 'compatibility': {'socket': 'AM5'}}]
    live = [{**deepcopy(base[0]), 'prices': [{'price': 999}], 'quality': {'custom': True}}]
    assert baseline_divergences(base, live) == []
    live[0]['name'] = 'AMD Ryzen 5 8600G'
    assert baseline_divergences(base, live) == [{'id': 'ryzen-5-7600', 'fields': ['name']}]


def test_baseline_missing_or_duplicate_ids_block_readiness():
    row = {'id': 'one', 'name': 'One'}
    assert baseline_divergences([row], [])
    assert baseline_divergences([row], [row, row])
