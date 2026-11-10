"""Production analysis must never fall back to the full category scan."""
from ai_context import enrich
from catalog_client import CatalogClient
from test_catalog_client import SETTINGS, FakeSession, FakeResponse


def test_client_uses_exact_lookup_endpoint():
    session = FakeSession(response=FakeResponse(body=[]))
    catalog = CatalogClient(SETTINGS, session)
    assert catalog.resolve_components('gpu', 'GeForce RTX 4060 Ti') == []
    assert session.last_request['url'].endswith('/components/resolve')
    assert session.last_request['params'] == {'category': 'gpu', 'q': 'GeForce RTX 4060 Ti'}


def test_unknown_indexed_lookup_never_scans_or_fuzzes():
    class Catalog:
        def resolve_components(self, category, name):
            return []

        def list_components(self, category):
            raise AssertionError('unbounded category scan')

        def search_components(self, category, name):
            raise AssertionError('legacy search')
    assert enrich('RTX 4070 Ti Super', 'gpu', Catalog())['catalog_id'] is None
