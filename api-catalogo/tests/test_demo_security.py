import sys
from pathlib import Path
import mongomock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services'))
from demo import install, is_blocked
from demo.routes import COLLECTIONS
from demo.sanitize import sanitize
from database import get_components_collection
from seed import COMPONENTS

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('DEMO_MODE', 'true')
    db = mongomock.MongoClient().demo
    db.components.insert_many([dict(c) for c in COMPONENTS])
    db.components.update_one({}, {'$set': {'password': 'private', 'unexpected_person': 'Do not expose'}})
    app = FastAPI()
    app.dependency_overrides[get_components_collection] = lambda: db.components
    install(app)
    return TestClient(app)

@pytest.mark.parametrize('method', ['POST','PUT','PATCH','DELETE'])
@pytest.mark.parametrize('path', ['/demo/database','/demo/matcher','/demo/telegram-parse','/components/x'])
def test_demo_rejects_writes(client, method, path):
    assert client.request(method,path,json={}).status_code == 403

def test_only_batch_post_is_exception():
    assert not is_blocked('POST','/components/batch')
    assert is_blocked('DELETE','/components/batch')

def test_collection_whitelist_and_bounds(client):
    assert client.get('/demo/database/users').status_code == 404
    assert client.get('/demo/database/components?page_size=11').status_code == 422
    assert client.get('/demo/database/components?page=101').status_code == 422
    rows = client.get('/demo/database/components').json()
    assert len(rows['documents']) == 5
    assert 'private' not in str(rows)
    assert 'Do not expose' not in str(rows)
    assert set(COLLECTIONS) == {'components','telegram_promotions','product_price_history','external_product_enrichment','ml_integration_state','telegram_service_status'}

def test_matcher_real_and_conservative(client):
    result = client.get('/demo/matcher',params={'text':'Processador AMD Ryzen 7 7800X3D 4.2GHz AM5'}).json()
    assert result['result']['component_id'] == 'ryzen-7-7800x3d'
    assert result['result']['level'] == 'high'
    ambiguous = client.get('/demo/matcher',params={'text':'Placa de vídeo RTX 5060 Ti'}).json()
    assert not ambiguous['result']['matched']

def test_sensitive_nested_values_and_url_credentials():
    result = sanitize({'token': 'private', 'nested': {'phone':'private', 'text':'a@example.com +55 11 99999-8888 192.168.1.3'}, 'url': 'https://user:pass@example.com/p/item?token=private#secret'})
    assert 'private' not in str(result)
    assert result['url'] == 'https://example.com/p/item'
    assert 'a@example.com' not in str(result)
