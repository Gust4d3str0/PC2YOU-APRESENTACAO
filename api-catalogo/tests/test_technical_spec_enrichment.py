"""The official ML integration now persists useful specs through the shared mapper."""
from copy import deepcopy

import mongomock
import ml_products as ml
from test_ml_products import GPU_RAW, Resp, client


def test_official_enrichment_fills_missing_sku_fields_but_preserves_manual_specs(tmp_path):
    api, _, _ = client(tmp_path, Resp(200, GPU_RAW))
    db = mongomock.MongoClient().catalog
    row = {'id': 'windforce-5060-ti-8', 'name': 'Gigabyte RTX 5060 Ti WINDFORCE MAX OC 8GB',
           'brand': 'Gigabyte', 'category': 'gpu', 'identity_scope': 'sku',
           'technical_specs': {'memory': '8GB', 'length_mm': 210}, 'compatibility': {},
           'prices': [{'price': 123, 'url': 'keep'}], 'price_history': ['preserve']}
    db.components.insert_one(deepcopy(row))
    service = ml.MercadoLivreProductEnrichment(db, api)
    assert service.enrich('MLB78085963', row, basis='manual_mapping')['applied']
    result = db.components.find_one({'id': row['id']})
    assert result['technical_specs']['length_mm'] == 210
    assert result['technical_specs']['power_consumption_watts'] == 180
    assert result['compatibility']['min_psu_watts'] == 650
    assert result['prices'] == row['prices'] and result['price_history'] == row['price_history']
    assert result['spec_provenance']['compatibility__min_psu_watts']['source'] == 'mercado_livre.POWER_REQUIREMENT'
