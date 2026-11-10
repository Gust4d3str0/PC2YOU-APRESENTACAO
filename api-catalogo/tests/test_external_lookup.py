"""The technical resolver uses exact indexed keys, preserves provenance and hides prices."""
import mongomock
from fastapi.testclient import TestClient

import main
import services
from database import get_components_collection, ensure_indexes
from catalog_specs.external_identity import search_metadata
from test_api import component
from catalog_specs.external_persistence import ensure_import_indexes
from catalog_specs.lookup import lookup_mongo


def test_resolver_is_static_route_and_retains_external_fields_without_commercial_seed():
    collection = mongomock.MongoClient().db.components
    row = component('amd-5700x', 'AMD Ryzen 7 5700X')
    row.update(brand='AMD', external_ids={'buildcores_opendb': ['uuid']}, mpn=['100-real'],
               identity_scope='model', spec_provenance={'technical_specs__cores': {'source': 'buildcores'}})
    row.update(search_metadata(row))
    collection.insert_one(row)
    ensure_indexes(collection)
    main.app.dependency_overrides[get_components_collection] = lambda: collection
    try:
        response = TestClient(main.app).get('/components/resolve', params={'category': 'cpu', 'q': 'Processador Ryzen 7 5700X'})
        assert response.status_code == 200
        data = response.json()[0]
        assert data['id'] == row['id'] and data['external_ids'] == row['external_ids']
        assert data['prices'] == data['price_history'] == []
        assert data['spec_provenance'] == row['spec_provenance']
        assert TestClient(main.app).get('/components/resolve', params={'category': 'cpu', 'q': 'Ryzen 7 5700'}).json() == []
    finally:
        main.app.dependency_overrides.pop(get_components_collection, None)


def test_admin_created_components_receive_nonnull_unique_lookup_metadata():
    db = mongomock.MongoClient().db
    ensure_import_indexes(db)
    for cid, name in [('cpu-one', 'AMD Ryzen 5 5600'), ('cpu-two', 'AMD Ryzen 5 5600X')]:
        row = component(cid, name)
        row.update(brand='AMD', normalized_identity=None)
        services.create_component(db.components, row)
    assert db.components.count_documents({}) == 2
    assert lookup_mongo(db.components, 'cpu', 'Ryzen 5 5600X')[0]['id'] == 'cpu-two'


def test_admin_name_update_refreshes_exact_lookup_keys():
    collection = mongomock.MongoClient().db.components
    row = component('cpu-one', 'AMD Ryzen 5 5600')
    row['brand'] = 'AMD'
    services.create_component(collection, row)
    services.update_component(collection, 'cpu-one', {'name': 'AMD Ryzen 5 5600G'})
    assert lookup_mongo(collection, 'cpu', 'Ryzen 5 5600') == []
    assert lookup_mongo(collection, 'cpu', 'Ryzen 5 5600G')[0]['id'] == 'cpu-one'
