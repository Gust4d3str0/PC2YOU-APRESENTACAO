import requests
import pytest

from catalog_client import CatalogClient
from settings import Settings


SETTINGS = Settings(
    database_url="sqlite://",
    catalog_api_url="http://catalog.test",
    catalog_connect_timeout=0.1,
    catalog_read_timeout=0.1,
    catalog_retries=0,
    jwt_secret="test",
    jwt_algorithm="HS256",
    jwt_audience=None,
    cors_origins=(),
)


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.mounted = []
        self.last_request = None

    def mount(self, prefix, adapter):
        self.mounted.append(prefix)

    def request(self, method, url, timeout, **kwargs):
        self.last_request = {"method": method, "url": url, "timeout": timeout, **kwargs}
        if self.error:
            raise self.error
        return self.response


class FakeResponse:
    def __init__(self, status_code=200, body=None, json_error=None):
        self.status_code = status_code
        self.body = body
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.body


def test_timeout_becomes_controlled_503():
    client = CatalogClient(SETTINGS, FakeSession(error=requests.Timeout()))
    with pytest.raises(Exception) as error:
        client.get_component("cpu")
    assert error.value.status_code == 503


def test_invalid_json_becomes_controlled_503():
    response = FakeResponse(json_error=requests.JSONDecodeError("bad", "x", 0))
    client = CatalogClient(SETTINGS, FakeSession(response=response))
    with pytest.raises(Exception) as error:
        client.list_components()
    assert error.value.status_code == 503


def test_batch_uses_catalog_contract_component_ids():
    session = FakeSession(response=FakeResponse(body=[{"id": "cpu"}]))
    client = CatalogClient(SETTINGS, session)

    assert client.get_components(["cpu"]) == [{"id": "cpu"}]
    assert session.last_request["json"] == {"component_ids": ["cpu"]}


def test_ai_search_is_scoped_by_category_and_query():
    session = FakeSession(response=FakeResponse(body=[{"id": "cpu"}]))
    client = CatalogClient(SETTINGS, session)
    assert client.search_components("cpu", "Ryzen 5 5600") == [{"id": "cpu"}]
    assert session.last_request["params"] == {"category": "cpu", "q": "Ryzen 5 5600"}


def test_ai_search_accepts_explicit_catalog_id():
    session = FakeSession(response=FakeResponse(body={"id": "ryzen-5-5600", "category": "cpu"}))
    client = CatalogClient(SETTINGS, session)
    assert client.search_components("cpu", "ryzen-5-5600")[0]["id"] == "ryzen-5-5600"
    assert session.last_request["url"].endswith("/components/ryzen-5-5600")


def test_ai_search_unknown_id_falls_back_to_name_query():
    from unittest.mock import Mock
    client = CatalogClient(SETTINGS, FakeSession())
    client._request = Mock(side_effect=[FakeResponse(status_code=404), FakeResponse(body=[])])
    assert client.search_components("cpu", "unknown-cpu") == []
    assert client._request.call_count == 2


def test_ai_search_invalid_catalog_response_is_controlled():
    client = CatalogClient(SETTINGS, FakeSession(response=FakeResponse(body={"bad": True})))
    with pytest.raises(Exception) as error:
        client.search_components("cpu", "Ryzen")
    assert error.value.status_code == 503


def test_upgrade_candidates_request_the_light_technical_view():
    session = FakeSession(response=FakeResponse(body=[{"id": "gpu-1"}]))
    rows = CatalogClient(SETTINGS, session).upgrade_candidates("gpu")
    assert rows == [{"id": "gpu-1"}]
    assert session.last_request["params"] == {"category": "gpu", "limit": 24, "technical_only": True}
    assert session.last_request["timeout"][1] <= 6
